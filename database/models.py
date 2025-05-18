"""SQLAlchemy models for HydroBot database."""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    Boolean, ForeignKey, MetaData, Table, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
metadata = MetaData()

class Trade(Base):
    """Records of executed trades."""
    __tablename__ = 'trade_log'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    trade_type = Column(String, nullable=False)  # BUY/SELL
    status = Column(String, nullable=False)
    binance_order_id = Column(String)
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    usd_value = Column(Float, nullable=False)
    fee = Column(Float)
    pnl = Column(Float)
    signal_confidence = Column(Float)
    trigger_reason = Column(String, nullable=False)
    trading_mode = Column(String, nullable=False)  # LIVE/PAPER
    timestamp = Column(DateTime, default=datetime.utcnow)

class Position(Base):
    """Currently open positions."""
    __tablename__ = 'positions'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, unique=True)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float)
    unrealized_pnl = Column(Float)
    last_update = Column(DateTime, default=datetime.utcnow)

class SymbolMetrics(Base):
    """Trading metrics per symbol."""
    __tablename__ = 'symbol_metrics'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, unique=True)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    max_drawdown = Column(Float)
    last_trade_time = Column(DateTime)

class ModelPrediction(Base):
    """ML model predictions and performance tracking."""
    __tablename__ = 'model_predictions'
    
    id = Column(Integer, primary_key=True)
    model_name = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    prediction = Column(Integer, nullable=False)  # 0=SELL, 1=BUY
    confidence = Column(Float, nullable=False)
    features = Column(String)  # JSON string of input features
    was_profitable = Column(Boolean)  # Set after position closes
    actual_pnl = Column(Float)  # Set after position closes

# Create indices
Trade.__table__.append_constraint(
    Index('idx_trade_symbol_time', Trade.symbol, Trade.timestamp)
)
ModelPrediction.__table__.append_constraint(
    Index('idx_pred_symbol_time', ModelPrediction.symbol, ModelPrediction.timestamp)
)