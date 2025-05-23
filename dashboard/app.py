"""Main dashboard application with real-time updates via Redis."""

import logging
import os
import sys

import dash
import dash_bootstrap_components as dbc

# Add the root directory to the Python module search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use absolute imports assuming 'cyclonev2' is the project root added to PYTHONPATH
from hydrobot.dashboard.data_provider import dashboard_data
from hydrobot.dashboard.layouts import create_layout
from hydrobot.utils.logger_setup import get_logger

log = get_logger(__name__)

# --- Initialize Dash App ---
# Load external stylesheets (Bootstrap theme)
external_stylesheets = [
    dbc.themes.BOOTSTRAP
]  # Or choose another theme like CYBORG, DARKLY

app = dash.Dash(
    __name__,
    external_stylesheets=external_stylesheets,
    suppress_callback_exceptions=True,  # Set to True if callbacks are in different files
    title="HydroBot Dashboard",
    update_title="Updating...",
)
server = app.server  # Expose server for potential WSGI deployment (e.g., Gunicorn)

# --- Define App Layout ---
app.layout = create_layout()


# --- Setup Redis Data Provider ---
@app.before_first_request
async def setup_data_provider():
    """Initialize Redis connection before first request."""
    try:
        await dashboard_data.start()
        log.info("Dashboard data provider initialized")
    except Exception as e:
        log.error(f"Failed to initialize dashboard data provider: {e}")


# --- Run the App ---
if __name__ == "__main__":
    # Register Callbacks (import here to avoid circular imports)
    from hydrobot.dashboard import callbacks  # noqa: F401

    # Setup basic logging for dashboard process if run directly
    # Note: If run via main.py, logging might be configured there already
    # Check if logging is already configured by root logger to avoid duplicate handlers
    if not logging.getLogger().hasHandlers():
        log_level_dashboard = getattr(logging, config.LOG_LEVEL, logging.INFO)
        logging.basicConfig(
            level=log_level_dashboard,
            format="%(asctime)s - %(levelname)s [%(name)s] %(message)s",
        )

    log.info("Starting Dash development server...")
    # Set debug=True for development (enables hot-reloading, detailed error pages)
    # Set debug=False for production deployment
    debug_mode = config.LOG_LEVEL == "DEBUG"
    app.run(
        debug=debug_mode, host="0.0.0.0", port=8050
    )  # Using port 8050 as decided earlier
