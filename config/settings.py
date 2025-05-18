# hydrobot2/config/settings.py
# (Keep all the Pydantic models defined above as they were)
# ... (PathSettings, ExchangeAPISettings, etc. - NO CHANGES HERE) ...

import os
from pydantic import BaseModel, Field, SecretStr, validator
from typing import List, Optional, Dict, Any
import yaml
import logging

# Setup basic logger for config loading issues
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# --- Environment and Paths ---
class PathSettings(BaseModel):
    """Defines paths used by the application."""
    log_dir: str = Field("logs", description="Directory to store log files.")
    data_dir: str = Field("data", description="Directory for storing data files (CSV, etc.).")
    model_dir: str = Field("models/saved", description="Directory to save trained models.")
    config_dir: str = Field("config", description="Directory where configuration files are stored.")

# --- Exchange API Configuration ---
class ExchangeAPISettings(BaseModel):
    """Configuration for connecting to a single exchange."""
    name: str = Field(..., description="Name of the exchange (e.g., 'binanceus', 'coinbase').")
    api_key: Optional[SecretStr] = Field(None, description="API Key for the exchange.")
    api_secret: Optional[SecretStr] = Field(None, description="API Secret for the exchange.")
    api_passphrase: Optional[SecretStr] = Field(None, description="API Passphrase (if required, e.g., Coinbase Pro).")
    is_sandbox: bool = Field(False, description="Whether to use the exchange's sandbox/test environment.")
    # Add other exchange-specific parameters if needed, e.g., rate limits

# --- Trading Parameters ---
class TradingSettings(BaseModel):
    """General trading parameters."""
    symbols: List[str] = Field(..., description="List of trading symbols (e.g., ['BTC/USD', 'ETH/USD']).")
    default_order_type: str = Field("limit", description="Default order type ('limit', 'market').")
    default_trade_amount_usd: float = Field(10.0, description="Default amount in USD for trades.")
    max_open_positions: int = Field(3, description="Maximum number of concurrent open positions.")
    slippage_tolerance: float = Field(0.001, description="Allowed slippage percentage (0.1%).") # Example

# --- Risk Management Settings ---
class RiskSettings(BaseModel):
    """Risk management parameters."""
    max_drawdown_pct: float = Field(0.1, description="Maximum allowed portfolio drawdown percentage (10%).")
    max_risk_per_trade_pct: float = Field(0.01, description="Maximum percentage of portfolio to risk per trade (1%).")
    stop_loss_pct: Optional[float] = Field(0.02, description="Default stop loss percentage (2%). Set to None to disable.")
    take_profit_pct: Optional[float] = Field(0.04, description="Default take profit percentage (4%). Set to None to disable.")

# --- Scalping Strategy Specific Settings ---
class ScalpingStrategySettings(BaseModel):
    """Parameters specific to the Scalping strategy."""
    min_spread_pct: float = Field(0.001, description="Minimum bid-ask spread percentage required to consider a trade.")
    min_imbalance: float = Field(1.5, description="Minimum order book imbalance ratio required.")
    lookback_period: int = Field(60, description="Lookback period (e.g., in seconds or ticks) for calculations.")
    min_profit_target_pct: float = Field(0.0005, description="Minimum profit target percentage for a scalp (0.05%).")
    max_position_size_usd: float = Field(100.0, description="Maximum size of a single position in USD.")
    confidence_threshold: Optional[float] = Field(0.6, description="Minimum model confidence score needed to trade (if model is used).")

# --- Strategy Manager Settings ---
class StrategyManagerSettings(BaseModel):
    """Settings for how strategies are selected and managed."""
    regime_mapping: Dict[str, str] = Field(
        default_factory=lambda: {"default": "ScalpingStrategy"}, # Default to Scalping for now
        description="Mapping from market regime name to Strategy class name."
    )

# --- Model Inference Settings ---
class ModelInferenceSettings(BaseModel):
    """Settings for loading and using prediction models."""
    prediction_model_path: Optional[str] = Field(None, description="Path to the trained prediction model file.")
    regime_model_path: Optional[str] = Field(None, description="Path to the trained market regime model file.")
    use_gpu: bool = Field(False, description="Whether to use GPU for inference if available.")

# --- Redis Settings ---
class RedisSettings(BaseModel):
    """Settings for connecting to Redis."""
    host: str = Field("localhost", description="Redis server host.")
    port: int = Field(6379, description="Redis server port.")
    db: int = Field(0, description="Redis database number.")
    password: Optional[SecretStr] = Field(None, description="Redis password (if required).")

# --- Main Application Settings ---
class AppSettings(BaseModel):
    """Root configuration model bringing all settings together."""
    app_name: str = Field("HydroBot2", description="Name of the application.")
    environment: str = Field("development", description="Runtime environment (e.g., 'development', 'production').")
    log_level: str = Field("INFO", description="Logging level (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR').")

    paths: PathSettings = Field(default_factory=PathSettings)
    exchange: ExchangeAPISettings # Expecting one primary exchange for now
    trading: TradingSettings = Field(default_factory=TradingSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    strategy_manager: StrategyManagerSettings = Field(default_factory=StrategyManagerSettings)
    scalping_strategy: ScalpingStrategySettings = Field(default_factory=ScalpingStrategySettings)
    model_inference: Optional[ModelInferenceSettings] = Field(default_factory=ModelInferenceSettings) # Optional for now
    redis: RedisSettings = Field(default_factory=RedisSettings)

    @validator('log_level', pre=True, allow_reuse=True)
    def log_level_to_upper(cls, v):
        return v.upper()

    @validator('environment', pre=True, allow_reuse=True)
    def environment_to_lower(cls, v):
        return v.lower()

# --- Loading Function ---
def load_config(config_file: str = "config/config.yaml", secrets_file: Optional[str] = None) -> AppSettings:
    """
    Loads configuration from YAML files and environment variables.

    Args:
        config_file: Path to the main configuration YAML file.
        secrets_file: Optional path to a secrets YAML file (for API keys, etc.).

    Returns:
        An AppSettings object populated with configuration values.
    """
    config_data = {}
    if os.path.exists(config_file):
        log.info(f"Loading configuration from: {config_file}")
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f) or {}
    else:
        log.warning(f"Configuration file not found: {config_file}. Using defaults.")

    # Ensure base structure exists before trying to merge secrets
    if 'exchange' not in config_data: config_data['exchange'] = {}
    if 'redis' not in config_data: config_data['redis'] = {}

    if secrets_file and os.path.exists(secrets_file):
        log.info(f"Loading secrets from: {secrets_file}")
        with open(secrets_file, 'r') as f:
            secrets_data = yaml.safe_load(f) or {}
            # --- Start FIX ---
            # Safely merge secrets only if the section exists in secrets_data
            if 'exchange' in secrets_data and isinstance(secrets_data['exchange'], dict):
                 config_data['exchange'].update(secrets_data['exchange'])
                 log.debug("Merged 'exchange' secrets.")
            elif 'exchange' in secrets_data:
                 log.warning(f"Skipping merge for 'exchange' secrets: Expected a dictionary, found {type(secrets_data['exchange'])}.")

            if 'redis' in secrets_data and isinstance(secrets_data['redis'], dict):
                config_data['redis'].update(secrets_data['redis'])
                log.debug("Merged 'redis' secrets.")
            elif 'redis' in secrets_data:
                 log.warning(f"Skipping merge for 'redis' secrets: Expected a dictionary, found {type(secrets_data['redis'])}.")
            # --- End FIX ---

            # Add other potential secret sections here with similar checks
    elif secrets_file:
         log.warning(f"Secrets file specified but not found: {secrets_file}")


    # --- Environment Variable Overrides ---
    redis_host_env = os.getenv("REDIS_HOST")
    if redis_host_env:
        log.info("Overriding Redis host from environment variable REDIS_HOST.")
        config_data['redis']['host'] = redis_host_env # Assumes redis dict exists

    api_key_env = os.getenv("EXCHANGE_API_KEY")
    if api_key_env:
        log.info("Overriding Exchange API key from environment variable EXCHANGE_API_KEY.")
        config_data['exchange']['api_key'] = api_key_env # Assumes exchange dict exists

    # ... (rest of the overrides)

    try:
        settings = AppSettings(**config_data)
        os.makedirs(settings.paths.log_dir, exist_ok=True)
        os.makedirs(settings.paths.data_dir, exist_ok=True)
        os.makedirs(settings.paths.model_dir, exist_ok=True)
        return settings
    except Exception as e:
        log.exception(f"Error loading or validating configuration: {e}")
        raise

# --- Global Configuration Instance ---
# ... (Keep the logic below load_config as it was) ...
# Load config when the module is imported...
try:
    _default_config_path = "config.yaml" # Look in CWD (project root) first
    _default_secrets_path = "secrets.yaml" # Look in CWD (project root) first

    if os.path.exists(_default_config_path):
         CONFIG = load_config(config_file=_default_config_path, secrets_file=_default_secrets_path)
    else:
        # Fallback if config not in CWD - maybe hydrobot2 is the CWD? Unlikely.
        # Let's assume config.yaml MUST be in the root where main.py is run.
        log.error(f"Could not find configuration file at '{_default_config_path}'. Please ensure config.yaml is in the project root directory.")
        CONFIG = None # Indicate failure to load
        raise FileNotFoundError(f"Configuration file '{_default_config_path}' not found.")


except Exception as e:
    log.exception("Failed to initialize configuration during module import.")
    CONFIG = None

# --- Helper function to get config ---
def get_config() -> AppSettings:
    """Returns the globally loaded configuration object."""
    if CONFIG is None:
        log.critical("Configuration accessed before it was successfully loaded or loading failed!")
        # Attempting to reload might hide the original error. Better to raise.
        raise RuntimeError("Configuration could not be loaded. Check logs for details.")
    return CONFIG