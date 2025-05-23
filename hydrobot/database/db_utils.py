"""Database utilities for HydroBot."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from hydrobot.config.settings import settings
from hydrobot.database.models import (
    Base,
    ModelPrediction,
    Position,
    SymbolMetrics,
    Trade,
)
from hydrobot.utils.logger_setup import get_logger

log = get_logger(__name__)

# Create database engine and session factory
engine = create_engine(
    settings.database.URL, echo=settings.database.ECHO, pool_pre_ping=True
)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Initialize database schema."""
    try:
        Base.metadata.create_all(bind=engine)
        log.info("Database initialized")
    except SQLAlchemyError as e:
        log.error("Database initialization failed", error=str(e))
        raise


def get_session() -> Session:
    """Get a database session.

    Returns:
        SQLAlchemy session
    """
    return SessionLocal()


def bulk_insert_data(records: List[Dict[str, Any]], model: Any) -> bool:
    """Insert multiple records into database.

    Args:
        records: List of dictionaries containing record data
        model: SQLAlchemy model class

    Returns:
        True if successful
    """
    try:
        with get_session() as session:
            session.bulk_insert_mappings(model, records)
            session.commit()
        return True
    except SQLAlchemyError as e:
        log.error("Bulk insert failed", error=str(e))
        return False


def get_open_positions() -> List[Dict[str, Any]]:
    """Get currently open positions.

    Returns:
        List of position dictionaries
    """
    try:
        with get_session() as session:
            positions = session.query(Position).all()
            return [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "last_update": p.last_update.isoformat(),
                }
                for p in positions
            ]
    except SQLAlchemyError as e:
        log.error("Failed to get positions", error=str(e))
        return []


def update_position(
    symbol: str, quantity: float, price: float, pnl: Optional[float] = None
) -> bool:
    """Update or create position record.

    Args:
        symbol: Trading pair symbol
        quantity: Position size
        price: Current price
        pnl: Optional unrealized PnL

    Returns:
        True if successful
    """
    try:
        with get_session() as session:
            position = session.query(Position).filter_by(symbol=symbol).first()

            if position:
                position.quantity = quantity
                position.current_price = price
                if pnl is not None:
                    position.unrealized_pnl = pnl
                position.last_update = datetime.utcnow()
            else:
                position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=price,
                    current_price=price,
                    unrealized_pnl=0.0,
                )
                session.add(position)

            session.commit()
            return True

    except SQLAlchemyError as e:
        log.error("Position update failed", error=str(e))
        return False


def log_model_prediction(
    model_name: str,
    symbol: str,
    prediction: int,
    confidence: float,
    features: Dict[str, Any],
) -> bool:
    """Log model prediction for later analysis.

    Args:
        model_name: Name of ML model
        symbol: Trading pair symbol
        prediction: Model prediction (0=SELL, 1=BUY)
        confidence: Prediction confidence score
        features: Input features used

    Returns:
        True if successful
    """
    try:
        with get_session() as session:
            pred = ModelPrediction(
                model_name=model_name,
                symbol=symbol,
                timestamp=datetime.utcnow(),
                prediction=prediction,
                confidence=confidence,
                features=json.dumps(features),
            )
            session.add(pred)
            session.commit()
            return True

    except SQLAlchemyError as e:
        log.error("Failed to log prediction", error=str(e))
        return False


def update_symbol_metrics(
    symbol: str, trade_won: bool, pnl: float, drawdown: Optional[float] = None
) -> bool:
    """Update trading metrics for symbol.

    Args:
        symbol: Trading pair symbol
        trade_won: Whether trade was profitable
        pnl: Realized profit/loss
        drawdown: Optional maximum drawdown

    Returns:
        True if successful
    """
    try:
        with get_session() as session:
            metrics = session.query(SymbolMetrics).filter_by(symbol=symbol).first()

            if not metrics:
                metrics = SymbolMetrics(symbol=symbol)
                session.add(metrics)

            metrics.total_trades += 1
            if trade_won:
                metrics.winning_trades += 1
            metrics.total_pnl += pnl

            if drawdown is not None:
                metrics.max_drawdown = min(
                    metrics.max_drawdown or float("inf"), drawdown
                )

            metrics.last_trade_time = datetime.utcnow()
            session.commit()
            return True

    except SQLAlchemyError as e:
        log.error("Failed to update metrics", error=str(e))
        return False
