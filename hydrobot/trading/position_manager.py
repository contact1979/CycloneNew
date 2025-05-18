# hydrobot/trading/position_manager.py

import json
import time
import math # For isnan
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover
    redis = None

# --- FIX: Use relative imports ---
from ..config.settings import get_config, AppSettings
from ..utils.logger_setup import get_logger

log = get_logger()

@dataclass
class Position:
    """Represents the bot's position in a single trading symbol."""
    symbol: str
    quantity: float = 0.0
    average_entry_price: float = 0.0
    last_update_time: float = 0.0

    def update_position(self, fill_quantity: float, fill_price: float, timestamp: float):
        """Updates the position based on a trade fill."""
        # Add validation for NaN/Inf values
        if math.isnan(fill_quantity) or math.isnan(fill_price) or math.isinf(fill_quantity) or math.isinf(fill_price):
             log.error(f"[{self.symbol}] Invalid fill data: Qty={fill_quantity}, Price={fill_price}. Ignoring update.")
             return

        log.info(f"[{self.symbol}] Updating position: Qty={fill_quantity:.8f} @ Price={fill_price:.2f}")

        # If closing out the position exactly
        if abs(self.quantity + fill_quantity) < 1e-9:
            log.info(f"[{self.symbol}] Position closed.")
            self.quantity = 0.0
            self.average_entry_price = 0.0
        # If opening or adding to position
        elif (self.quantity >= 0 and fill_quantity > 0) or (self.quantity <= 0 and fill_quantity < 0):
             old_value = self.quantity * self.average_entry_price
             new_value = fill_quantity * fill_price
             new_quantity = self.quantity + fill_quantity
             # Avoid division by zero if new_quantity is somehow zero
             self.average_entry_price = (old_value + new_value) / new_quantity if new_quantity != 0 else 0.0
             self.quantity = new_quantity
             log.info(f"[{self.symbol}] Position updated: New Qty={self.quantity:.8f}, Avg Price={self.average_entry_price:.2f}")
        # If reducing or flipping position
        else:
            new_quantity = self.quantity + fill_quantity
            if (self.quantity > 0 and new_quantity < 0) or (self.quantity < 0 and new_quantity > 0):
                log.info(f"[{self.symbol}] Position flipped direction.")
                self.average_entry_price = fill_price # Reset avg price
            elif abs(new_quantity) < 1e-9:
                 log.info(f"[{self.symbol}] Position closed by reduction.")
                 self.quantity = 0.0 # Ensure exactly zero
                 self.average_entry_price = 0.0
            else:
                log.info(f"[{self.symbol}] Position reduced.")
                # Keep old average_entry_price
            self.quantity = new_quantity
            log.info(f"[{self.symbol}] Position updated: New Qty={self.quantity:.8f}, Avg Price={self.average_entry_price:.2f}")

        self.last_update_time = timestamp

    def calculate_unrealized_pnl(self, current_price: float) -> Optional[Tuple[float, float]]:
        """Calculates the unrealized profit or loss."""
        if self.quantity == 0 or self.average_entry_price == 0 or math.isnan(current_price) or math.isinf(current_price):
            return None
        pnl_absolute = (current_price - self.average_entry_price) * self.quantity
        initial_value = self.average_entry_price * abs(self.quantity)
        if initial_value == 0:
             pnl_percentage = 0.0
        else:
             pnl_percentage = pnl_absolute / initial_value
        return pnl_absolute, pnl_percentage


class PositionManager:
    """Manages and tracks all open positions across different symbols."""
    def __init__(self, config: AppSettings):
        """Initializes the PositionManager."""
        self.config = config
        self.positions: Dict[str, Position] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = f"{config.app_name or 'hydrobot'}:position:"  # Use default if app_name missing
        self._connect_redis()
        if self.redis_client:
            self._load_positions_from_redis()
        log.info("PositionManager initialized.")
        # ... (rest of PositionManager methods remain the same) ...

    def _connect_redis(self):
        """Establishes connection to the Redis server."""
        if self.config.redis and redis is not None:
            try:
                self.redis_client = redis.Redis(
                    host=self.config.redis.host, port=self.config.redis.port, db=self.config.redis.db,
                    password=self.config.redis.password.get_secret_value() if self.config.redis.password else None,
                    decode_responses=True, socket_timeout=5, socket_connect_timeout=5 )
                self.redis_client.ping()
                log.info(f"Successfully connected to Redis: {self.config.redis.host}:{self.config.redis.port}")
            except redis.exceptions.ConnectionError as e:
                log.error(f"Redis connection failed: {e}.", exc_info=False)
                self.redis_client = None
            except Exception as e:
                log.exception(f"Unexpected error during Redis connection: {e}")
                self.redis_client = None
        else:
             self.redis_client = None
             if redis is None:
                 log.warning("Redis package not installed. Persistence disabled.")

    def _save_position_to_redis(self, position: Position):
        """Saves a single position object to Redis."""
        if not self.redis_client: return
        try:
            key = f"{self.redis_key_prefix}{position.symbol}"
            # Ensure data is serializable (handle NaN/Inf if necessary)
            pos_dict = position.__dict__
            for k, v in pos_dict.items():
                 if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                      log.warning(f"[{position.symbol}] Cannot save NaN/Inf value for '{k}' to Redis. Storing as None.")
                      pos_dict[k] = None # Store as None or string representation
            value = json.dumps(pos_dict)
            self.redis_client.set(key, value)
            log.debug(f"Saved position {position.symbol} to Redis.")
        except Exception as e:
            log.exception(f"Failed to save position {position.symbol} to Redis: {e}")

    def _load_positions_from_redis(self):
        """Loads all positions managed by this instance from Redis on startup."""
        if not self.redis_client: return
        log.info("Attempting to load positions from Redis...")
        loaded_count = 0
        try:
            cursor = '0'
            while cursor != 0:
                cursor, keys = self.redis_client.scan(cursor=cursor, match=f"{self.redis_key_prefix}*", count=100)
                for key in keys:
                    try:
                        symbol = key.replace(self.redis_key_prefix, "")
                        value = self.redis_client.get(key)
                        if value:
                            pos_data = json.loads(value)
                            # Handle potential None values loaded back if NaN was saved
                            for k, v in pos_data.items():
                                 if v is None and k in Position.__annotations__ and Position.__annotations__[k] == float:
                                      pos_data[k] = 0.0 # Restore floats from None (or NaN?)
                            self.positions[symbol] = Position(**pos_data)
                            loaded_count += 1
                            log.debug(f"Loaded position {symbol} from Redis.")
                        else:
                             log.warning(f"Redis key {key} has no value.")
                    except json.JSONDecodeError:
                        log.error(f"Failed to decode JSON for Redis key {key}.")
                    except Exception as e:
                        log.exception(f"Failed to load/parse position for key {key}: {e}")
        except Exception as e:
            log.exception(f"Error scanning/loading positions from Redis: {e}")
        log.info(f"Finished loading from Redis. Loaded {loaded_count} positions.")

    def update_position_on_fill(self, symbol: str, quantity: float, price: float, timestamp: float):
        """Updates the position for a symbol based on an executed trade (fill)."""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        position = self.positions[symbol]
        position.update_position(fill_quantity=quantity, fill_price=price, timestamp=timestamp)
        self._save_position_to_redis(position)

    def get_position(self, symbol: str) -> Optional[Position]:
        """Retrieves the current position object for a given symbol."""
        return self.positions.get(symbol)

    def get_position_size(self, symbol: str) -> float:
        """Gets the quantity of the asset held for a given symbol."""
        position = self.get_position(symbol)
        return position.quantity if position else 0.0

    def get_all_positions(self) -> Dict[str, Position]:
        """Returns a dictionary of all currently managed positions."""
        return self.positions

    def get_total_portfolio_value(self, current_prices: Dict[str, float], quote_currency: str = "USDT") -> float:
        """Calculates the estimated total value of the portfolio (assets only)."""
        total_value = 0.0
        for symbol, position in self.positions.items():
            if position.quantity != 0:
                 current_price = current_prices.get(symbol)
                 if current_price is not None and not math.isnan(current_price) and not math.isinf(current_price):
                      total_value += position.quantity * current_price
                 else:
                      log.warning(f"[{symbol}] Cannot calculate value: Missing or invalid current price.")

        # Placeholder for adding free quote currency balance
        log.debug(f"Calculated portfolio asset value: {total_value:.2f} {quote_currency}")
        return total_value