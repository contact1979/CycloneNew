"""Utility helpers for order formatting and validation."""

import math
from decimal import Decimal, ROUND_DOWN, ROUND_UP # Use Decimal for precision
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - avoid runtime dependency during tests
    import ccxt.async_support as ccxt

# --- FIX: Use relative import ---
from ..utils.logger_setup import get_logger

log = get_logger()

_market_cache: Dict[str, Dict[str, Any]] = {}

async def update_market_cache(exchange: "ccxt.Exchange"):
    """Fetches and caches market information from the exchange."""
    global _market_cache
    # Import ccxt only when this function is invoked to avoid heavy dependency
    import ccxt.async_support as ccxt
    if not exchange or not exchange.markets: # Check if markets loaded
        try:
             if not exchange: raise ValueError("Exchange object is None")
             log.info(f"Markets not loaded for {exchange.id}. Attempting load...")
             await exchange.load_markets()
             log.info("Markets loaded.")
        except Exception as e:
             log.error(f"Failed to load markets for cache update: {e}")
             return # Cannot proceed without markets

    _market_cache = exchange.markets
    log.info(f"Market cache updated for {exchange.id}. {len(_market_cache)} markets.")

def get_market_info(symbol: str) -> Optional[Dict[str, Any]]:
    """Retrieves cached market information for a specific symbol."""
    if not _market_cache:
        log.warning("Market cache is empty. Call update_market_cache first.")
        return None
    market = _market_cache.get(symbol)
    if not market:
        # Try variations? e.g. BTC/USD vs BTC-USD
        # log.warning(f"Market info not found in cache for symbol: {symbol}")
        pass # Reduce noise, check will happen in calling functions
    return market

# --- Precision and Formatting ---

def format_quantity(symbol: str, quantity: float) -> Optional[float]:
    """Formats the order quantity according to exchange precision rules (rounds DOWN)."""
    market = get_market_info(symbol)
    # Ensure quantity is valid number first
    if math.isnan(quantity) or math.isinf(quantity):
        log.error(f"[{symbol}] Invalid quantity for formatting: {quantity}")
        return None

    precision_amount = market.get('precision', {}).get('amount') if market else None
    if precision_amount is None:
        log.debug(f"[{symbol}] No amount precision found. Using original qty: {quantity}")
        return quantity # Return original if info missing

    try:
        # Use Decimal for accuracy
        quantity_dec = Decimal(str(quantity))
        if isinstance(precision_amount, int): # Decimal places
             decimal_places = precision_amount
             quantizer = Decimal('1e-' + str(decimal_places))
             formatted_qty = float(quantity_dec.quantize(quantizer, rounding=ROUND_DOWN))
             log.debug(f"[{symbol}] Qty {quantity} -> {formatted_qty} (DP: {decimal_places})")
             return formatted_qty
        elif isinstance(precision_amount, float): # Step size
             step_size = Decimal(str(precision_amount))
             if step_size == 0: return float(quantity_dec) # Avoid division by zero
             formatted_qty = float( (quantity_dec // step_size) * step_size )
             log.debug(f"[{symbol}] Qty {quantity} -> {formatted_qty} (Step: {step_size})")
             return formatted_qty
        else:
             log.warning(f"[{symbol}] Unknown amount precision format: {precision_amount}. Using original.")
             return quantity
    except Exception as e:
        log.exception(f"[{symbol}] Error formatting quantity {quantity}: {e}")
        return None

def format_price(symbol: str, price: float) -> Optional[float]:
    """Formats the order price according to exchange precision rules."""
    market = get_market_info(symbol)
    # Ensure price is valid number
    if math.isnan(price) or math.isinf(price):
        log.error(f"[{symbol}] Invalid price for formatting: {price}")
        return None

    precision_price = market.get('precision', {}).get('price') if market else None
    if precision_price is None:
        log.debug(f"[{symbol}] No price precision found. Using original price: {price}")
        return price

    try:
        price_dec = Decimal(str(price))
        if isinstance(precision_price, int): # Decimal places
            step_size = Decimal('1e-' + str(precision_price))
            # Round to nearest step
            formatted_price = float( round(price_dec / step_size) * step_size )
            log.debug(f"[{symbol}] Price {price} -> {formatted_price} (DP: {precision_price})")
            return formatted_price
        elif isinstance(precision_price, float): # Step size
            step_size = Decimal(str(precision_price))
            if step_size == 0: return float(price_dec)
            formatted_price = float( round(price_dec / step_size) * step_size )
            log.debug(f"[{symbol}] Price {price} -> {formatted_price} (Step: {step_size})")
            return formatted_price
        else:
            log.warning(f"[{symbol}] Unknown price precision format: {precision_price}. Using original.")
            return price
    except Exception as e:
        log.exception(f"[{symbol}] Error formatting price {price}: {e}")
        return None

# --- Order Validation Helpers ---

def check_min_order_size(symbol: str, quantity: float, price: Optional[float] = None) -> bool:
    """Checks if the order meets minimum amount (base) and cost (quote) requirements."""
    market = get_market_info(symbol)
    if not market:
        log.warning(f"[{symbol}] Limits info not found. Assuming OK.")
        return True
    # Ensure inputs are valid
    if math.isnan(quantity) or math.isinf(quantity) or \
       (price is not None and (math.isnan(price) or math.isinf(price))):
         log.error(f"[{symbol}] Invalid inputs for min size check: Qty={quantity}, Price={price}")
         return False

    limits = market.get('limits', {})
    min_amount = limits.get('amount', {}).get('min')
    min_cost = limits.get('cost', {}).get('min')

    # Check min amount (base currency)
    if min_amount is not None and quantity < min_amount:
        log.warning(f"[{symbol}] FAIL Min Size: Qty {quantity} < Min Amount {min_amount}.")
        return False

    # Check min cost (quote currency)
    if min_cost is not None:
        if price is None or price <= 0:
            log.warning(f"[{symbol}] Skipping min cost check: Invalid price {price}.")
        else:
            order_cost = quantity * price
            if order_cost < min_cost:
                log.warning(f"[{symbol}] FAIL Min Size: Cost {order_cost:.4f} < Min Cost {min_cost}.")
                return False

    log.debug(f"[{symbol}] Order Qty {quantity} meets min size checks.")
    return True