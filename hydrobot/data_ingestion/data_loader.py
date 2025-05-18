"""Data loader for backtesting.

Loads historical market data from CSV/Parquet files and replays them
through the trading strategy for backtesting.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Generator
from datetime import datetime
from pathlib import Path
import pyarrow.parquet as pq
from hydrobot.utils.logger_setup import get_logger

logger = get_logger(__name__)

class HistoricalDataLoader:
    """Historical market data loader for backtesting."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize data loader.
        
        Args:
            config: Loader configuration
        """
        self.config = config
        self.data_path = Path(config['data_path'])
        self._data_cache: Dict[str, pd.DataFrame] = {}
    
    def load_market_data(self,
                       symbol: str,
                       start_time: Optional[datetime] = None,
                       end_time: Optional[datetime] = None
                       ) -> pd.DataFrame:
        """Load historical market data.
        
        Args:
            symbol: Trading pair symbol
            start_time: Optional start time filter
            end_time: Optional end time filter
        
        Returns:
            DataFrame with historical data
        """
        try:
            # Check cache
            if symbol in self._data_cache:
                data = self._data_cache[symbol]
            else:
                # Load from file
                file_path = self.data_path / f"{symbol.replace('/', '_')}.parquet"
                if file_path.exists():
                    data = pq.read_table(file_path).to_pandas()
                else:
                    # Try CSV
                    csv_path = file_path.with_suffix('.csv')
                    data = pd.read_csv(csv_path)
                
                # Parse timestamps
                data['timestamp'] = pd.to_datetime(data['timestamp'])
                data.set_index('timestamp', inplace=True)
                
                # Cache data
                self._data_cache[symbol] = data
            
            # Apply time filters
            if start_time:
                data = data[data.index >= start_time]
            if end_time:
                data = data[data.index <= end_time]
            
            return data
            
        except Exception as e:
            logger.error("data_loading_error",
                        error=str(e),
                        symbol=symbol)
            return pd.DataFrame()
    
    def iterate_market_data(self,
                          symbols: List[str],
                          batch_size: int = 100
                          ) -> Generator[Dict[str, Any], None, None]:
        """Iterate through historical data in batches.
        
        Args:
            symbols: List of trading pair symbols
            batch_size: Number of ticks per batch
        
        Yields:
            Dict containing market data batch
        """
        # Load all symbol data
        dfs = {
            symbol: self.load_market_data(symbol)
            for symbol in symbols
        }
        
        # Get common time index
        common_idx = pd.concat([pd.Series(df.index) for df in dfs.values()]).unique()
        common_idx.sort_values()
        
        # Iterate through batches
        for i in range(0, len(common_idx), batch_size):
            batch_idx = common_idx[i:i + batch_size]
            
            # Build market data batch
            batch = {}
            for symbol, df in dfs.items():
                symbol_data = df[df.index.isin(batch_idx)]
                
                batch[symbol] = {
                    'orderbook': {
                        'bids': symbol_data[['bid_price', 'bid_size']].values.tolist(),
                        'asks': symbol_data[['ask_price', 'ask_size']].values.tolist()
                    },
                    'trades': [{
                        'timestamp': pd.Timestamp(str(idx)).isoformat(),
                        'price': row['price'],
                        'amount': row['amount'],
                        'side': row['side']
                    } for idx, row in symbol_data.iterrows()],
                    'timestamp': batch_idx[-1].isoformat()
                }
            
            yield batch