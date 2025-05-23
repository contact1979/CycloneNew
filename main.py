import asyncio
import os
import signal
import sys
from typing import Optional

# Core imports
from hydrobot.config.settings import AppSettings, get_config
from hydrobot.strategies.strategy_manager import StrategyManager
from hydrobot.trader import TradingManager
from hydrobot.trading.order_executor import OrderExecutor
from hydrobot.trading.position_manager import PositionManager
from hydrobot.trading.risk_controller import RiskController
from hydrobot.utils.logger_setup import get_logger

# Placeholder for data stream:
# from data.market_data_stream import MarketDataStream

# Ensure the project root is in the Python path if running main.py directly
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

log = get_logger()  # Get the logger instance

# --- Global Variable for App State ---
# Used by signal handler to trigger shutdown
shutdown_event = asyncio.Event()


# --- Signal Handler ---
def handle_shutdown_signal(sig, frame):
    """Handles OS signals like SIGINT (Ctrl+C) and SIGTERM."""
    log.warning(f"Received shutdown signal: {sig}. " f"Initiating graceful shutdown...")
    shutdown_event.set()


# --- Main Application Class (Optional but good practice) ---
class TradingBotApp:
    """Encapsulates the trading bot application setup and lifecycle."""

    def __init__(self, config: AppSettings):
        self.config = config
        self.position_manager: Optional[PositionManager] = None
        self.strategy_manager: Optional[StrategyManager] = None
        self.risk_controller: Optional[RiskController] = None
        self.order_executor: Optional[OrderExecutor] = None
        # self.market_data_stream: Optional[MarketDataStream] = None
        self.trading_manager: Optional[TradingManager] = None

    async def initialize(self):
        """Initializes all bot components."""
        log.info(f"Initializing Trading Bot: {self.config.app_name}")
        log.info(
            f"Environment: {self.config.environment}, "
            f"Log Level: {self.config.log_level}"
        )

        # --- Instantiate Components (Dependency Injection) ---
        log.info("Instantiating components...")

        # Position Manager (needs config)
        self.position_manager = PositionManager(config=self.config)

        # Strategy Manager (needs config)
        self.strategy_manager = StrategyManager(config=self.config)

        # Risk Controller (needs config, position manager)
        self.risk_controller = RiskController(
            config=self.config, position_manager=self.position_manager
        )

        # Order Executor (needs config, position manager)
        self.order_executor = OrderExecutor(
            config=self.config, position_manager=self.position_manager
        )

        # Trading Manager (needs all other components)
        self.trading_manager = TradingManager(
            config=self.config,
            strategy_manager=self.strategy_manager,
            position_manager=self.position_manager,
            risk_controller=self.risk_controller,
            order_executor=self.order_executor,
            # market_data_stream=self.market_data_stream
        )
        log.info("All components instantiated.")

    async def run(self):
        """Starts the bot and runs the main application loop."""
        if not self.trading_manager:
            log.critical("Trading Manager not initialized. Cannot run.")
            return

        log.info("Starting main application run loop...")
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, handle_shutdown_signal)  # Ctrl+C
        signal.signal(signal.SIGTERM, handle_shutdown_signal)  # Kill signal

        # Start the trading manager
        await self.trading_manager.start()

        # Keep the application running until shutdown is signaled
        log.info("Bot started. Waiting for shutdown signal (Ctrl+C)...")
        await shutdown_event.wait()

        # Initiate shutdown sequence
        log.info("Shutdown signal received. Stopping components...")
        await self.shutdown()

    async def shutdown(self):
        """Performs graceful shutdown of all components."""
        log.info("Executing graceful shutdown...")

        # Stop the trading manager first
        if self.trading_manager:
            await self.trading_manager.stop()

        # Stop other components if needed (e.g., data stream)
        # if self.market_data_stream: await self.market_data_stream.stop()

        log.info("Trading Bot shutdown complete.")


# --- Script Entry Point ---
async def main():
    """Main asynchronous function to run the bot."""
    try:
        # Load configuration from config.yaml/secrets.yaml/env vars
        config = get_config()
        if config is None:
            print("CRITICAL: Failed to load configuration.", file=sys.stderr)
            sys.exit(1)

        # Create and Initialize the Application
        app = TradingBotApp(config)
        await app.initialize()

        # Run the Application
        await app.run()

    except Exception as e:
        # Catch unexpected errors during startup or runtime
        log.critical(f"Unhandled exception in main: {e}", exc_info=True)
        # Ensure shutdown is attempted even if run fails mid-way
        if "app" in locals() and app and hasattr(app, "shutdown"):
            log.info("Attempting emergency shutdown...")
            await app.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    # Check Python version (Asyncio features might require >= 3.7)
    if sys.version_info < (3, 7):
        print("Python 3.7 or higher is required.", file=sys.stderr)
        sys.exit(1)

    # Run the main asynchronous function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This might catch Ctrl+C before the signal handler
        log.info("KeyboardInterrupt caught in __main__. Exiting.")
    except Exception as e:
        print(f"Critical error during asyncio.run: {e}", file=sys.stderr)
        sys.exit(1)
