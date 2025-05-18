"""Backtesting script for cryptocurrency trading strategies.

This script simulates trading strategies on historical data to evaluate their
performance without risking real capital. It supports multiple data sources,
strategies, and generates detailed performance metrics and visualizations.
"""

import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple

from hydrobot.config.settings import settings
from hydrobot.utils.logger_setup import setup_logging, get_logger
from hydrobot.data.technicals import calculate_indicators
from hydrobot.data.data_loader import load_historical_data
from hydrobot.strategies.strategy_manager import StrategyManager
from hydrobot.trading.portfolio import PortfolioManager
from hydrobot.trading.position_manager import PositionManager
from hydrobot.trading.risk_controller import RiskController
from hydrobot.database.db_utils import df_to_db
from hydrobot.utils.backtest_metrics import calculate_metrics

logger = get_logger(__name__)

class Backtester:
    """Backtesting engine that simulates trading on historical data."""
    
    def __init__(self, config: Dict):
        """Initialize backtester with configuration.
        
        Args:
            config: Configuration dictionary from settings
        """
        self.config = config
        self.initial_capital = config['initial_capital']
        self.fee_rate = config['fee_rate']
        self.slippage = config['slippage']
        
        # Initialize components
        self.portfolio = PortfolioManager(initial_capital=self.initial_capital)
        self.position_manager = PositionManager()
        self.risk_controller = RiskController(
            risk_settings=settings.risk,
            position_manager=self.position_manager
        )
        self.strategy_manager = StrategyManager(settings.strategy)
        
        # Track trades and performance
        self.trades: List[Dict] = []
        self.equity_curve: List[float] = []
        self.current_time: Optional[datetime] = None
        
    async def initialize(self) -> bool:
        """Initialize backtesting components.
        
        Returns:
            True if initialization successful
        """
        try:
            # Initialize strategy
            if not await self.strategy_manager.initialize():
                return False
                
            # Initialize tracking for each symbol
            for symbol in settings.exchange.trading_pairs:
                self.position_manager.initialize_symbol(symbol)
                
            return True
            
        except Exception as e:
            logger.error("Backtester initialization error", error=str(e))
            return False
            
    def simulate_order(self, symbol: str, side: str, size: float, current_price: float) -> Dict:
        """Simulate order execution with slippage and fees.
        
        Args:
            symbol: Trading pair symbol
            side: Order side ('buy' or 'sell')
            size: Order size
            current_price: Current market price
            
        Returns:
            Dict containing order execution details
        """
        # Apply random slippage within configured range
        slippage_factor = 1 + (np.random.uniform(-1, 1) * self.slippage)
        executed_price = current_price * slippage_factor
        
        # Calculate fill amount and fees
        executed_size = size
        fee = executed_size * executed_price * self.fee_rate
        
        return {
            'symbol': symbol,
            'side': side,
            'size': executed_size,
            'price': executed_price,
            'fee': fee,
            'timestamp': self.current_time
        }
        
    def update_portfolio(self, order: Dict) -> None:
        """Update portfolio after order execution.
        
        Args:
            order: Order execution details
        """
        # Update position
        size_with_sign = order['size'] if order['side'] == 'buy' else -order['size']
        self.position_manager.update_position(
            order['symbol'],
            size_with_sign,
            order['price'],
            order['timestamp']
        )
        
        # Track trade
        self.trades.append(order)
        
        # Update equity curve
        total_value = self.portfolio.calculate_total_value()
        self.equity_curve.append(total_value)
        
    async def process_market_update(self, 
                                  market_data: Dict,
                                  predictions: Optional[Dict] = None) -> None:
        """Process a single market data update in the backtest.
        
        Args:
            market_data: Market data update
            predictions: Optional model predictions
        """
        self.current_time = market_data['timestamp']
        
        # Check if trading allowed by risk controller
        if not self.risk_controller.can_trade(market_data['symbol']):
            return
            
        # Get trading signal from strategy
        signal = await self.strategy_manager.process_market_update(
            market_data['symbol'],
            market_data,
            predictions
        )
        
        if signal:
            # Simulate order execution
            order = self.simulate_order(
                signal.symbol,
                signal.side,
                signal.size,
                market_data['close']
            )
            
            # Update portfolio state
            self.update_portfolio(order)
            
    def generate_metrics(self) -> Dict:
        """Calculate backtest performance metrics.
        
        Returns:
            Dict containing performance metrics
        """
        equity_series = pd.Series(self.equity_curve)
        return calculate_metrics(
            equity_series,
            self.trades,
            self.initial_capital,
            settings.backtest.metrics
        )
        
    def save_results(self, metrics: Dict) -> None:
        """Save backtest results and generate reports.
        
        Args:
            metrics: Performance metrics
        """
        if not self.config['metrics']['save_trades']:
            return
            
        # Create results directory
        results_dir = Path(self.config['report_directory'])
        results_dir.mkdir(exist_ok=True)
        
        # Save trades to CSV
        trades_df = pd.DataFrame(self.trades)
        trades_df.to_csv(results_dir / 'trades.csv', index=False)
        
        # Save metrics
        metrics_df = pd.DataFrame([metrics])
        metrics_df.to_csv(results_dir / 'metrics.csv', index=False)
        
        # Save equity curve
        if self.config['metrics']['plot_equity']:
            equity_df = pd.DataFrame({
                'timestamp': [t['timestamp'] for t in self.trades],
                'equity': self.equity_curve
            })
            equity_df.to_csv(results_dir / 'equity.csv', index=False)
            
        logger.info("Saved backtest results to %s", results_dir)

async def run_backtest(
    symbols: List[str],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> None:
    """Run backtest on historical data.
    
    Args:
        symbols: List of trading pairs to backtest
        start_date: Start date for historical data
        end_date: End date for historical data
    """
    # Initialize backtester
    backtester = Backtester(settings.backtest)
    if not await backtester.initialize():
        logger.error("Failed to initialize backtester")
        return
        
    # Load historical data
    data = await load_historical_data(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        source=settings.backtest.data_source
    )
    
    if not data:
        logger.error("No historical data loaded")
        return
        
    # Add technical indicators
    for symbol in data:
        data[symbol] = calculate_indicators(data[symbol])
        
    logger.info("Starting backtest simulation...")
    
    # Process each symbol's data chronologically
    for symbol in symbols:
        symbol_data = data[symbol]
        
        for _, row in symbol_data.iterrows():
            market_update = {
                'symbol': symbol,
                'timestamp': row.name,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
                'indicators': {
                    col: row[col] for col in row.index 
                    if col not in ['open', 'high', 'low', 'close', 'volume']
                }
            }
            
            await backtester.process_market_update(market_update)
            
    # Calculate and save performance metrics
    metrics = backtester.generate_metrics()
    backtester.save_results(metrics)
    
    # Log summary
    logger.info("Backtest completed")
    logger.info("Performance Metrics:")
    for key, value in metrics.items():
        logger.info(f"{key}: {value}")

async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Cryptocurrency Trading Backtest')
    parser.add_argument(
        '--symbols',
        type=str,
        nargs='+',
        help='Trading pairs to backtest'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = args.log_level or settings.log_level
    setup_logging(log_level)
    
    # Get symbols from args or settings
    symbols = args.symbols or settings.exchange.trading_pairs
    if not symbols:
        logger.error("No symbols specified and none found in settings")
        return
        
    # Parse dates if provided
    start_date = None
    end_date = None
    if args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
        
    # Run backtest
    await run_backtest(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date
    )

if __name__ == '__main__':
    asyncio.run(main())
