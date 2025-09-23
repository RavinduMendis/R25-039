from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

def create_filter_panel(state) -> Panel:
    level_filter = state.log_filter
    search_term = state.log_search_term

    level_text = f"[bold white]Level:[/] [cyan]{level_filter}[/]"

    if state.is_searching:
        search_text = f"[bold white]Search:[/] [cyan]{search_term}[/][blink]|[/]"
        help_text = Text.from_markup("[bold green]Enter[/]/[bold green]Esc[/]: Exit | [bold green]r[/]: Clear", justify="right")
    else:
        search_text = f"[bold white]Search:[/] [cyan]{search_term if search_term else 'None'}[/]"
        help_text = Text.from_markup("[bold green]f[/]: Filter Level | [bold green]s[/]: Search | [bold green]r[/]: Reset", justify="right")

    filter_info_table = Table.grid(expand=True)
    filter_info_table.add_column(justify="left", ratio=2)
    filter_info_table.add_column(justify="right", ratio=3)
    filter_info_table.add_row(
        Text.from_markup(f"{level_text}   {search_text}"),
        help_text
    )

    return Panel(filter_info_table, border_style="green", padding=(0, 1), expand=True)

def create_logs_panel(logs, state) -> Panel:
    # This check is good practice and remains.
    if not isinstance(logs, list):
        error_msg = "Received unexpected data format for logs."
        if isinstance(logs, dict) and "error" in logs:
            error_msg = logs["error"]
        return Panel(f"[bold red]Error:[/] {error_msg}", title="Recent Logs", border_style="red", expand=True)

    # Filter logs based on state
    filtered_logs = []
    log_level_map = {"INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    filter_level_value = log_level_map.get(state.log_filter) if state.log_filter != "ALL" else 0
    search_term = state.log_search_term.lower()

    for log in logs:
        log_level = log.get('levelname', 'INFO').upper()
        log_message = log.get('message', '').lower()
        log_name = log.get('name', '').lower() # Also search in logger name

        if log_level_map.get(log_level, 0) < filter_level_value:
            continue
        if search_term and search_term not in log_message and search_term not in log_name:
            continue
        filtered_logs.append(log)
    
    # FIXED: Replaced Text with a structured Table for clarity and detail
    log_table = Table(border_style="dim", expand=True)
    log_table.add_column("Timestamp", style="white", ratio=2)
    log_table.add_column("Level", style="white", ratio=1)
    log_table.add_column("Logger", style="cyan", ratio=2)
    log_table.add_column("Message", style="white", ratio=5)

    if not filtered_logs:
        log_table.add_row("[italic dim]No logs found with the current filters.[/]", "", "", "")
    else:
        for log in filtered_logs:
            timestamp = log.get('asctime', 'N/A')
            level = log.get('levelname', 'INFO')
            name = log.get('name', 'N/A')
            message = log.get('message', 'N/A')
            level_color = {"ERROR": "bold red", "CRITICAL": "bold red", "WARNING": "bold yellow"}.get(level, "green")
            
            log_table.add_row(
                timestamp,
                f"[{level_color}]{level}[/{level_color}]",
                name,
                message
            )

    return Panel(log_table, title="Recent Logs", border_style="red", expand=True)

async def create_logs_page(logs_data, state) -> Layout:
    layout = Layout(name="body")
    layout.split_column(
        Layout(name="filter_bar", size=3),
        Layout(name="logs", ratio=1)
    )

    layout["filter_bar"].update(create_filter_panel(state))
    layout["logs"].update(create_logs_panel(logs_data, state))

    return layout