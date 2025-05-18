"""Dash callbacks for real-time dashboard updates."""
from typing import List
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objs as go
from dash import Input, Output, State, ctx, callback
from dash.exceptions import PreventUpdate

from hydrobot.dashboard.data_provider import dashboard_data
from hydrobot.utils.logger_setup import get_logger

log = get_logger(__name__)

# --- Portfolio Value & PnL Updates ---
@callback(
    [Output('portfolio-value-graph', 'figure'),
     Output('portfolio-stats', 'children')],
    [Input('portfolio-update-interval', 'n_intervals'),
     Input('timeframe-selector', 'value')]
)
def update_portfolio_value(n_intervals: int, timeframe: str) -> tuple:
    """Update portfolio value graph and statistics."""
    if not dashboard_data.is_connected:
        log.warning("Dashboard not connected to Redis")
        raise PreventUpdate
    
    # Convert timeframe to minutes
    minutes = {
        '1H': 60,
        '4H': 240,
        '1D': 1440,
        '1W': 10080
    }.get(timeframe, 60)
    
    # Get portfolio history
    df = dashboard_data.get_portfolio_history(minutes=minutes)
    if df.empty:
        raise PreventUpdate
    
    # Create portfolio value figure
    figure = {
        'data': [
            go.Scatter(
                x=df.index,
                y=df['total_value'],
                name='Portfolio Value',
                fill='tozeroy'
            )
        ],
        'layout': {
            'title': 'Portfolio Value Over Time',
            'xaxis': {'title': 'Time'},
            'yaxis': {'title': 'Value (USD)'},
            'height': 400
        }
    }
    
    # Calculate statistics
    start_value = df['total_value'].iloc[0] if not df.empty else 0
    current_value = df['total_value'].iloc[-1] if not df.empty else 0
    pnl = current_value - start_value
    pnl_pct = (pnl / start_value * 100) if start_value > 0 else 0
    
    stats = [
        f"Current Value: ${current_value:,.2f}",
        f"Period P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)",
        f"Last Update: {dashboard_data.last_update.strftime('%Y-%m-%d %H:%M:%S')}"
    ]
    
    return figure, stats

# --- Active Trades Table ---
@callback(
    Output('active-positions-table', 'data'),
    Input('position-update-interval', 'n_intervals')
)
def update_active_positions(n_intervals: int) -> List[dict]:
    """Update active positions table."""
    if not dashboard_data.is_connected:
        raise PreventUpdate
    
    positions = dashboard_data.get_active_positions()
    
    # Format positions for DataTable
    position_data = []
    for symbol, pos in positions.items():
        position_data.append({
            'symbol': symbol,
            'entry_price': f"${pos['entry_price']:,.2f}",
            'quantity': f"{pos['quantity']:.8f}",
            'entry_time': pd.to_datetime(pos['entry_time']).strftime('%Y-%m-%d %H:%M:%S'),
            'current_value': f"${pos['entry_price'] * pos['quantity']:,.2f}"
        })
    
    return position_data

# --- Trade History Graph ---
@callback(
    Output('trade-history-graph', 'figure'),
    [Input('trade-update-interval', 'n_intervals'),
     Input('symbol-selector', 'value'),
     Input('timeframe-selector', 'value')]
)
def update_trade_history(n_intervals: int, symbol: str, timeframe: str) -> dict:
    """Update trade history visualization."""
    if not dashboard_data.is_connected:
        raise PreventUpdate
    
    # Convert timeframe to minutes
    minutes = {
        '1H': 60,
        '4H': 240,
        '1D': 1440,
        '1W': 10080
    }.get(timeframe, 60)
    
    # Get trade history
    df = dashboard_data.get_trade_history(minutes=minutes)
    if df.empty:
        raise PreventUpdate
    
    if symbol:
        df = df[df['symbol'] == symbol]
    
    # Create scatter plot for trades
    buy_trades = df[df['trade_type'] == 'BUY']
    sell_trades = df[df['trade_type'] == 'SELL']
    
    figure = {
        'data': [
            # Buy trades
            go.Scatter(
                x=buy_trades.index,
                y=buy_trades['price'],
                mode='markers',
                name='Buy',
                marker=dict(
                    symbol='triangle-up',
                    size=10,
                    color='green'
                )
            ),
            # Sell trades
            go.Scatter(
                x=sell_trades.index,
                y=sell_trades['price'],
                mode='markers',
                name='Sell',
                marker=dict(
                    symbol='triangle-down',
                    size=10,
                    color='red'
                )
            )
        ],
        'layout': {
            'title': f'Trade History - {symbol if symbol else "All Symbols"}',
            'xaxis': {'title': 'Time'},
            'yaxis': {'title': 'Price'},
            'height': 400
        }
    }
    
    return figure

# --- System Events Log ---
@callback(
    Output('system-events-log', 'children'),
    Input('events-update-interval', 'n_intervals')
)
def update_system_events(n_intervals: int) -> List[dict]:
    """Update system events log."""
    if not dashboard_data.is_connected:
        raise PreventUpdate
    
    events = dashboard_data.get_recent_events(count=10)
    
    # Format events for display
    event_elements = []
    for event in events:
        event_time = pd.to_datetime(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        event_type = event['event_type']
        message = event['message']
        
        color = {
            'ERROR': 'red',
            'WARNING': 'orange',
            'INFO': 'blue'
        }.get(event_type, 'gray')
        
        event_elements.append(
            html.Div([
                html.Span(f"{event_time} - ", style={'color': 'gray'}),
                html.Span(f"{event_type}: ", style={'color': color, 'fontWeight': 'bold'}),
                html.Span(message)
            ], style={'marginBottom': '5px'})
        )
    
    return event_elements

# --- Strategy Status Updates ---
@callback(
    Output('strategy-status', 'children'),
    Input('strategy-update-interval', 'n_intervals')
)
def update_strategy_status(n_intervals: int) -> List[dict]:
    """Update strategy status indicators."""
    if not dashboard_data.is_connected:
        raise PreventUpdate
    
    states = dashboard_data.get_strategy_states()
    
    # Format strategy states for display
    status_elements = []
    for strategy, state in states.items():
        status = state['state']
        timestamp = pd.to_datetime(state['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        details = state.get('details', {})
        
        color = {
            'ACTIVE': 'green',
            'PAUSED': 'orange',
            'STOPPED': 'red',
            'ERROR': 'red'
        }.get(status, 'gray')
        
        status_elements.append(
            html.Div([
                html.H4(strategy),
                html.P([
                    html.Span("Status: ", style={'fontWeight': 'bold'}),
                    html.Span(status, style={'color': color}),
                ]),
                html.P(f"Last Update: {timestamp}"),
                html.Details([
                    html.Summary("Details"),
                    html.Pre(json.dumps(details, indent=2))
                ]) if details else None
            ], style={'marginBottom': '20px'})
        )
    
    return status_elements
