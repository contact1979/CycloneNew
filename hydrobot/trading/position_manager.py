# hydrobot/trading/position_manager.py

import json
import time
import math # For isnan
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any, TYPE_CHECKING, Any

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover
    redis = None

# --- FIX: Use relative imports ---
from ..utils.logger_setup import get_logger

if TYPE_CHECKING:
    from ..config.settings import AppSettings

log = get_logger()

@dataclass
class Position:
    """Represents the bot's position in a single trading symbol."""
    symbol: str
    size: float = 0.0  # Changed from quantity for test compatibility
    entry_price: float = 0.0  # Changed from average_entry_price for test compatibility
    current_price: float = 0.0  # Added for test compatibility
    quantity: float = 0.0  # Keep for backward compatibility
    average_entry_price: float = 0.0  # Keep for backward compatibility
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
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

    def __init__(self, config: "AppSettings | Dict[str, Any]"):
        """Initializes the PositionManager."""
        self.config = config
        self.positions: Dict[str, Position] = {}
        self.redis_client: Optional[redis.Redis] = None
        app_name = config.get("app_name") if isinstance(config, dict) else getattr(config, "app_name", None)
        self.redis_key_prefix = f"{app_name or 'hydrobot'}:position:"
        self._connect_redis()
        if self.redis_client:
            self._load_positions_from_redis()
        log.info("PositionManager initialized.")

    def initialize_symbol(self, symbol: str) -> None:
        """Ensure a symbol entry exists."""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)

    def update_position(self, symbol: str, trade: Dict[str, Any], mark_price: float) -> Position:
        """Update position based on a trade and return updated position."""
        self.initialize_symbol(symbol)
        position = self.positions[symbol]

        side = trade.get("side", "").lower()
        size = float(trade.get("size", 0))
        price = float(trade.get("price", 0))
        ts = trade.get("timestamp")
        timestamp = ts.timestamp() if hasattr(ts, "timestamp") else float(ts)

        if side == "buy":
            new_size = position.size + size
            position.entry_price = (
                (position.size * position.entry_price + size * price) / new_size
            ) if new_size != 0 else 0.0
            position.size = new_size
        elif side == "sell":
            close_size = min(size, position.size)
            position.realized_pnl += (price - position.entry_price) * close_size
            position.size -= close_size
            if position.size == 0:
                position.entry_price = 0.0

        position.quantity = position.size
        position.average_entry_price = position.entry_price
        position.unrealized_pnl = (
            (mark_price - position.entry_price) * position.size if position.size != 0 else 0.0
        )
        position.total_pnl = position.realized_pnl + position.unrealized_pnl
        position.last_update_time = timestamp

        if self.redis_client:
            self._save_position_to_redis(position)
        return position

    def _connect_redis(self):
        """Establishes connection to the Redis server if configuration is provided."""
        redis_cfg = None
        if isinstance(self.config, dict):
            redis_cfg = self.config.get("redis")
        else:
            redis_cfg = getattr(self.config, "redis", None)

        if redis_cfg and redis is not None:
            try:
                host = redis_cfg.get("host") if isinstance(redis_cfg, dict) else redis_cfg.host
                port = redis_cfg.get("port", 6379) if isinstance(redis_cfg, dict) else redis_cfg.port
                db = redis_cfg.get("db", 0) if isinstance(redis_cfg, dict) else redis_cfg.db
                password = None
                if isinstance(redis_cfg, dict):
                    password = redis_cfg.get("password")
                else:
                    if getattr(redis_cfg, "password", None):
                        password = redis_cfg.password.get_secret_value()

                self.redis_client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
                self.redis_client.ping()
                log.info(f"Successfully connected to Redis: {host}:{port}")
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
    
    def update_position(self, symbol: str, trade: Dict[str, Any], current_price: float) -> Position:
        """Updates position based on a trade dictionary and current market price.
        Compatible with the test_position_manager test."""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
            
        # Extract trade details
        quantity = trade.get("size", 0.0)
        price = trade.get("price", 0.0)
        timestamp = trade.get("timestamp", datetime.utcnow()).timestamp() \
            if isinstance(trade.get("timestamp"), datetime) else trade.get("timestamp", time.time())
        
        # Handle buy/sell direction
        side = trade.get("side", "").lower()
        if side == "sell":
            quantity = -abs(quantity)  # Ensure negative for sells
        else:  # Default to buy
            quantity = abs(quantity)  # Ensure positive for buys
            
        # Update the position
        self.update_position_on_fill(symbol, quantity, price, timestamp)
        
        # Update current price for display/calculations
        position = self.positions[symbol]
        position.current_price = current_price
        
        return position

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
