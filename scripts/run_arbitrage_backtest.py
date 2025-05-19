#!/usr/bin/env python
# scripts/run_arbitrage_backtest.py
"""
Advanced backtesting script for cryptocurrency arbitrage strategies.

This script simulates arbitrage trading between multiple exchanges using
historical price data, accounting for exchange fees, slippage, and realistic
execution constraints.
"""

import argparse
import logging
import os
import sys
import json
from datetime import datetime
import pandas as pd
import numpy as np
from tabulate import tabulate
import matplotlib.pyplot as plt
from colorama import Fore, Style, init

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import hydrobot modules
from hydrobot.utils.logger_setup import get_logger
from hydrobot.trading.position_manager import PositionManager

# Initialize colorama for colored output
init(autoreset=True)

logger = get_logger(__name__)

class ArbitrageBacktester:
    """Backtester for crypto arbitrage strategies."""
    
    def __init__(self, config_path='config.json', log_level='INFO'):
        """Initialize backtester with configuration.
        
        Args:
            config_path: Path to configuration file
            log_level: Logging level
        """
        self.setup_logging(log_level)
        self.config = self.load_config(config_path)
        self.exchanges = {ex['name']: ex for ex in self.config['exchanges']}
        self.symbol = self.config['symbol']
        self.trade_amount = self.config['trade_amount']
        self.max_trade_amount = self.config['max_trade_amount']
        self.min_profit_percent = self.config['min_profit_percent']
        self.slippage = self.config.get('slippage', 0.0005)  # Default 0.05%
        
        # Track balances and performance
        self.balances = {}
        self.trade_log = []
        self.position_manager = PositionManager()
        
        logger.info(f"ArbitrageBacktester initialized with symbol {self.symbol}")    def setup_logging(self, log_level):
        """Setup logging configuration."""
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(
            log_dir, 
            f"arbitrage_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        
        # Configure logging directly
        logging_level = getattr(logging, log_level.upper(), logging.INFO)
        
        # Setup file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging_level)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        # Apply configuration to root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging_level)
        root_logger.addHandler(file_handler)
        
        # Log the setup
        logger.info(f"Logging configured. Level: {log_level}, File: {log_file}")
    
    def load_config(self, config_path):
        """Load configuration from file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # Validate config
            required_keys = [
                'exchanges', 'symbol', 'min_profit_percent', 
                'trade_amount', 'max_trade_amount', 'initial_balance'
            ]
            
            for key in required_keys:
                if key not in config:
                    raise ValueError(f"Missing required config key: {key}")
                    
            return config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            sys.exit(1)
    
    def load_historical_data(self):
        """Load and synchronize historical data from all exchanges."""
        exchange_names = [ex['name'] for ex in self.config['exchanges']]
        data = {}
        
        # Exchange-specific symbol mapping
        exchange_symbol_map = {
            'binance': self.symbol,
            'kraken': self.symbol.replace('BTC', 'XBT'),
            'coinbase': self.symbol,
            'bitfinex': self.symbol,
            'huobi': self.symbol.replace('USD', 'USDT'),
            'bittrex': self.symbol,
            'bitstamp': self.symbol,
            'gemini': self.symbol,
            'okx': self.symbol.replace('USD', 'USDT'),
            'kucoin': self.symbol.replace('USD', 'USDT')
        }
        
        for exchange in exchange_names:
            ex_symbol = exchange_symbol_map.get(exchange, self.symbol)
            filename = f"data/{exchange}_{ex_symbol.replace('/', '')}.csv"
            
            try:
                df = pd.read_csv(filename, parse_dates=['timestamp'])
                df.sort_values('timestamp', inplace=True)
                
                # Ensure timestamps are timezone-naive for consistent comparison
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
                df.set_index('timestamp', inplace=True)
                
                data[exchange] = df
                logger.info(f"Loaded {len(df)} data points for {exchange}")
            except FileNotFoundError:
                logger.error(f"Data file {filename} not found")
            except Exception as e:
                logger.error(f"Error loading data from {filename}: {e}")
        
        return self.synchronize_data(data)
    
    def synchronize_data(self, data):
        """Synchronize data from multiple exchanges to common timestamps."""
        if not data:
            logger.error("No data loaded. Exiting.")
            sys.exit(1)
            
        df_list = []
        for ex_name, df in data.items():
            df = df[['bid', 'ask']]
            df.columns = pd.MultiIndex.from_product([[ex_name], df.columns])
            df_list.append(df)
            
        df_merged = pd.concat(df_list, axis=1)
        
        # Forward fill missing values (limited to 5 periods)
        df_merged = df_merged.fillna(method='ffill', limit=5)
        
        # Drop rows with any NaN values - ensure we have complete data for all exchanges
        df_merged = df_merged.dropna()
        
        logger.info(f"Data synchronized across {len(data)} exchanges, {len(df_merged)} valid data points")
        return df_merged
    
    def initialize_balances(self):
        """Initialize account balances for each exchange."""
        exchange_names = [ex['name'] for ex in self.config['exchanges']]
        initial_balance = self.config['initial_balance']
        
        self.balances = {
            ex: {'USD': initial_balance, 'BTC': 0, 'fee_paid': 0}
            for ex in exchange_names
        }
        
        logger.info(f"Initialized balance of ${initial_balance} for {len(exchange_names)} exchanges")
    
    def calculate_profit(self, buy_price, sell_price, buy_fee, sell_fee, amount):
        """Calculate profit accounting for fees and slippage."""
        # Apply slippage to prices
        buy_price_with_slip = buy_price * (1 + self.slippage)
        sell_price_with_slip = sell_price * (1 - self.slippage)
        
        # Calculate costs and revenue
        buy_cost = buy_price_with_slip * amount * (1 + buy_fee)
        sell_revenue = sell_price_with_slip * amount * (1 - sell_fee)
        
        profit = sell_revenue - buy_cost
        profit_percent = (profit / buy_cost) * 100
        
        return profit_percent, profit
    
    def find_arbitrage_opportunities(self, row, timestamp):
        """Find arbitrage opportunities in current market data."""
        opportunities = []
        exchange_names = row.columns.levels[0].tolist()
        
        for buy_ex in exchange_names:
            for sell_ex in exchange_names:
                if buy_ex == sell_ex:
                    continue
                    
                buy_price = row[(buy_ex, 'ask')]
                sell_price = row[(sell_ex, 'bid')]
                
                # Check if we have valid prices and price difference
                if pd.isna(buy_price) or pd.isna(sell_price) or buy_price >= sell_price:
                    continue
                
                buy_fee = self.exchanges[buy_ex]['fees']['taker']
                sell_fee = self.exchanges[sell_ex]['fees']['taker']
                
                # Calculate maximum trade amount based on available balance
                max_amount_usd = self.balances[buy_ex]['USD'] / (buy_price * (1 + buy_fee))
                max_amount_btc = self.balances[sell_ex]['BTC']  # Limit by BTC balance
                
                max_amount = min(
                    self.trade_amount,
                    self.max_trade_amount,
                    max_amount_usd
                )
                
                if max_amount <= 0:
                    continue
                    
                # Calculate profit
                profit_percent, profit = self.calculate_profit(
                    buy_price, sell_price, buy_fee, sell_fee, max_amount
                )
                
                logger.debug(
                    f"Opportunity: Buy {buy_ex} at {buy_price:.2f}, "
                    f"Sell {sell_ex} at {sell_price:.2f}, "
                    f"Profit: {profit_percent:.4f}%, ${profit:.2f}"
                )
                
                # Record if profit exceeds threshold
                if profit_percent >= self.min_profit_percent:
                    opportunity = {
                        'timestamp': timestamp,
                        'buy_exchange': buy_ex,
                        'sell_exchange': sell_ex,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'amount': max_amount,
                        'profit_percent': profit_percent,
                        'profit': profit
                    }
                    opportunities.append(opportunity)
        
        return opportunities
    
    def execute_trade(self, opportunity):
        """Simulate trade execution based on opportunity."""
        buy_ex = opportunity['buy_exchange']
        sell_ex = opportunity['sell_exchange']
        amount = opportunity['amount']
        buy_price = opportunity['buy_price']
        sell_price = opportunity['sell_price']
        
        buy_fee = self.exchanges[buy_ex]['fees']['taker']
        sell_fee = self.exchanges[sell_ex]['fees']['taker']
        
        # Apply slippage
        buy_price_with_slip = buy_price * (1 + self.slippage)
        sell_price_with_slip = sell_price * (1 - self.slippage)
        
        # Calculate costs and update balances
        buy_cost = buy_price_with_slip * amount * (1 + buy_fee)
        sell_revenue = sell_price_with_slip * amount * (1 - sell_fee)
        
        buy_fee_paid = buy_price_with_slip * amount * buy_fee
        sell_fee_paid = sell_price_with_slip * amount * sell_fee
        
        # Check if we have enough balance
        if self.balances[buy_ex]['USD'] < buy_cost:
            logger.warning(
                f"Insufficient USD balance on {buy_ex}. "
                f"Required: ${buy_cost:.2f}, Available: ${self.balances[buy_ex]['USD']:.2f}"
            )
            return False
        
        # Execute buy
        self.balances[buy_ex]['USD'] -= buy_cost
        self.balances[buy_ex]['BTC'] += amount
        self.balances[buy_ex]['fee_paid'] += buy_fee_paid
        
        # Execute sell
        self.balances[sell_ex]['BTC'] -= amount
        self.balances[sell_ex]['USD'] += sell_revenue
        self.balances[sell_ex]['fee_paid'] += sell_fee_paid
        
        # Update opportunity with actual results
        opportunity['executed'] = True
        opportunity['actual_buy_price'] = buy_price_with_slip
        opportunity['actual_sell_price'] = sell_price_with_slip
        opportunity['actual_profit'] = sell_revenue - buy_cost
        opportunity['fees_paid'] = buy_fee_paid + sell_fee_paid
        
        logger.info(
            f"Executed: Buy {amount:.4f} BTC on {buy_ex} at ${buy_price_with_slip:.2f}, "
            f"Sell on {sell_ex} at ${sell_price_with_slip:.2f}, "
            f"Profit: ${opportunity['actual_profit']:.2f}"
        )
        
        return True
    
    def run_backtest(self):
        """Run the backtest."""
        logger.info("Starting arbitrage backtest")
        
        # Load and synchronize data
        df_merged = self.load_historical_data()
        if df_merged.empty:
            logger.error("No synchronized data available. Exiting.")
            return None, None
            
        # Initialize balances
        self.initialize_balances()
        
        # Iterate through each timestamp
        for timestamp, row in df_merged.iterrows():
            # Find opportunities
            opportunities = self.find_arbitrage_opportunities(row, timestamp)
            
            # Execute the most profitable opportunity
            if opportunities:
                # Sort by profit and take the best one
                best_opportunity = max(opportunities, key=lambda x: x['profit'])
                success = self.execute_trade(best_opportunity)
                
                if success:
                    self.trade_log.append(best_opportunity)
        
        # Calculate final performance
        performance = self.calculate_performance()
        
        return performance, pd.DataFrame(self.trade_log)
    
    def calculate_performance(self):
        """Calculate performance metrics."""
        # Calculate total balance across all exchanges
        total_usd = sum(balance['USD'] for balance in self.balances.values())
        total_btc = sum(balance['BTC'] for balance in self.balances.values())
        total_fees = sum(balance['fee_paid'] for balance in self.balances.values())
        
        # Calculate profit
        initial_balance = self.config['initial_balance'] * len(self.balances)
        profit = total_usd - initial_balance
        profit_percent = (profit / initial_balance) * 100
        
        # Calculate other metrics
        num_trades = len(self.trade_log)
        if num_trades > 0:
            avg_profit_per_trade = profit / num_trades
            max_profit = max([t['actual_profit'] for t in self.trade_log]) if num_trades > 0 else 0
            min_profit = min([t['actual_profit'] for t in self.trade_log]) if num_trades > 0 else 0
        else:
            avg_profit_per_trade = 0
            max_profit = 0
            min_profit = 0
            
        performance = {
            'total_balance_usd': total_usd,
            'total_balance_btc': total_btc,
            'profit': profit,
            'profit_percent': profit_percent,
            'total_fees_paid': total_fees,
            'num_trades': num_trades,
            'avg_profit_per_trade': avg_profit_per_trade,
            'max_profit': max_profit,
            'min_profit': min_profit
        }
        
        return performance
    
    def print_results(self, performance, trade_df):
        """Print backtest results in a formatted way."""
        print(f"\n{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}ARBITRAGE BACKTEST RESULTS{Style.RESET_ALL}".center(60))
        print(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}\n")
        
        profit_color = Fore.GREEN if performance['profit'] > 0 else Fore.RED
        
        # Print summary table
        summary_data = [
            ["Total Final Balance", f"${performance['total_balance_usd']:.2f}"],
            ["BTC Balance", f"{performance['total_balance_btc']:.8f} BTC"],
            ["Total Profit", f"{profit_color}${performance['profit']:.2f}{Style.RESET_ALL}"],
            ["Profit %", f"{profit_color}{performance['profit_percent']:.2f}%{Style.RESET_ALL}"],
            ["Number of Trades", performance['num_trades']],
            ["Total Fees Paid", f"${performance['total_fees_paid']:.2f}"],
            ["Avg Profit per Trade", f"{profit_color}${performance['avg_profit_per_trade']:.2f}{Style.RESET_ALL}"],
        ]
        
        print(tabulate(summary_data, headers=["Metric", "Value"], tablefmt="fancy_grid"))
        
        # Print exchange balances
        print("\nFinal Exchange Balances:")
        balances_data = []
        
        for ex_name, balance in self.balances.items():
            balances_data.append([
                ex_name,
                f"${balance['USD']:.2f}",
                f"{balance['BTC']:.8f}",
                f"${balance['fee_paid']:.2f}"
            ])
            
        print(tabulate(
            balances_data, 
            headers=["Exchange", "USD Balance", "BTC Balance", "Fees Paid"], 
            tablefmt="fancy_grid"
        ))
        
        # Print sample trades
        if not trade_df.empty:
            print("\nSample Trades:")
            sample_size = min(5, len(trade_df))
            sample_trades = trade_df.sample(sample_size) if len(trade_df) > 5 else trade_df
            
            # Format for display
            sample_trades_display = sample_trades.copy()
            sample_trades_display['timestamp'] = sample_trades_display['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            sample_trades_display['profit'] = sample_trades_display['actual_profit'].map(lambda x: f"${x:.2f}")
            
            display_cols = ['timestamp', 'buy_exchange', 'sell_exchange', 'amount', 'profit']
            print(tabulate(
                sample_trades_display[display_cols].values, 
                headers=["Timestamp", "Buy Exchange", "Sell Exchange", "BTC Amount", "Profit"], 
                tablefmt="fancy_grid"
            ))
            
        # Save results to CSV
        if not trade_df.empty:
            results_dir = 'results'
            if not os.path.exists(results_dir):
                os.makedirs(results_dir)
                
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            trade_df.to_csv(f"{results_dir}/arbitrage_trades_{timestamp}.csv", index=False)
            
            # Save performance summary
            with open(f"{results_dir}/arbitrage_performance_{timestamp}.json", 'w') as f:
                json.dump(performance, f, indent=2)
                
            print(f"\nResults saved to {results_dir}/arbitrage_trades_{timestamp}.csv")
            
    def plot_results(self, trade_df):
        """Plot backtest results."""
        if trade_df.empty:
            logger.warning("No trades to plot")
            return
            
        # Create results directory if it doesn't exist
        results_dir = 'results'
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
            
        # Calculate cumulative profit
        trade_df['cumulative_profit'] = trade_df['actual_profit'].cumsum()
        
        plt.figure(figsize=(12, 8))
        
        # Plot cumulative profit
        plt.subplot(2, 1, 1)
        plt.plot(trade_df['timestamp'], trade_df['cumulative_profit'], 'b-')
        plt.title('Cumulative Profit Over Time')
        plt.xlabel('Time')
        plt.ylabel('Cumulative Profit ($)')
        plt.grid(True)
        
        # Plot profit per trade
        plt.subplot(2, 1, 2)
        plt.bar(range(len(trade_df)), trade_df['actual_profit'], color='g')
        plt.title('Profit per Trade')
        plt.xlabel('Trade Number')
        plt.ylabel('Profit ($)')
        plt.grid(True)
        
        plt.tight_layout()
        
        # Save plot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plt.savefig(f"{results_dir}/arbitrage_plot_{timestamp}.png")
        plt.close()
        
        logger.info(f"Plot saved to {results_dir}/arbitrage_plot_{timestamp}.png")

def main():
    """Main function to run the arbitrage backtester."""
    parser = argparse.ArgumentParser(description="Cryptocurrency Arbitrage Backtester")
    parser.add_argument(
        "--config", 
        type=str, 
        default="config.json",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--log-level", 
        type=str, 
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    parser.add_argument(
        "--plot", 
        action="store_true",
        help="Generate performance plots"
    )
    
    args = parser.parse_args()
    
    # Run backtest
    backtester = ArbitrageBacktester(args.config, args.log_level)
    performance, trade_df = backtester.run_backtest()
    
    if performance:
        backtester.print_results(performance, trade_df)
        
        if args.plot and not trade_df.empty:
            backtester.plot_results(trade_df)
    
if __name__ == "__main__":
    main()
