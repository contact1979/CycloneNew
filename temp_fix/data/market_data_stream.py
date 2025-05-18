"""Market data stream processor.

Handles real-time market data aggregation, orderbook management,
and trade feed processing with efficient data structures and async I/O.
"""
import asyncio
import aiohttp
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import numpy as np
from collections import deque
from utilities.logger_setup import get_logger
from utilities.metrics import (
    MARKET_DATA_UPDATES,
    MARKET_DATA_LATENCY,
    SYSTEM_LATENCY
)

logger = get_logger(__name__)

class OrderBook:
    """Real-time order book management."""
    
    def __init__(self, depth: int = 10):
        """Initialize order book.
        
        Args:
            depth: Number of price levels to track
        """
        self.depth = depth
        self.bids: List[List[float]] = []  # [price, amount]
        self.asks: List[List[float]] = []
        self.bid_dict: Dict[float, float] = {}  # price -> amount
        self.ask_dict: Dict[float, float] = {}
        self.timestamp: Optional[datetime] = None
    
    def update(self, bids: List[List[float]], asks: List[List[float]]) -> None:
        """Update order book state.
        
        Args:
            bids: List of [price, amount] bid updates
            asks: List of [price, amount] ask updates
        """
        # Update bids
        for price, amount in bids:
            if amount > 0:
                self.bid_dict[price] = amount
            else:
                self.bid_dict.pop(price, None)
        
        # Update asks
        for price, amount in asks:
            if amount > 0:
                self.ask_dict[price] = amount
            else:
                self.ask_dict.pop(price, None)
        
        # Sort and trim to depth
        self.bids = sorted(
            [[p, a] for p, a in self.bid_dict.items()],
            key=lambda x: x[0],
            reverse=True
        )[:self.depth]
        
        self.asks = sorted(
            [[p, a] for p, a in self.ask_dict.items()],
            key=lambda x: x[0]
        )[:self.depth]
        
        self.timestamp = datetime.utcnow()
    
    def get_mid_price(self) -> Optional[float]:
        """Get current mid price.
        
        Returns:
            Mid price if available
        """
        if self.bids and self.asks:
            return (self.bids[0][0] + self.asks[0][0]) / 2
        return None
    
    def get_spread(self) -> Optional[float]:
        """Get current bid-ask spread.
        
        Returns:
            Spread if available
        """
        if self.bids and self.asks:
            return self.asks[0][0] - self.bids[0][0]
        return None
    
    def get_imbalance(self) -> Optional[float]:
        """Get order book imbalance.
        
        Returns:
            Imbalance metric if available
        """
        if not self.bids or not self.asks:
            return None
        
        bid_vol = sum(amount for _, amount in self.bids)
        ask_vol = sum(amount for _, amount in self.asks)
        total_vol = bid_vol + ask_vol
        
        if total_vol == 0:
            return 0
        
        return (bid_vol - ask_vol) / total_vol

class TradeBuffer:
    """Recent trade history buffer."""
    
    def __init__(self, max_size: int = 1000):
        """Initialize trade buffer.
        
        Args:
            max_size: Maximum number of trades to store
        """
        self.max_size = max_size
        self.trades: deque = deque(maxlen=max_size)
    
    def add_trade(self, trade: Dict[str, Any]) -> None:
        """Add trade to buffer.
        
        Args:
            trade: Trade data
        """
        self.trades.append(trade)
    
    def get_vwap(self, window: int = None) -> Optional[float]:
        """Get volume-weighted average price.
        
        Args:
            window: Optional number of recent trades to consider
        
        Returns:
            VWAP if trades available
        """
        if not self.trades:
            return None
        
        trades = list(self.trades)[-window:] if window else self.trades
        
        volume = sum(t['amount'] for t in trades)
        if volume == 0:
            return None
        
        weighted_sum = sum(t['price'] * t['amount'] for t in trades)
        return weighted_sum / volume
    
    def get_volatility(self, window: int = None) -> Optional[float]:
        """Get price volatility.
        
        Args:
            window: Optional number of recent trades to consider
        
        Returns:
            Volatility if trades available
        """
        if not self.trades:
            return None
        
        trades = list(self.trades)[-window:] if window else self.trades
        prices = [t['price'] for t in trades]
        
        if len(prices) < 2:
            return None
        
        return np.std(prices)

class MarketDataStream:
    """Market data stream processor with async I/O."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize market data stream.
        
        Args:
            config: Stream configuration
        """
        self.config = config
        
        # Data structures
        self.orderbooks: Dict[str, OrderBook] = {}
        self.trade_buffers: Dict[str, TradeBuffer] = {}
        
        # Async session and websockets
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_connections: Dict[str, aiohttp.ClientWebSocketResponse] = {}
        self._running = False
        
        # Callbacks and queues
        self._callbacks: List[Callable] = []
        self._event_queues: Dict[str, asyncio.Queue] = {}
        
        # Configuration
        self.orderbook_depth = config.get('orderbook_levels', 10)
        self.trade_buffer_size = config.get('trade_history_size', 1000)
        self.batch_size = config.get('batch_size', 100)
        self.max_queue_size = config.get('max_queue_size', 10000)
    
    async def initialize(self, symbols: List[str]) -> None:
        """Initialize data streams.
        
        Args:
            symbols: Trading pair symbols
        """
        # Create async session
        self._session = aiohttp.ClientSession()
        
        for symbol in symbols:
            # Initialize data structures
            self.orderbooks[symbol] = OrderBook(self.orderbook_depth)
            self.trade_buffers[symbol] = TradeBuffer(self.trade_buffer_size)
            
            # Create event queue
            self._event_queues[symbol] = asyncio.Queue(
                maxsize=self.max_queue_size
            )
            
            # Start processors
            asyncio.create_task(self._process_events(symbol))
    
    async def _process_events(self, symbol: str) -> None:
        """Process market data events for symbol.
        
        Args:
            symbol: Trading pair symbol
        """
        queue = self._event_queues[symbol]
        
        while self._running:
            try:
                # Get batch of events
                events = []
                try:
                    while len(events) < self.batch_size:
                        event = await asyncio.wait_for(
                            queue.get(),
                            timeout=0.1
                        )
                        events.append(event)
                except asyncio.TimeoutError:
                    pass
                
                if not events:
                    continue
                
                # Process batch with latency tracking
                start_time = datetime.utcnow()
                
                for event in events:
                    event_type = event['type']
                    data = event['data']
                    
                    if event_type == 'orderbook':
                        self.orderbooks[symbol].update(
                            data['bids'],
                            data['asks']
                        )
                        MARKET_DATA_UPDATES.labels(
                            symbol=symbol,
                            type='orderbook'
                        ).inc()
                    
                    elif event_type == 'trade':
                        self.trade_buffers[symbol].add_trade(data)
                        MARKET_DATA_UPDATES.labels(
                            symbol=symbol,
                            type='trade'
                        ).inc()
                
                # Record latency
                latency = (datetime.utcnow() - start_time).total_seconds()
                MARKET_DATA_LATENCY.labels(symbol=symbol).observe(latency)
                
                # Notify callbacks
                market_state = self.get_market_state(symbol)
                for callback in self._callbacks:
                    await callback(market_state)
                
            except Exception as e:
                logger.error("event_processing_error",
                           error=str(e),
                           symbol=symbol)
                await asyncio.sleep(1)
    
    async def _maintain_websocket(self,
                               symbol: str,
                               url: str,
                               subscribe_msg: Dict[str, Any]
                               ) -> None:
        """Maintain websocket connection.
        
        Args:
            symbol: Trading pair symbol
            url: Websocket URL
            subscribe_msg: Subscription message
        """
        while self._running:
            try:
                async with self._session.ws_connect(url) as ws:
                    self._ws_connections[symbol] = ws
                    
                    # Subscribe
                    await ws.send_json(subscribe_msg)
                    
                    # Process messages
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            
                            # Queue event
                            event_queue = self._event_queues[symbol]
                            try:
                                # Non-blocking put with backpressure
                                if not event_queue.full():
                                    await event_queue.put({
                                        'type': 'orderbook' if 'bids' in data else 'trade',
                                        'data': data
                                    })
                                else:
                                    logger.warning("event_queue_full",
                                                symbol=symbol)
                            except Exception as e:
                                logger.error("event_queue_error",
                                         error=str(e),
                                         symbol=symbol)
                        
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error("websocket_error",
                                     error=str(msg.data),
                                     symbol=symbol)
                            break
                
            except Exception as e:
                logger.error("websocket_connection_error",
                           error=str(e),
                           symbol=symbol)
            
            # Remove connection
            self._ws_connections.pop(symbol, None)
            
            if self._running:
                # Wait before reconnecting
                await asyncio.sleep(5)
    
    def register_callback(self,
                        callback: Callable[[Dict[str, Any]], None]
                        ) -> None:
        """Register data update callback.
        
        Args:
            callback: Callback function
        """
        self._callbacks.append(callback)
    
    @SYSTEM_LATENCY.labels(operation='get_market_state').time()
    def get_market_state(self, symbol: str) -> Dict[str, Any]:
        """Get current market state.
        
        Args:
            symbol: Trading pair symbol
        
        Returns:
            Market state snapshot
        """
        orderbook = self.orderbooks.get(symbol)
        trade_buffer = self.trade_buffers.get(symbol)
        
        if not orderbook or not trade_buffer:
            return {}
        
        return {
            'symbol': symbol,
            'timestamp': datetime.utcnow().isoformat(),
            'orderbook': {
                'mid_price': orderbook.get_mid_price(),
                'spread': orderbook.get_spread(),
                'imbalance': orderbook.get_imbalance(),
                'bids': orderbook.bids[:5],  # Top 5 levels
                'asks': orderbook.asks[:5]
            },
            'trades': {
                'vwap': trade_buffer.get_vwap(100),  # Last 100 trades
                'volatility': trade_buffer.get_volatility(100),
                'last_price': trade_buffer.trades[-1]['price']
                if trade_buffer.trades else None
            }
        }
    
    async def start(self) -> None:
        """Start market data streams."""
        self._running = True
    
    async def stop(self) -> None:
        """Stop market data streams."""
        self._running = False
        
        # Close websockets
        for ws in self._ws_connections.values():
            await ws.close()
        
        # Close session
        if self._session:
            await self._session.close()
        
        logger.info("market_data_stream_stopped")