# hydrobot/strategies/strategy_manager.py

import importlib
import pkgutil
import inspect
from typing import Dict, Type, Optional, Any

# --- FIX: Use relative imports ---
# Import the base class and specific strategies to ensure they are recognized
from .base_strategy import Strategy
from .impl_scalping import ScalpingStrategy
# If you add more strategies, import their classes here as well:
# from .impl_momentum import MomentumStrategy
# from .impl_mean_reversion import MeanReversionStrategy

from ..config.settings import get_config, AppSettings, StrategyManagerSettings
from ..utils.logger_setup import get_logger

log = get_logger()

class StrategyManager:
    """
    Manages the loading, selection, and instantiation of trading strategies.
    """
    def __init__(self, config: AppSettings):
        """Initializes the StrategyManager."""
        self.global_config = config
        self.manager_config: StrategyManagerSettings = config.strategy_manager
        self.available_strategies: Dict[str, Type[Strategy]] = self._discover_strategies()
        self.active_strategy_instances: Dict[str, Strategy] = {}
        log.info("StrategyManager initialized.")
        log.info(f"Available strategy classes found: {list(self.available_strategies.keys())}")
        log.info(f"Regime to Strategy mapping: {self.manager_config.regime_mapping}")

    def _discover_strategies(self) -> Dict[str, Type[Strategy]]:
        """Dynamically discovers all Strategy subclasses within the 'strategies' module."""
        strategies = {}
        # Use relative path '.' to refer to the current package (strategies)
        package_path = [os.path.dirname(__file__)]
        prefix = self.__module__.split('.')[0] + '.strategies.'  # Assumes hydrobot.strategies...

        for importer, modname, ispkg in pkgutil.iter_modules(package_path, prefix):
            try:
                module = importlib.import_module(modname)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, Strategy) and obj is not Strategy:
                        log.debug(f"Discovered Strategy class: {name} in module {modname}")
                        if name in strategies:
                             log.warning(f"Duplicate strategy class name '{name}' found.")
                        strategies[name] = obj
            except Exception as e:
                log.error(f"Failed to import or inspect module {modname}: {e}", exc_info=True)

        # Ensure explicitly imported strategies are included
        if "ScalpingStrategy" not in strategies and ScalpingStrategy:
             strategies["ScalpingStrategy"] = ScalpingStrategy
             log.debug("Explicitly added ScalpingStrategy.")

        if not strategies:
             log.warning("No strategy classes were automatically discovered!")
        return strategies

    # ... (rest of StrategyManager remains the same) ...

    def _get_strategy_class_for_regime(self, regime: str = "default") -> Optional[Type[Strategy]]:
        """Finds the strategy class mapped to a given market regime name."""
        strategy_name = self.manager_config.regime_mapping.get(regime)
        if not strategy_name:
            strategy_name = self.manager_config.regime_mapping.get("default")
            if not strategy_name:
                log.error(f"No strategy mapping found for regime '{regime}' or 'default'.")
                return None

        strategy_class = self.available_strategies.get(strategy_name)
        if not strategy_class:
            log.error(f"Strategy class '{strategy_name}' not found in {list(self.available_strategies.keys())}")
            return None
        return strategy_class

    def _get_strategy_config(self, strategy_class_name: str) -> Optional[Dict[str, Any]]:
         """Retrieves the specific configuration section for a given strategy name."""
         config_key = strategy_class_name[0].lower() + strategy_class_name[1:].replace("Strategy", "_strategy")
         if hasattr(self.global_config, config_key):
              strategy_conf = getattr(self.global_config, config_key)
              log.debug(f"Found config for '{strategy_class_name}' under key '{config_key}'.")
              return strategy_conf
         else:
              log.warning(f"No specific config found for '{strategy_class_name}' (key: '{config_key}').")
              return None

    def get_strategy_for_symbol(self, symbol: str, market_regime: str = "default") -> Optional[Strategy]:
        """Gets or creates the active strategy instance for a given symbol and market regime."""
        required_strategy_class = self._get_strategy_class_for_regime(market_regime)
        if not required_strategy_class:
            log.error(f"[{symbol}] Could not determine strategy class for regime '{market_regime}'.")
            return None

        required_strategy_name = required_strategy_class.__name__
        existing_instance = self.active_strategy_instances.get(symbol)

        if existing_instance and isinstance(existing_instance, required_strategy_class):
            log.debug(f"[{symbol}] Using existing '{required_strategy_name}' instance.")
            return existing_instance
        elif existing_instance:
             log.info(f"[{symbol}] Regime changed. Replacing '{existing_instance.get_name()}' with '{required_strategy_name}'.")

        log.info(f"[{symbol}] Creating new instance of '{required_strategy_name}'.")
        strategy_config_data = self._get_strategy_config(required_strategy_name)

        if strategy_config_data is None:
             log.warning(f"[{symbol}] No specific config for {required_strategy_name}. Using defaults.")
             strategy_config_data = {} # Pass empty dict

        try:
            new_instance = required_strategy_class(strategy_config=strategy_config_data, global_config=self.global_config)
            new_instance.set_symbol(symbol)
            self.active_strategy_instances[symbol] = new_instance
            return new_instance
        except Exception as e:
            log.exception(f"[{symbol}] Failed to instantiate strategy '{required_strategy_name}': {e}")
            return None

    def update_strategy_parameters(self, symbol: str, new_params: Dict[str, Any]):
        """Updates parameters for the currently active strategy for a given symbol."""
        strategy_instance = self.active_strategy_instances.get(symbol)
        if strategy_instance:
            log.info(f"[{symbol}] Requesting parameter update for '{strategy_instance.get_name()}'.")
            strategy_instance.update_parameters(new_params)
        else:
            log.warning(f"[{symbol}] Cannot update parameters: No active strategy.")