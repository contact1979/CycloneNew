"""Data provider for the dashboard with real-time Redis updates."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from collections import deque
import pandas as pd
from hydrobot.config.settings import settings
from hydrobot.utils.redis_utils import RedisSubscriber
from hydrobot.utils.logger_setup import get_logger

log = get_logger(__name__)

class DashboardDataProvider:
    """Manages data for the dashboard, including real-time updates via Redis."""
    
    def __init__(self, max_history: int = 1000):
        """Initialize data provider.
        
        Args:
            max_history: Maximum number of historical data points to keep
        """
        self.max_history = max_history
        self._subscriber = RedisSubscriber()
        
        # Data storage
        self._trade_history = deque(maxlen=max_history)
        self._portfolio_updates = deque(maxlen=max_history)
        self._strategy_states = {}
        self._system_events = deque(maxlen=max_history)
        
        # Latest state
        self._latest_portfolio_value = 0.0
        self._latest_pnl = 0.0
        self._active_positions: Dict[str, Dict[str, Any]] = {}
        self._last_update = datetime.utcnow()
        
        # Connection state
        self._connected = False
        self._connection_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the data provider and Redis subscriber."""
        if not self._connected:
            try:
                # Connect to Redis and subscribe to channels
                if await self._subscriber.connect():
                    await self._subscriber.subscribe(
                        settings.redis.channels.trade_updates,
                        self._handle_trade_update
                    )
                    await self._subscriber.subscribe(
                        settings.redis.channels.portfolio_updates,
                        self._handle_portfolio_update
                    )
                    await self._subscriber.subscribe(
                        settings.redis.channels.strategy_updates,
                        self._handle_strategy_update
                    )
                    await self._subscriber.subscribe(
                        settings.redis.channels.system_events,
                        self._handle_system_event
                    )
                    await self._subscriber.start()
                    self._connected = True
                    log.info("Dashboard data provider started")
                else:
                    log.error("Failed to connect to Redis")
            except Exception as e:
                log.error(f"Error starting data provider: {e}")

    async def stop(self) -> None:
        """Stop the data provider and Redis subscriber."""
        if self._connected:
            await self._subscriber.stop()
            await self._subscriber.disconnect()
            self._connected = False
            log.info("Dashboard data provider stopped")

    def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """Handle trade update messages.
        
        Args:
            data: Trade update data including trade details
        """
        try:
            # Add timestamp if not present
            if 'timestamp' not in data:
                data['timestamp'] = datetime.utcnow().isoformat()
            
            # Store trade history
            self._trade_history.append(data)
            
            # Update active positions
            symbol = data.get('symbol')
            if symbol and data.get('trade_type') in ['BUY', 'SELL']:
                if data['trade_type'] == 'BUY':
                    self._active_positions[symbol] = {
                        'entry_price': data['price'],
                        'quantity': data['quantity'],
                        'entry_time': data['timestamp']
                    }
                elif data['trade_type'] == 'SELL':
                    self._active_positions.pop(symbol, None)
            
            self._last_update = datetime.utcnow()
        except Exception as e:
            log.error(f"Error handling trade update: {e}")

    def _handle_portfolio_update(self, data: Dict[str, Any]) -> None:
        """Handle portfolio update messages.
        
        Args:
            data: Portfolio update data including value and PnL
        """
        try:
            # Add timestamp if not present
            if 'timestamp' not in data:
                data['timestamp'] = datetime.utcnow().isoformat()
            
            # Store portfolio history
            self._portfolio_updates.append(data)
            
            # Update latest values
            self._latest_portfolio_value = data.get('total_value', self._latest_portfolio_value)
            self._latest_pnl = data.get('unrealized_pnl', self._latest_pnl)
            
            self._last_update = datetime.utcnow()
        except Exception as e:
            log.error(f"Error handling portfolio update: {e}")

    def _handle_strategy_update(self, data: Dict[str, Any]) -> None:
        """Handle strategy update messages.
        
        Args:
            data: Strategy update data including state changes
        """
        try:
            strategy_name = data.get('strategy')
            if strategy_name:
                self._strategy_states[strategy_name] = {
                    'state': data.get('state'),
                    'timestamp': data.get('timestamp', datetime.utcnow().isoformat()),
                    'details': data.get('details', {})
                }
            self._last_update = datetime.utcnow()
        except Exception as e:
            log.error(f"Error handling strategy update: {e}")

    def _handle_system_event(self, data: Dict[str, Any]) -> None:
        """Handle system event messages.
        
        Args:
            data: System event data including errors and warnings
        """
        try:
            # Add timestamp if not present
            if 'timestamp' not in data:
                data['timestamp'] = datetime.utcnow().isoformat()
            
            # Store system event
            self._system_events.append(data)
            self._last_update = datetime.utcnow()
        except Exception as e:
            log.error(f"Error handling system event: {e}")

    def get_trade_history(self, minutes: Optional[int] = None) -> pd.DataFrame:
        """Get trade history as a DataFrame.
        
        Args:
            minutes: Optional time window in minutes to filter data
        
        Returns:
            DataFrame containing trade history
        """
        df = pd.DataFrame(self._trade_history)
        if df.empty:
            return df
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        if minutes:
            cutoff = datetime.utcnow() - timedelta(minutes=minutes)
            df = df[df.index >= cutoff]
        
        return df

    def get_portfolio_history(self, minutes: Optional[int] = None) -> pd.DataFrame:
        """Get portfolio value history as a DataFrame.
        
        Args:
            minutes: Optional time window in minutes to filter data
        
        Returns:
            DataFrame containing portfolio history
        """
        df = pd.DataFrame(self._portfolio_updates)
        if df.empty:
            return df
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        if minutes:
            cutoff = datetime.utcnow() - timedelta(minutes=minutes)
            df = df[df.index >= cutoff]
        
        return df

    def get_active_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get currently active positions.
        
        Returns:
            Dictionary of active positions by symbol
        """
        return self._active_positions.copy()

    def get_strategy_states(self) -> Dict[str, Dict[str, Any]]:
        """Get current strategy states.
        
        Returns:
            Dictionary of strategy states by strategy name
        """
        return self._strategy_states.copy()

    def get_recent_events(self, count: int = 10) -> list:
        """Get recent system events.
        
        Args:
            count: Number of recent events to return
        
        Returns:
            List of recent system events
        """
        return list(self._system_events)[-count:]

    @property
    def last_update(self) -> datetime:
        """Get timestamp of last data update.
        
        Returns:
            Datetime of last update
        """
        return self._last_update

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis.
        
        Returns:
            True if connected, False otherwise
        """
        return self._connected

# Global instance for use across dashboard components
dashboard_data = DashboardDataProvider()

