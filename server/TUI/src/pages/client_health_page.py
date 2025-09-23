from typing import Dict, Any
from datetime import datetime, timezone
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

def _format_timestamp(ts: int) -> str:
    """Converts a Unix timestamp to a formatted string."""
    if not isinstance(ts, (int, float)) or ts == 0:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    except (ValueError, TypeError):
        return "Invalid Timestamp"

def _calculate_uptime(start_ts: int) -> str:
    """Calculates uptime from a start timestamp."""
    if not isinstance(start_ts, (int, float)) or start_ts == 0:
        return "N/A"
    try:
        # Get the current time in UTC to correctly compare with UTC timestamps
        uptime_delta = datetime.now(timezone.utc) - datetime.fromtimestamp(start_ts, tz=timezone.utc)
        # Remove microseconds for cleaner display
        return str(uptime_delta).split('.')[0]
    except (ValueError, TypeError):
        return "Invalid Timestamp"


def create_client_health_panel(data: Dict[str, Any]) -> Panel:
    """Creates a Rich Panel displaying client health information in a table."""
    table = Table(border_style="blue", expand=True)
    table.add_column("Client ID", style="cyan", justify="left", ratio=2)
    table.add_column("Status", style="bold", justify="center", ratio=1)
    table.add_column("Reputation", style="green", justify="center", ratio=1)
    table.add_column("Latency (ms)", style="magenta", justify="right", ratio=1)
    table.add_column("Uptime", style="blue", justify="left", ratio=2)
    table.add_column("Client Type", style="cyan", justify="left", ratio=1)
    table.add_column("Last Success Rnd", style="yellow", justify="center", ratio=1)
    table.add_column("IP Address", style="yellow", justify="left", ratio=2)
    table.add_column("Last Heartbeat", style="dim", justify="left", ratio=2)
    table.add_column("Details", style="white", justify="left", ratio=3)

    if "error" in data:
        # Span the error message across all columns
        table.add_row(data["error"], *[""] * 9)
    else:
        clients = data.get("clients", {})
        total = len(clients)
        blocked = sum(1 for c in clients.values() if c.get('is_blocked'))
        table.title = "[bold]Client Health Status[/]"
        table.caption = f"[white]Total Clients:[/] {total} | [green]Active:[/] {total - blocked} | [red]Blocked:[/] {blocked}"

        if not clients:
            table.add_row("[italic]No clients connected.[/]", *[""] * 9)
        
        for client_id, client_info in clients.items():
            is_blocked = client_info.get('is_blocked', False)
            block_details = client_info.get('block_details')

            # Determine Status style and text
            status_text = "[green]Connected[/]"
            if is_blocked:
                status_text = "[red]Blocked[/]"
            elif client_info.get('status') != "connected":
                status_text = f"[yellow]{str(client_info.get('status', 'N/A')).capitalize()}[/]"

            # --- FIX START ---
            # Handle reputation_history being a list or a dictionary
            latency_ms_str = "N/A"
            reputation_history = client_info.get('reputation_history')
            latest_round_history = None

            if isinstance(reputation_history, list) and reputation_history:
                # If it's a list, get the last (most recent) entry
                latest_round_history = reputation_history[-1]
            elif isinstance(reputation_history, dict):
                # If it's a dict, get the entry for round '0' (or the max key)
                if '0' in reputation_history:
                    latest_round_history = reputation_history['0']
                elif reputation_history: # Fallback for other keys
                    latest_round_key = max(reputation_history.keys())
                    latest_round_history = reputation_history[latest_round_key]

            if isinstance(latest_round_history, dict):
                latency = latest_round_history.get('latency')
                if isinstance(latency, (int, float)):
                    latency_ms_str = f"{latency * 1000:.2f}"
            # --- FIX END ---

            # Determine Details text
            details_text = ""
            if is_blocked and isinstance(block_details, dict):
                details_text = block_details.get('reason', 'No reason specified.')
            
            # Add all data to the row, ensuring all values are strings
            table.add_row(
                str(client_id),
                status_text,
                str(client_info.get('reputation', 'N/A')),
                latency_ms_str,
                _calculate_uptime(client_info.get('uptime_start_time')),
                str(client_info.get('client_type', 'N/A')),
                str(client_info.get('last_successful_round', 'N/A')),
                str(client_info.get('ip_address', 'N/A')),
                _format_timestamp(client_info.get('last_heartbeat')),
                details_text
            )

    return Panel(table, border_style="blue", expand=True)

async def create_client_health_page(client_health_data: Dict[str, Any]) -> Layout:
    """Creates the main layout for the client health page."""
    layout = Layout(name="body")
    layout.update(create_client_health_panel(client_health_data))
    return layout