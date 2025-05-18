# hydrobot2/trader.py

import asyncio
import time
import math
from typing import Dict, Any, Optional

# --- FIX: Use relative imports ---
from .config.settings import get_config, AppSettings
from .strategies.strategy_manager import StrategyManager
from .strategies.base_strategy import Signal
from .trading.position_manager import PositionManager
from .trading.risk_controller import RiskController
from .trading.order_executor import OrderExecutor, OrderExecutionError
# Use relative import for trading_utils
from .trading import trading_utils
from .utils.logger_setup import get_logger
# from .data.market_data_stream import MarketDataStream # Placeholder

log = get_logger()

class TradingManager:
    """Orchestrates the main trading loop."""
    def __init__(self, config: AppSettings, strategy_manager: StrategyManager,
                 position_manager: PositionManager, risk_controller: RiskController,
                 order_executor: OrderExecutor): # Removed market_data_stream for now
        """Initializes the TradingManager."""
        self.config = config
        self.strategy_manager = strategy_manager
        self.position_manager = position_manager
        self.risk_controller = risk_controller
        self.order_executor = order_executor
        self.trading_symbols = config.trading.symbols
        self.is_running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self.latest_market_data: Dict[str, Dict[str, Any]] = {}
        self.latest_prices: Dict[str, float] = {}
        log.info("TradingManager initialized.")
        log.info(f"Managing symbols: {self.trading_symbols}")

    async def _handle_market_data_update(self, symbol: str, data: Dict[str, Any]):
        """Processes incoming market data updates (called by simulator/stream)."""
        log.debug(f"Market data for {symbol} @ {data.get('timestamp')}")
        self.latest_market_data[symbol] = data

        # Update latest price (ensure keys exist and values are valid)
        bids = data.get('bids')
        asks = data.get('asks')
        if bids and asks and bids[0] and asks[0] and \
           isinstance(bids[0][0], (int, float)) and not math.isnan(bids[0][0]) and \
           isinstance(asks[0][0], (int, float)) and not math.isnan(asks[0][0]):
            mid_price = (bids[0][0] + asks[0][0]) / 2
            if mid_price > 0 and not math.isinf(mid_price): # Basic validation
                 self.latest_prices[symbol] = mid_price
                 log.debug(f"[{symbol}] Updated latest price: {mid_price:.4f}")
            else:
                 log.warning(f"[{symbol}] Calculated invalid mid-price: {mid_price}")
        else:
             # Fallback: use last trade price if available?
             last_trade = data.get('last_trade')
             if last_trade and isinstance(last_trade, (int, float)) and not math.isnan(last_trade) and last_trade > 0:
                   self.latest_prices[symbol] = last_trade
                   log.debug(f"[{symbol}] Updated latest price (last trade): {last_trade:.4f}")
             # else: Keep old price or mark as stale?


        # Trigger Trading Logic if not already running for this symbol
        if symbol not in self._tasks or self._tasks[symbol].done():
             # Pass a copy of data to avoid race conditions if data is mutated later
             self._tasks[symbol] = asyncio.create_task(self._run_trade_cycle(symbol, market_data.copy()))
        else:
             log.debug(f"[{symbol}] Trade cycle task busy. Skipping.")

    async def _run_trade_cycle(self, symbol: str, market_data: Dict[str, Any]):
        """Executes a single trading cycle for a symbol."""
        log.debug(f"--- Running trade cycle for {symbol} ---")

        # --- 1. Get Strategy & Signal ---
        market_regime = "default" # Placeholder
        strategy = self.strategy_manager.get_strategy_for_symbol(symbol, market_regime)
        if not strategy: log.error(f"[{symbol}] No strategy found. Skipping."); return

        model_prediction = None # Placeholder
        try:
             signal = strategy.generate_signal(market_data, model_prediction)
             log.info(f"[{symbol}] Strategy '{strategy.get_name()}' signal: {signal}")
        except Exception as e: log.exception(f"[{symbol}] Signal generation error: {e}"); return

        # --- 2. Validate Risk ---
        portfolio_value = self.position_manager.get_total_portfolio_value(self.latest_prices)
        log.debug(f"[{symbol}] Portfolio value for risk check: {portfolio_value:.2f}")
        try:
             validated_signal = self.risk_controller.validate_trade(signal, portfolio_value, self.latest_prices)
        except Exception as e: log.exception(f"[{symbol}] Risk validation error: {e}"); return

        if not validated_signal: log.info(f"[{symbol}] Signal rejected by RiskController."); return
        signal = validated_signal # Use potentially modified signal

        # --- 3. Format & Validate Params ---
        if signal.action in ["BUY", "SELL"]:
             if signal.quantity is None or signal.quantity <= 0:
                  log.error(f"[{symbol}] Invalid signal qty ({signal.quantity}). Skipping."); return

             formatted_quantity = trading_utils.format_quantity(symbol, signal.quantity)
             formatted_price = trading_utils.format_price(symbol, signal.price) if signal.price else None

             if formatted_quantity is None or (signal.order_type == "LIMIT" and formatted_price is None):
                  log.error(f"[{symbol}] Format error: Qty={formatted_quantity}, Price={formatted_price}. Skipping."); return
             if formatted_quantity <= 0 or (formatted_price is not None and formatted_price <=0):
                  log.error(f"[{symbol}] Invalid formatted values: Qty={formatted_quantity}, Price={formatted_price}. Skipping."); return


             is_size_valid = trading_utils.check_min_order_size(symbol, formatted_quantity, formatted_price)
             if not is_size_valid: log.warning(f"[{symbol}] Order size {formatted_quantity} invalid. Skipping."); return

             signal.quantity = formatted_quantity
             signal.price = formatted_price
             log.debug(f"[{symbol}] Formatted params: Qty={signal.quantity}, Price={signal.price}")

             # --- 4. Execute Order ---
             try:
                  log.info(f"[{symbol}] Executing signal: {signal}")
                  # Pass current prices for market order simulation
                  order_result = await self.order_executor.execute_signal(signal, self.latest_prices)
                  if order_result: log.info(f"[{symbol}] Execution result: {order_result.get('status')}, ID: {order_result.get('id')}")
                  else: log.warning(f"[{symbol}] Execution did not return result.")
             except OrderExecutionError as e: log.error(f"[{symbol}] Execution failed: {e}")
             except Exception as e: log.exception(f"[{symbol}] Unexpected execution error: {e}")

        log.debug(f"--- Finished trade cycle for {symbol} ---")


    async def start(self):
        """Starts the TradingManager."""
        if self.is_running: log.warning("TradingManager already running."); return
        log.info("Starting TradingManager...")
        self.is_running = True
        try:
            # Initialize executor (connects to exchange)
            await self.order_executor.initialize_exchange() # Use renamed public method
            if not self.order_executor.is_initialized:
                 raise RuntimeError("Order Executor failed initialization.")
            # Update market cache using the initialized executor's exchange object
            await trading_utils.update_market_cache(self.order_executor.exchange)
        except Exception as e:
             log.critical(f"TradingManager start failed during initialization: {e}")
             self.is_running = False
             return

        # --- Start Data Simulation ---
        log.warning("!!! STARTING SIMULATED MARKET DATA !!!")
        async def simulate_data():
            while self.is_running:
                for symbol in self.trading_symbols:
                    timestamp = time.time()
                    # Simulate slightly more realistic price movement
                    base_price = 50000 + (symbol.__hash__() % 1000) # Different base per symbol
                    price = base_price + math.sin(timestamp / (60 + (symbol.__hash__() % 30))) * 100
                    spread = max(1.0, price * 0.0001) # Min spread $1 or 0.01%
                    bid = max(0.01, price - spread / 2) # Ensure positive prices
                    ask = max(0.01, price + spread / 2)
                    fake_data = { 'timestamp': timestamp, 'bids': [(bid, 1.0)], 'asks': [(ask, 1.0)], 'last_trade': price }
                    await self._handle_market_data_update(symbol, fake_data)
                await asyncio.sleep(3) # Update slightly faster

        self._tasks["data_simulator"] = asyncio.create_task(simulate_data())
        log.info("TradingManager started (with simulated data).")

    async def stop(self):
        """Stops the TradingManager."""
        if not self.is_running: log.warning("TradingManager not running."); return
        log.info("Stopping TradingManager...")
        self.is_running = False
        # Cancel tasks (same as before)
        # ... (task cancellation logic) ...
        tasks_to_cancel = [task for task in self._tasks.values() if task and not task.done()]
        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.cancel()
            try:
                 await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                 log.info("Async tasks cancelled.")
            except asyncio.CancelledError:
                 log.info("Tasks cancellation confirmed.")
            except Exception as e:
                 log.exception(f"Error during task gather/cancellation: {e}")


        if self.order_executor: await self.order_executor.close()
        self._tasks.clear()
        log.info("TradingManager stopped.")
