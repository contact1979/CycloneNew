# hydrobot/trading/order_executor.py

import ccxt.async_support as ccxt # Use the async version of ccxt
import asyncio
import time
import math
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

# --- FIX: Use relative imports ---
from ..config.settings import get_config, AppSettings
from ..strategies.base_strategy import Signal, OrderType
from ..utils.logger_setup import get_logger
from .position_manager import PositionManager # To notify about fills

log = get_logger()

class OrderExecutionError(Exception):
    """Custom exception for errors during order placement or management."""
    pass

class OrderExecutor:
    """Handles interaction with the exchange API to execute trades."""
    def __init__(self, config: AppSettings, position_manager: PositionManager):
        """Initializes the OrderExecutor."""
        self.config = config
        self.position_manager = position_manager
        self.exchange_name = config.exchange.name
        self.is_sandbox = config.exchange.is_sandbox
        self.exchange: Optional[ccxt.Exchange] = None
        self.is_initialized = False
        self.api_key = config.exchange.api_key.get_secret_value() if config.exchange.api_key else None
        self.api_secret = config.exchange.api_secret.get_secret_value() if config.exchange.api_secret else None
        self.api_passphrase = config.exchange.api_passphrase.get_secret_value() if config.exchange.api_passphrase else None
        self.last_order_time = 0
        self.min_order_interval = 0.5 # Seconds

    async def initialize_exchange(self): # Renamed from _initialize_exchange for clarity
        """Initializes the ccxt exchange instance."""
        if self.is_initialized: return
        log.info(f"Initializing exchange '{self.exchange_name}'...")
        # ... (Rest of initialization logic remains the same) ...
        exchange_class = getattr(ccxt, self.exchange_name, None)
        if not exchange_class:
            raise OrderExecutionError(f"Unsupported exchange: {self.exchange_name}")

        exchange_config = {'apiKey': self.api_key, 'secret': self.api_secret, 'enableRateLimit': True}
        if self.api_passphrase: exchange_config['password'] = self.api_passphrase

        if self.is_sandbox:
             # Simplified sandbox logic check - ccxt handles many cases via standard properties
             log.info(f"Attempting to enable sandbox mode for {self.exchange_name}.")
             exchange_config['options'] = {'sandboxMode': True} # Common option
             # Or check URLs directly if needed:
             # if 'test' in exchange_class.urls: exchange_config['urls'] = {'api': exchange_class.urls['test']}

        try:
            self.exchange = exchange_class(exchange_config)
            # Set sandbox mode if needed via specific method (some exchanges)
            if self.is_sandbox and hasattr(self.exchange, 'set_sandbox_mode'):
                 self.exchange.set_sandbox_mode(True)

            log.info(f"Loading markets for {self.exchange_name}...")
            await self.exchange.load_markets()
            log.info(f"Exchange '{self.exchange_name}' initialized successfully.")
            self.is_initialized = True
        except ccxt.AuthenticationError as e:
            log.critical(f"Exchange authentication failed: {e}")
            await self.close() # Close connection on critical failure
            raise OrderExecutionError(f"AuthenticationError: {e}") from e
        except Exception as e:
            log.exception(f"Failed to initialize exchange: {e}")
            await self.close()
            raise OrderExecutionError(f"Initialization failed: {e}") from e

    async def execute_signal(self, signal: Signal, current_prices: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """Attempts to execute a trade based on the provided signal."""
        if not self.is_initialized or not self.exchange:
            log.error("Cannot execute signal: Exchange not initialized.")
            # Try to re-initialize? Risky if called repeatedly.
            # await self.initialize_exchange() # Consider calling this explicitly before starting trader
            raise OrderExecutionError("Exchange not ready.")

        if signal.action == "HOLD" or signal.quantity is None or signal.quantity <= 0 or signal.symbol is None:
            log.debug(f"[{signal.symbol}] No execution for signal: {signal.action}")
            return None

        # --- Rate Limiting & Param Validation ---
        current_time = asyncio.get_event_loop().time()
        # ... (rate limit check) ...
        self.last_order_time = current_time

        symbol = signal.symbol
        side = 'buy' if signal.action == "BUY" else 'sell'
        amount = signal.quantity
        order_type = signal.order_type.lower()
        price = signal.price if order_type == 'limit' else None

        if math.isnan(amount) or math.isinf(amount) or \
           (price is not None and (math.isnan(price) or math.isinf(price))):
            log.error(f"[{symbol}] Invalid order parameters: Qty={amount}, Price={price}. Rejecting.")
            raise OrderExecutionError("Invalid numeric parameters in signal.")

        log.info(f"[{symbol}] Placing {side} {order_type} order: Qty={amount:.8f}, Price={price}")

        # --- Place Order (Simulated) ---
        try:
            order_result = None
            simulated_status = 'open' # Default simulation
            simulated_filled = 0.0
            simulated_average = price

            # --- !!! SIMULATION LOGIC START !!! ---
            log.warning("!!! SIMULATING ORDER PLACEMENT (No actual trade) !!!")
            order_id = f'sim_{int(time.time()*1000)}'
            timestamp = int(time.time()*1000)
            current_price = current_prices.get(symbol)

            if order_type == 'limit':
                if price is None: raise OrderExecutionError("Limit order needs price.")
                # Simulate fill based on price relative to current market (simple)
                if current_price:
                     if side == 'buy' and price >= current_price: simulated_status = 'closed'; simulated_filled = amount; simulated_average=current_price
                     if side == 'sell' and price <= current_price: simulated_status = 'closed'; simulated_filled = amount; simulated_average=current_price
                else: log.warning(f"[{symbol}] Cannot simulate limit fill: No current price.")

            elif order_type == 'market':
                 if current_price:
                     simulated_status = 'closed'; simulated_filled = amount; simulated_average=current_price
                 else:
                     log.warning(f"[{symbol}] Cannot simulate market fill: No current price. Assuming open.")
                     simulated_status = 'open' # Cannot determine fill price


            order_result = {
                'id': order_id, 'timestamp': timestamp, 'datetime': datetime.utcnow().isoformat(),
                'symbol': symbol, 'type': order_type, 'side': side,
                'price': price, 'amount': amount, 'status': simulated_status,
                'filled': simulated_filled, 'average': simulated_average,
                'info': {'simulated': True, 'sim_fill_price': simulated_average}
            }
            await asyncio.sleep(0.1) # Simulate latency
            # --- !!! SIMULATION LOGIC END !!! ---

            # Replace above simulation block with actual ccxt calls:
            # if order_type == 'limit':
            #     order_result = await self.exchange.create_limit_order(symbol, side, amount, price)
            # elif order_type == 'market':
            #     order_result = await self.exchange.create_market_order(symbol, side, amount)
            # else:
            #     raise OrderExecutionError(f"Unsupported order type: {order_type}")

            log.info(f"[{symbol}] Order placement attempted (Simulated): ID={order_result.get('id')}, Status={order_result.get('status')}")
            log.debug(f"Order Result: {order_result}")

            # --- Process Fill (Simulated) ---
            if order_result and order_result.get('status') == 'closed' and order_result.get('filled', 0) > 0:
                 fill_qty = order_result.get('filled')
                 fill_price = order_result.get('average', order_result.get('price')) # Use average if available
                 fill_timestamp = order_result.get('timestamp', time.time() * 1000) / 1000
                 position_update_qty = fill_qty if side == 'buy' else -fill_qty
                 log.info(f"[{symbol}] Simulated Fill. Updating position: Qty={position_update_qty:.8f}, Price={fill_price:.2f}")
                 self.position_manager.update_position_on_fill(symbol, position_update_qty, fill_price, fill_timestamp)

            return order_result

        # --- Error Handling (remains the same) ---
        except ccxt.InsufficientFunds as e: # ... etc
             log.error(f"[{symbol}] Order failed: Insufficient funds. {e}")
             raise OrderExecutionError(f"InsufficientFunds: {e}") from e
        except ccxt.InvalidOrder as e:
            log.error(f"[{symbol}] Order failed: Invalid order parameters. {e}")
            raise OrderExecutionError(f"InvalidOrder: {e}") from e
        except ccxt.NetworkError as e:
            log.error(f"[{symbol}] Order failed: Network error. {e}")
            raise OrderExecutionError(f"NetworkError: {e}") from e
        except ccxt.ExchangeError as e:
            log.error(f"[{symbol}] Order failed: Exchange error. {e}")
            raise OrderExecutionError(f"ExchangeError: {e}") from e
        except Exception as e:
            log.exception(f"[{symbol}] Unexpected error during order execution: {e}")
            raise OrderExecutionError(f"Unexpected error: {e}") from e


    # ... (cancel_order, fetch_order_status remain largely the same, ensure they check self.is_initialized) ...

    async def close(self):
        """Closes the exchange connection."""
        if self.exchange:
            log.info(f"Closing exchange '{self.exchange_name}' connection...")
            try:
                await self.exchange.close()
            except Exception as e:
                log.exception(f"Error closing exchange connection: {e}")
            finally:
                self.exchange = None
                self.is_initialized = False
                log.info("Exchange connection closed.")

    # Placeholder methods for cancel/fetch
    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
         if not self.is_initialized: raise OrderExecutionError("Exchange not initialized.")
         log.warning(f"!!! SIMULATING CANCEL ORDER {order_id} !!!")
         return {'info': {'simulated_cancel': True, 'id': order_id}}

    async def fetch_order_status(self, order_id: str, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
         if not self.is_initialized: raise OrderExecutionError("Exchange not initialized.")
         log.warning(f"!!! SIMULATING FETCH STATUS {order_id} !!!")
         return {'id': order_id, 'status': 'open', 'symbol': symbol or 'UNKNOWN', 'info': {'simulated_fetch': True}}
