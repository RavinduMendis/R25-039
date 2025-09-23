from typing import Dict, Any
from datetime import datetime, timezone
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.console import Group
from rich.align import Align
from rich.progress_bar import ProgressBar
from ..config import MODULE_NAME_MAPPING
from ..components import create_details_table

# --- Helper Function for Uptime ---

def _calculate_uptime(start_ts: int) -> str:
    """Calculates uptime from a start timestamp."""
    if not isinstance(start_ts, (int, float)) or start_ts == 0:
        return "N/A"
    try:
        uptime_delta = datetime.now(timezone.utc) - datetime.fromtimestamp(start_ts, tz=timezone.utc)
        # Remove microseconds for cleaner display
        return str(uptime_delta).split('.')[0]
    except (ValueError, TypeError):
        return "Invalid Timestamp"

# --- Panel Creation Functions ---

def create_training_status_panel(overview_data: Dict[str, Any]) -> Panel:
    if "error" in overview_data:
        return Panel(f"[bold red]Error:[/] {overview_data.get('error')}", title="Server Overview", border_style="red")
    progress = overview_data.get("training_progress", {})
    current_round, total_rounds, percentage = progress.get("current_round", 0), progress.get("total_rounds", 1), progress.get("percentage", 0)
    status_table = Table.grid(expand=True, padding=(0, 1))
    status_table.add_column(style="bold cyan", no_wrap=True, ratio=1)
    status_table.add_column(justify="left", ratio=2)
    status_table.add_row("Server State:", f"[{overview_data.get('server_status', {}).get('class', 'red')}]{overview_data.get('server_status', {}).get('text', 'Offline')}[/]")
    status_table.add_row("Progress:", f"Round {current_round} of {total_rounds}")
    status_table.add_row("", ProgressBar(total=100, completed=percentage, width=30))
    status_table.add_row("Round Duration:", f"{overview_data.get('round_duration_formatted', 'N/A')}")
    status_table.add_row("Last Aggregation:", f"{overview_data.get('time_since_last_aggregation_formatted', 'N/A')}")
    return Panel(status_table, title="Server Overview", border_style="green", expand=True)

def create_orchestrator_panel(orchestrator_data: Dict[str, Any]) -> Panel:
    if "error" in orchestrator_data:
        return Panel(f"[bold red]Error:[/] {orchestrator_data['error']}", title="Orchestrator", border_style="red")
    table = create_details_table(orchestrator_data)
    return Panel(table, title="[bold]Orchestrator[/]", border_style="green", expand=True)

def create_manager_panel(manager_name: str, data: Dict[str, Any]) -> Panel:
    details = data.get("modules", {}).get(manager_name.replace(' ', '_').lower(), {})
    if not details:
        return Panel(f"[italic]{manager_name} details not available[/]", title=manager_name, border_style="green", expand=True)
    table = create_details_table(details)
    return Panel(table, title=f"[bold green]{manager_name}[/]", border_style="green", expand=True)

def create_model_manager_summary_panel(mm_data: Dict[str, Any]) -> Panel:
    if "error" in mm_data:
        return Panel(f"[bold red]Error:[/] {mm_data['error']}", title="Model Manager", border_style="red")
    content_table = Table.grid(padding=(0, 1), expand=True)
    content_table.add_column(style="bold cyan", no_wrap=True)
    content_table.add_column()
    version = mm_data.get("model_version", "N/A")
    converged = mm_data.get("convergence_status", "N/A")
    content_table.add_row("Version:", str(version))
    content_table.add_row("Status:", str(converged))
    summary = mm_data.get("aggregation_summary", {})
    if summary and (summary.get('first_aggregation') or summary.get('last_aggregation')):
        content_table.add_row()
        for key, details in summary.items():
            if not details: continue
            title = "First Aggregation" if key == 'first_aggregation' else "Last Aggregation"
            content_table.add_row(f"[bold green]{title}[/]")
            content_table.add_row("  Round:", str(details.get('round', 'N/A')))
            metrics = details.get('metrics', {})
            if metrics:
                content_table.add_row("  Metrics:")
                for m_key, m_value in metrics.items():
                    value_str = f"{m_value:.4f}" if isinstance(m_value, (int, float)) else str(m_value).replace('_', ' ').title()
                    key_str = m_key.replace('_', ' ').title()
                    content_table.add_row(f"    {key_str}:", value_str)
    return Panel(content_table, title="[bold]Model Manager[/]", border_style="green", expand=True)

def create_client_health_panel(data: Dict[str, Any]) -> Panel:
    clients = list(data.get("clients", {}).values())
    total_clients = len(clients)
    blocked_clients = sum(1 for c in clients if c.get('is_blocked'))
    title = f"[bold]Client Health Status[/] ([white]Total:[/] {total_clients}, [green]Active:[/] {total_clients - blocked_clients}, [red]Blocked:[/] {blocked_clients})"
    table = Table(border_style="blue", expand=True, title=title)
    table.add_column("Client ID", style="cyan", ratio=2)
    table.add_column("Status", style="magenta", ratio=1)
    table.add_column("Reputation", style="green", ratio=1)
    table.add_column("Uptime", style="blue", ratio=2)
    table.add_column("Client Type", style="cyan", ratio=1)
    table.add_column("Details", style="white", ratio=3)
    if "error" in data:
        table.add_row(data["error"], "", "", "", "", "")
    else:
        if not clients:
            table.add_row("[italic]No clients connected.[/]", "", "", "", "", "")
        for client_info in clients:
            is_blocked = client_info.get('is_blocked', False)
            status_text = "[green]Connected[/]"
            if is_blocked: status_text = "[bold red]Blocked[/]"
            elif client_info.get('status') != "connected": status_text = f"[yellow]{client_info.get('status', 'N/A').capitalize()}[/]"
            
            details_text = client_info.get('ip_address', 'N/A')
            if is_blocked: details_text = client_info.get('block_details', {}).get('reason', '')
            
            uptime_str = _calculate_uptime(client_info.get('uptime_start_time'))
            client_type = str(client_info.get('client_type', 'N/A'))

            table.add_row(
                client_info.get('client_id', 'N/A'), 
                status_text, 
                str(client_info.get('reputation', 'N/A')),
                uptime_str,
                client_type,
                details_text
            )
    return Panel(table, border_style="blue", expand=True)

def create_logs_panel(logs: Any) -> Panel:
    # FIXED: Replaced Text-based log display with a structured Table.
    if not isinstance(logs, list):
        error_msg = "Unexpected log format"
        if isinstance(logs, dict) and 'error' in logs:
            error_msg = logs['error']
        return Panel(f"[red]Error: {error_msg}[/]", title="[bold]Recent Logs[/]", border_style="red")

    log_table = Table.grid(expand=True, padding=(0, 1))
    log_table.add_column(style="dim", no_wrap=True)  # Timestamp
    log_table.add_column(width=7)  # Level
    log_table.add_column(ratio=1)  # Message

    if not logs:
        log_table.add_row("[italic]No logs available.[/]")
    else:
        for log in logs[-5:]:  # Display last 5 logs
            timestamp = log.get('asctime', 'N/A').split(',')[0]
            level = log.get('levelname', 'I')
            msg = log.get('message', 'N/A')
            color = {"ERROR": "red", "WARNING": "yellow"}.get(level, "green")

            log_table.add_row(
                f"{timestamp}",
                f"[{color}]{level[:4]}[/{color}]",
                msg
            )

    return Panel(log_table, title="[bold]Recent Logs[/]", border_style="red", expand=True)

def create_module_details_panel(module_name: str, details: Dict[str, Any]) -> Panel:
    friendly_name = MODULE_NAME_MAPPING.get(module_name, module_name).replace('_', ' ').title()
    table = create_details_table(details)
    return Panel(table, title=f"[bold yellow]{friendly_name}[/]", border_style="magenta", expand=True)

# --- Main Layout Function ---

async def create_overview_page(overview_data, client_health_data, logs_data, status_data, modules_data, state) -> Layout:
    # Re-designed the layout according to the new specification.
    layout = Layout(name="body")
    layout.split_row(
        Layout(name="left_column", ratio=1),
        Layout(name="right_column", ratio=1)
    )

    # --- Left Column ---
    layout["left_column"].split_column(
        Layout(name="top_left_grid", ratio=2),
        Layout(name="client_health_area", ratio=1)
    )
    # 2x2 grid for managers
    top_left_grid = layout["top_left_grid"]
    top_left_grid.split_column(Layout(name="row1"), Layout(name="row2"))
    top_left_grid["row1"].split_row(Layout(name="server_overview"), Layout(name="orchestrator"))
    top_left_grid["row2"].split_row(Layout(name="client_manager"), Layout(name="model_manager"))

    # --- Right Column ---
    layout["right_column"].split_column(
        Layout(name="other_modules_area", ratio=3),
        Layout(name="logs_area", ratio=1)
    )

    # --- Populate Panels ---
    orchestrator_data = modules_data.get('orchestrator', {})
    mm_data = modules_data.get('mm', {})
    
    # Populate left column
    layout["server_overview"].update(create_training_status_panel(overview_data))
    layout["orchestrator"].update(create_orchestrator_panel(orchestrator_data))
    layout["client_manager"].update(create_manager_panel("Client Manager", status_data))
    layout["model_manager"].update(create_model_manager_summary_panel(mm_data))
    layout["client_health_area"].update(create_client_health_panel(client_health_data))
    
    # Populate right column
    layout["logs_area"].update(create_logs_panel(logs_data))
    
    # Populate the 'Other Modules' 2x2 grid panel
    other_modules_data = {k: v for k, v in modules_data.items() if k not in ['mm', 'orchestrator'] and 'error' not in v}
    module_panels = [create_module_details_panel(name, details) for name, details in other_modules_data.items()]
    
    if module_panels:
        # Create a 2x2 grid for the other modules
        modules_grid = Layout(name="modules_grid")
        modules_grid.split_column(Layout(name="mod_row1"), Layout(name="mod_row2"))
        
        # Distribute panels into the grid
        if len(module_panels) > 0:
            modules_grid["mod_row1"].split_row(Layout(module_panels[0]), Layout(module_panels[1]) if len(module_panels) > 1 else Layout())
        if len(module_panels) > 2:
            modules_grid["mod_row2"].split_row(Layout(module_panels[2]), Layout(module_panels[3]) if len(module_panels) > 3 else Layout())
        
        layout["other_modules_area"].update(Panel(modules_grid, title="[bold green]Other Modules[/]", border_style="green"))
    else:
        layout["other_modules_area"].update(Panel("[italic]No other modules available[/]", title="Other Modules", border_style="green"))

    return layout