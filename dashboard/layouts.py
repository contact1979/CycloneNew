# /dashboard/layouts.py

import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table
import plotly.graph_objects as go
import pandas as pd
import logging # Added logging import

# Use absolute imports assuming 'cyclonev2' is the project root added to PYTHONPATH
import config # To display default config values
# Use relative imports for modules within the same package
from . import data_provider # To get initial dropdown options
# from .. import config

log = logging.getLogger(__name__) # Added logger instance

# --- Helper Functions ---
def create_empty_figure(message="No data available") -> go.Figure:
    """Creates an empty Plotly figure with a message."""
    fig = go.Figure()
    fig.update_layout(
        xaxis={'visible': False},
        yaxis={'visible': False},
        annotations=[{'text': message, 'xref': 'paper', 'yref': 'paper', 'showarrow': False, 'font': {'size': 16}}]
    )
    return fig

# --- Layout Sections ---

def create_overview_layout() -> dbc.Container:
    """Creates the layout for the Overview tab."""
    return dbc.Container([
        dbc.Row([
            dbc.Col(dbc.Card([dbc.CardHeader("Status"), dbc.CardBody(id='overview-status-indicators')], color="light"), width=3),
            dbc.Col(dbc.Card([dbc.CardHeader("Total Value"), dbc.CardBody(id='overview-total-value')], color="light"), width=3),
            dbc.Col(dbc.Card([dbc.CardHeader("Cash"), dbc.CardBody(id='overview-cash')], color="light"), width=3),
            dbc.Col(dbc.Card([dbc.CardHeader("Open Positions"), dbc.CardBody(id='overview-open-positions')], color="light"), width=3),
        ], className="mb-4"),
        dbc.Row([
             dbc.Col(dbc.Card([dbc.CardHeader("Portfolio Value Over Time"), dbc.CardBody(dcc.Graph(id='overview-pnl-graph', figure=create_empty_figure()))]), width=12),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col(dbc.Card([dbc.CardHeader("Recent Trades"), dbc.CardBody(
                dash_table.DataTable(
                    id='overview-trade-table',
                    columns=[], # Populated by callback
                    data=[],    # Populated by callback
                    page_size=10,
                    style_cell={'textAlign': 'left', 'padding': '5px'},
                    style_header={'fontWeight': 'bold'},
                    style_table={'overflowX': 'auto'},
                )
            )]), width=12),
        ]),
         dbc.Row([
            dbc.Col(dbc.Card([dbc.CardHeader("System Alerts / Disabled Symbols"), dbc.CardBody(id='overview-alerts')]), width=12),
        ], className="mt-4"),
    ], fluid=True)

def create_market_view_layout() -> dbc.Container:
    """Creates the layout for the Market View tab."""
    # Get initial list of symbols for dropdown
    try:
        initial_symbol_options = [{'label': s, 'value': s} for s in data_provider.get_target_symbols_list()]
    except Exception as e:
        log.error(f"Failed to get initial symbols for dropdown: {e}")
        initial_symbol_options = [] # Default to empty list on error

    return dbc.Container([
        dbc.Row([
            dbc.Col(dcc.Dropdown(
                id='market-symbol-dropdown',
                options=initial_symbol_options,
                value=initial_symbol_options[0]['value'] if initial_symbol_options else None, # Default to first symbol
                clearable=False,
                placeholder="Select Symbol..."
            ), width=4),
            dbc.Col(dcc.Dropdown(
                id='market-timeframe-dropdown',
                options=[
                    {'label': '1 Hour', 'value': '1h'},
                    {'label': '4 Hours', 'value': '4h'},
                    {'label': '12 Hours', 'value': '12h'},
                    {'label': '1 Day', 'value': '24h'},
                    {'label': '7 Days', 'value': '7d'},
                    {'label': '30 Days', 'value': '30d'},
                ],
                value='24h', # Default timeframe
                clearable=False,
            ), width=3),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col(dcc.Graph(id='market-price-chart', figure=create_empty_figure("Select symbol to load chart"))),
        ]),
        dbc.Row([
             dbc.Col(html.H5("Recent News & Tweets"), width=12),
             # TODO: Add component to display recent news/tweets for the selected symbol
             dbc.Col(html.Div(id='market-news-feed', children="News feed placeholder..."), width=12),
        ], className="mt-4")
    ], fluid=True)

def create_sentiment_layout() -> dbc.Container:
    """Creates the layout for the Sentiment Analysis tab."""
    return dbc.Container([
         dbc.Row([
            dbc.Col(dcc.Dropdown(
                id='sentiment-timeframe-dropdown',
                options=[
                    {'label': '1 Hour', 'value': '1h'},
                    {'label': '4 Hours', 'value': '4h'},
                    {'label': '12 Hours', 'value': '12h'},
                    {'label': '1 Day', 'value': '24h'},
                    {'label': '7 Days', 'value': '7d'},
                ],
                value='24h', # Default timeframe
                clearable=False,
            ), width=3),
         ], className="mb-4"),
         dbc.Row([
             dbc.Col(dcc.Graph(id='sentiment-agg-chart', figure=create_empty_figure())),
         ]),
         # TODO: Add sections for source-specific sentiment charts and recent high-impact posts
         dbc.Row([
             dbc.Col(html.H5("Recent High-Impact Posts/Tweets"), width=12),
             dbc.Col(html.Div(id='sentiment-feed', children="Sentiment feed placeholder..."), width=12),
         ], className="mt-4")
    ], fluid=True)

def create_trading_layout() -> dbc.Container:
    """Creates the layout for the Trading Monitor tab."""
    return dbc.Container([
        dbc.Row([
            dbc.Col(html.H4("Open Positions"), width=12)
        ], className="mb-2"),
        dbc.Row([
            dbc.Col(dash_table.DataTable(
                    id='trading-open-positions-table',
                    columns=[], data=[], page_size=10,
                    style_cell={'textAlign': 'left', 'padding': '5px'}, style_header={'fontWeight': 'bold'}, style_table={'overflowX': 'auto'}
                ), width=12)
        ], className="mb-4"),
        dbc.Row([
            dbc.Col(html.H4("Trade History"), width=12)
        ], className="mb-2"),
        dbc.Row([
            dbc.Col(dash_table.DataTable(
                    id='trading-history-table',
                    columns=[], data=[], page_size=20, filter_action='native', sort_action='native',
                    style_cell={'textAlign': 'left', 'padding': '5px'}, style_header={'fontWeight': 'bold'}, style_table={'overflowX': 'auto'}
                ), width=12)
        ]),
    ], fluid=True)

def create_settings_layout() -> dbc.Container:
    """Creates the layout for the Settings tab."""
    # Get initial values (might be defaults if config not updated at runtime)
    try:
        initial_settings = data_provider.get_config_settings()
    except Exception as e:
        log.error(f"Failed to get initial config settings for layout: {e}")
        initial_settings = {} # Default to empty dict on error

    return dbc.Container([
        dbc.Row([dbc.Col(html.H4("Trading Mode"), width=12)], className="mb-2"),
        dbc.Row([
            dbc.Col(dbc.Switch(id='settings-trading-mode-switch', label="Enable Live Trading", value=False), width=6), # Default to Paper
            dbc.Col(html.Div(id='settings-trading-mode-status', children="Current Mode: PAPER"), width=6)
        ], className="mb-4"),

        dbc.Row([dbc.Col(html.H4("Risk Parameters"), width=12)], className="mb-2"),
        dbc.Row([
            dbc.Col(dbc.Label("% Capital per Trade"), width=3),
            dbc.Col(dbc.Input(id='settings-capital-pct-input', type='number', value=initial_settings.get('trade_capital_percentage', 0.01), min=0.001, max=0.1, step=0.001), width=3),
            dbc.Col(dbc.Button("Update", id='settings-update-capital-pct-button', color="primary", size="sm"), width=2),
            dbc.Col(html.Div(id='settings-update-capital-pct-status'), width=4)
        ], className="mb-3 align-items-center"),
        dbc.Row([
            dbc.Col(dbc.Label("Stop Loss %"), width=3),
            dbc.Col(dbc.Input(id='settings-stop-loss-input', type='number', value=initial_settings.get('stop_loss_pct', 0.05), min=0.001, max=0.5, step=0.001), width=3),
            dbc.Col(dbc.Button("Update", id='settings-update-stop-loss-button', color="primary", size="sm"), width=2),
            dbc.Col(html.Div(id='settings-update-stop-loss-status'), width=4)
        ], className="mb-3 align-items-center"),
        dbc.Row([
            dbc.Col(dbc.Label("Take Profit %"), width=3),
            dbc.Col(dbc.Input(id='settings-take-profit-input', type='number', value=initial_settings.get('take_profit_pct', 0.10), min=0.001, max=1.0, step=0.001), width=3),
            dbc.Col(dbc.Button("Update", id='settings-update-take-profit-button', color="primary", size="sm"), width=2),
            dbc.Col(html.Div(id='settings-update-take-profit-status'), width=4)
        ], className="mb-3 align-items-center"),
         dbc.Row([
            dbc.Col(dbc.Label("Max Portfolio Drawdown %"), width=3),
            dbc.Col(dbc.Input(id='settings-drawdown-input', type='number', value=initial_settings.get('portfolio_drawdown_pct', 0.15), min=0.01, max=0.9, step=0.01), width=3),
            dbc.Col(dbc.Button("Update", id='settings-update-drawdown-button', color="primary", size="sm"), width=2),
            dbc.Col(html.Div(id='settings-update-drawdown-status'), width=4)
        ], className="mb-4 align-items-center"),

        dbc.Row([dbc.Col(html.H4("Disabled Symbols Management"), width=12)], className="mb-2"),
        dbc.Row([
             dbc.Col(dbc.Label("Select symbol to re-enable:"), width=3),
             dbc.Col(dcc.Dropdown(id='settings-disabled-symbol-dropdown', options=[], placeholder="Select symbol..."), width=4),
             dbc.Col(dbc.Button("Re-enable Symbol", id='settings-reenable-symbol-button', color="warning", size="sm"), width=2),
             dbc.Col(html.Div(id='settings-reenable-symbol-status'), width=3)
        ], className="mb-3 align-items-center"),

        # Placeholder for other settings (e.g., model confidence thresholds)
    ], fluid=True)


def create_main_layout() -> html.Div:
    """Creates the main application layout with tabs."""
    return html.Div([
        dbc.NavbarSimple(brand="Cyclone v2 Trading Bot Dashboard", color="dark", dark=True, fluid=True),
        dbc.Tabs(id="main-tabs", active_tab="tab-overview", children=[
            dbc.Tab(label="Overview", tab_id="tab-overview", children=create_overview_layout()),
            dbc.Tab(label="Market View", tab_id="tab-market", children=create_market_view_layout()),
            dbc.Tab(label="Sentiment", tab_id="tab-sentiment", children=create_sentiment_layout()),
            dbc.Tab(label="Trading Monitor", tab_id="tab-trading", children=create_trading_layout()),
            # dbc.Tab(label="Model Performance", tab_id="tab-performance", children=html.Div("Model Performance Placeholder")), # Add later
            dbc.Tab(label="Settings", tab_id="tab-settings", children=create_settings_layout()),
        ]),
        # Interval component for periodic updates
        dcc.Interval(
            id='interval-component',
            interval=15*1000, # 15 seconds in milliseconds
            n_intervals=0
        ),
        # Hidden div to store intermediate data or trigger actions (if needed)
        # dcc.Store(id='some-shared-state')
    ])
