import asyncio
import time
from typing import Any, Dict, List
from datetime import datetime

import aiohttp
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.style import Style
from prompt_toolkit.input import create_input
import sys
# No longer need rich.prompt.Prompt

# Initialize console
console = Console()
API_URL = "http://127.0.0.1:8080/api"

# Global data cache to reduce API calls
DATA_CACHE = {}
CACHE_LIFETIME = 5  # seconds

# Fixed and complete mapping from API names to friendly names and vice-versa
MODULE_NAME_MAPPING = {
    'mm': 'model_manager',
    'sam': 'sampling_and_aggregation_module',
    'adrm': 'auxiliary_data_retrieval_module',
    'ppm': 'privacy_preserving_module',
    'scpm': 'server_communication_and_enforcement_module'
}

# Create a reverse mapping for easy lookup
FRIENDLY_NAME_MAPPING = {v: k for k, v in MODULE_NAME_MAPPING.items()}


class TuiState:
    def __init__(self, modules: List[str]):
        self.active_tab = "Overview"
        self.selected_module = None
        self.module_selection_index = 0
        self.modules = modules
        self.log_filter = "ALL"
        self.log_search_term = ""
        self.is_searching = False
    
    def set_tab(self, tab_name: str):
        if self.active_tab != tab_name:
            self.active_tab = tab_name
            self.selected_module = None
            self.module_selection_index = 0
            self.log_filter = "ALL"
            self.log_search_term = ""
            self.is_searching = False
    
    def select_module(self, module_name: str):
        self.selected_module = module_name
        
    def deselect_module(self):
        self.selected_module = None
        self.is_searching = False

async def fetch_data(session: aiohttp.ClientSession, endpoint: str) -> Any:
    cache_key = endpoint
    cached_data = DATA_CACHE.get(cache_key)
    if cached_data and (time.time() - cached_data['timestamp']) < CACHE_LIFETIME:
        return cached_data['data']
    
    try:
        async with session.get(f"{API_URL}{endpoint}") as response:
            response.raise_for_status()
            data = await response.json()
            result = data.get("data", data)
            DATA_CACHE[cache_key] = {'data': result, 'timestamp': time.time()}
            return result
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch {endpoint}: {e}"}

def _create_details_table(details: Dict[str, Any]) -> Table:
    table = Table(box=None, show_header=False, padding=0, expand=True)
    table.add_column(style="cyan")
    table.add_column(style="white")

    for key, value in details.items():
        key_name = key.replace('_', ' ').title()
        if isinstance(value, dict):
            table.add_row(f"[bold cyan]{key_name}:[/]", "")
            for sub_key, sub_value in value.items():
                sub_key_name = sub_key.replace('_', ' ').title()
                table.add_row(f"  [cyan]{sub_key_name}:[/]", str(sub_value))
        elif isinstance(value, list):
            value_str = ", ".join(str(item) for item in value) if value else "[]"
            table.add_row(f"[cyan]{key_name}:[/]", value_str)
        else:
            table.add_row(f"[cyan]{key_name}:[/]", str(value))
    return table

def create_overview_panel(overview_data: Dict[str, Any], status_data: Dict[str, Any]) -> Panel:
    if "error" in overview_data or "error" in status_data:
        error_msg = overview_data.get("error", status_data.get("error", "Failed to fetch data."))
        return Panel(f"[bold red]Error:[/] {error_msg}", title="Server Overview", border_style="red")

    connected_clients = status_data.get('connected_clients', 0)
    client_status_text = "[bold yellow]Active, no clients connected[/]"
    if connected_clients > 0:
        client_status_text = f"[bold green]Active with {connected_clients} client(s)[/]"

    overview_text = (
        f"[bold green]Server Status:[/] {overview_data.get('server_status', {}).get('text', 'N/A')}\n"
        f"[bold cyan]Client Manager:[/] {client_status_text}\n"
        f"[bold blue]Uptime:[/] {status_data.get('uptime_seconds', 'N/A')} seconds\n"
        f"[bold cyan]Current Round:[/] {overview_data.get('current_round', 'N/A')}\n"
        f"[bold cyan]Last Aggregation:[/] {overview_data.get('last_aggregation_time', 'N/A')}"
    )
    return Panel(overview_text, title="Server Overview", border_style="green", expand=True)


def create_manager_panel(manager_name: str, data: Dict[str, Any]) -> Panel:
    details = data.get("modules", {}).get(manager_name.replace(' ', '_').lower(), {})
    if not details:
        return Panel(f"[italic]{manager_name} details not available[/]", title=manager_name, border_style="green", expand=True)

    table = _create_details_table(details)
    return Panel(table, title=f"[bold green]{manager_name}[/]", border_style="green", expand=True)

def create_client_health_panel(data: Dict[str, Any]) -> Panel:
    table = Table(border_style="blue", expand=True)
    table.add_column("Client ID", style="cyan", justify="left", ratio=3)
    table.add_column("Status", style="magenta", justify="center")
    table.add_column("Last Heartbeat", style="white", justify="center")
    table.add_column("IP Address", style="yellow", justify="left", ratio=3)

    if "error" in data:
        table.add_row("N/A", data["error"], "N/A", "N/A")
    else:
        clients = data.get("clients", {})
        for client_id, client_info in clients.items():
            status_text = "[green]Active[/]" if client_info.get('status') == "connected" else "[red]Inactive[/]"
            table.add_row(
                client_id,
                status_text,
                str(client_info.get('last_heartbeat', 'N/A')),
                client_info.get('ip_address', 'N/A')
            )
        
    return Panel(table, title="Client Health", border_style="blue", expand=True)

def create_module_details_panel(module_name: str, details: Dict[str, Any]) -> Panel:
    friendly_name = MODULE_NAME_MAPPING.get(module_name, module_name).replace('_', ' ').title()
    table = _create_details_table(details)
    return Panel(table, title=f"[bold yellow]{friendly_name} Details[/]", border_style="magenta", expand=True)

def create_filter_panel(state: 'TuiState') -> Panel:
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

def create_logs_panel(logs: List[Dict[str, str]], state: 'TuiState') -> Panel:
    if isinstance(logs, dict) and "error" in logs:
        return Panel(f"[bold red]Error:[/] {logs['error']}", title="Recent Logs", border_style="red", expand=True)

    logs_text = Text()
    
    # Filter logs based on state
    filtered_logs = []
    log_level_map = {"INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    filter_level_value = log_level_map.get(state.log_filter) if state.log_filter != "ALL" else 0
    search_term = state.log_search_term.lower()

    for log in logs:
        log_level = log.get('levelname', 'INFO').upper()
        log_message = log.get('message', '').lower()
        
        # Check level filter
        if log_level_map.get(log_level, 0) < filter_level_value:
            continue
            
        # Check search term filter
        if search_term and search_term not in log_message:
            continue
            
        filtered_logs.append(log)

    if not filtered_logs:
        logs_text.append("[italic]No logs found with the current filters.[/]", style="dim")
    else:
        for log in filtered_logs:
            timestamp = log.get('asctime', 'N/A')
            level = log.get('levelname', 'INFO')
            message = log.get('message', 'N/A')

            level_color = {
                "ERROR": "bold red",
                "WARNING": "bold yellow"
            }.get(level, "bold green")

            logs_text.append(f"{timestamp} | ", style="white")
            logs_text.append(f"{level}:", style=level_color)
            logs_text.append(f" {message}\n", style="white")

    return Panel(logs_text, title="Recent Logs", border_style="red", expand=True)

def create_header_panel() -> Panel:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_table = Table.grid(expand=True)
    header_table.add_column(justify="left", ratio=3)
    header_table.add_column(justify="right", ratio=1)
    header_table.add_row(
        Text("FLF-2.0 - R25-039", style="bold white"),
        Text(f"{now}", style="bold white")
    )
    return Panel(header_table, border_style="white", padding=(0, 1), expand=True)

def create_navigation_bar(state: TuiState) -> Panel:
    tab_titles = ["Overview", "Client Health", "Modules", "Logs", "TUI Details"]
    tabs_text = Text()
    for i, title in enumerate(tab_titles):
        style = Style(color="cyan", bold=True)
        if title == state.active_tab:
            style = Style(color="green", bold=True, underline=True)
        tabs_text.append(f"({i+1}) {title}", style=style)
        if i < len(tab_titles) - 1:
            tabs_text.append(" | ", style="white")
    
    return Panel(tabs_text, border_style="white", padding=(0, 1), expand=True)

def create_topic_bar(state: TuiState) -> Panel:
    if state.active_tab == "Modules" and state.selected_module:
        title = MODULE_NAME_MAPPING.get(state.selected_module, state.selected_module).replace('_', ' ').title()
        return Panel(f"[bold white]{title}[/] ([bold cyan]b[/] to go back)", border_style="green", padding=(0,1), expand=True)
    else:
        return Panel(f"[bold white]{state.active_tab}[/]", border_style="green", padding=(0,1), expand=True)

def create_module_navigation_bar(state: TuiState) -> Panel:
    if not state.modules:
        return Panel("[italic]No modules available[/]", border_style="green")
        
    nav_text = Text()
    for i, module_name in enumerate(state.modules):
        friendly_name = MODULE_NAME_MAPPING.get(module_name, module_name).replace('_', ' ').title()
        style = Style(color="cyan", bold=True)
        if i == state.module_selection_index:
            style = Style(color="green", bold=True, underline=True)
        nav_text.append(f" {friendly_name} ", style=style)
        if i < len(state.modules) - 1:
            nav_text.append(" | ", style="white")
    
    return Panel(Align.center(nav_text), border_style="green", padding=(0, 1), expand=True)

async def create_overview_page(overview_data, client_health_data, logs_data, status_data, modules_data, state: TuiState) -> Layout:
    layout = Layout(name="body")
    layout.split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=1)
    )

    layout["left"].split_column(
        Layout(name="top_left", size=15),
        Layout(name="bottom_left", ratio=3)
    )

    layout["right"].split_column(
        Layout(name="top_right", ratio=3),
        Layout(name="bottom_right", ratio=1)
    )

    layout["top_left"].split_column(
        Layout(name="server_overview", size=8),
        Layout(name="managers", ratio=1)
    )

    layout["managers"].split_row(
        Layout(name="client_manager"),
        Layout(name="model_manager")
    )
    
    module_panels = [create_module_details_panel(name, details) for name, details in modules_data.items() if "error" not in details]
    
    if module_panels:
        modules_layout = Layout(name="modules_layout")
        if len(module_panels) > 2:
            modules_layout.split_column(
                Layout(name="modules_row_1", ratio=1),
                Layout(name="modules_row_2", ratio=1)
            )
            modules_layout["modules_row_1"].split_row(Layout(module_panels[0]), Layout(module_panels[1]))
            if len(module_panels) > 2:
                modules_layout["modules_row_2"].split_row(Layout(module_panels[2]), Layout(module_panels[3]) if len(module_panels) > 3 else Layout(module_panels[2]))
            layout["top_right"].update(Panel(modules_layout, title="[bold green]Modules[/]", border_style="green", expand=True))
        else:
            layout["top_right"].update(Panel(Columns(module_panels, expand=True), title="[bold green]Modules[/]", border_style="green", expand=True))

    else:
        layout["top_right"].update(Panel("[italic]No modules available[/]", title="Modules", border_style="green"))

    layout["server_overview"].update(create_overview_panel(overview_data, status_data))
    layout["client_manager"].update(create_manager_panel("Client Manager", status_data))
    layout["model_manager"].update(create_manager_panel("Model Manager", status_data))
    layout["bottom_left"].update(create_client_health_panel(client_health_data))
    layout["bottom_right"].update(create_logs_panel(logs_data, state))
    
    return layout

async def create_client_health_page(client_health_data) -> Layout:
    layout = Layout(name="body")
    layout.update(create_client_health_panel(client_health_data))
    return layout

async def create_modules_page(state: TuiState, modules_data: Dict[str, Any]) -> Layout:
    layout = Layout(name="body")
    
    if state.selected_module:
        module_details = modules_data.get(state.selected_module, {})
        layout.update(create_module_details_panel(state.selected_module, module_details))
    else:
        layout.split_column(
            Layout(name="nav_bar", size=3),
            Layout(name="module_details", ratio=1)
        )
        layout["nav_bar"].update(create_module_navigation_bar(state))
        
        current_module_name = state.modules[state.module_selection_index]
        current_module_details = modules_data.get(current_module_name, {})
        layout["module_details"].update(create_module_details_panel(current_module_name, current_module_details))
    
    return layout

async def create_logs_page(logs_data, state: TuiState) -> Layout:
    layout = Layout(name="body")
    layout.split_column(
        Layout(name="filter_bar", size=3),
        Layout(name="logs", ratio=1)
    )
    
    layout["filter_bar"].update(create_filter_panel(state))
    layout["logs"].update(create_logs_panel(logs_data, state))
    
    return layout
    
async def create_tui_details_page() -> Layout:
    layout = Layout(name="body")
    help_text = Text()
    help_text.append("Global Navigation:\n", style="bold green")
    help_text.append("  (1) Overview: View server status, client health, and recent logs.\n")
    help_text.append("  (2) Client Health: Detailed view of connected clients.\n")
    help_text.append("  (3) Modules: Navigate through and view details for each server module.\n")
    help_text.append("  (4) Logs: Filter and search through recent server logs.\n")
    help_text.append("  (5) TUI Details: Display this help information.\n\n")
    help_text.append("Module Page Navigation:\n", style="bold green")
    help_text.append("  [left]/[right] or [p]/[n]: Cycle through modules.\n")
    help_text.append("  [Enter]: Select and view details for the highlighted module.\n")
    help_text.append("  [b]: Go back to the module list.\n\n")
    help_text.append("Logs Page Navigation:\n", style="bold green")
    help_text.append("  [f]: Cycle through log level filters (ALL, INFO, WARNING, ERROR).\n")
    help_text.append("  [s]: Enter search mode to filter logs by a term.\n")
    help_text.append("  [r]: Reset log filters and clear the search term.\n\n")
    help_text.append("Global Actions:\n", style="bold green")
    help_text.append("  [q]: Quit the TUI.\n", style="bold red")

    panel = Panel(
        help_text,
        title="[bold blue]TUI Navigation and Controls[/]",
        border_style="blue",
        expand=True
    )
    layout.update(panel)
    return layout

async def create_main_layout(state: TuiState) -> Layout:
    async with aiohttp.ClientSession() as session:
        overview_data = await fetch_data(session, "/overview")
        client_health_data = await fetch_data(session, "/client_health")
        logs_data = await fetch_data(session, "/logs")
        status_data = await fetch_data(session, "/status")
        
        modules_status_data = {}
        for module_name in state.modules:
            modules_status_data[module_name] = await fetch_data(session, f"/module_status/{module_name}")

    layout = Layout(name="root")
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="nav", size=3),
        Layout(name="topic", size=3),
        Layout(name="body", ratio=1)
    )
    
    layout["header"].update(create_header_panel())
    layout["nav"].update(create_navigation_bar(state))
    layout["topic"].update(create_topic_bar(state))

    if state.active_tab == "Overview":
        layout["body"].update(await create_overview_page(overview_data, client_health_data, logs_data, status_data, modules_status_data, state))
    elif state.active_tab == "Client Health":
        layout["body"].update(await create_client_health_page(client_health_data))
    elif state.active_tab == "Modules":
        layout["body"].update(await create_modules_page(state, modules_status_data))
    elif state.active_tab == "Logs":
        layout["body"].update(await create_logs_page(logs_data, state))
    elif state.active_tab == "TUI Details":
        layout["body"].update(await create_tui_details_page())

    return layout

async def main_tui():
    async with aiohttp.ClientSession() as session:
        status_data = await fetch_data(session, "/status")
    
    modules = sorted(list(MODULE_NAME_MAPPING.keys()))

    state = TuiState(modules)
    
    input_thread = create_input(sys.stdin)
    
    async def read_keys():
        with input_thread.raw_mode():
            while True:
                keys = input_thread.read_keys()
                if keys:
                    key = keys[0].key

                    if state.is_searching:
                        if key == 'enter' or key == 'escape':
                            state.is_searching = False
                        elif key == 'backspace':
                            state.log_search_term = state.log_search_term[:-1]
                        elif len(key) == 1:
                            state.log_search_term += key
                        
                    else:
                        if key == 'q' or key == 'Q':
                            return "quit"
                        
                        if key == '1':
                            state.set_tab("Overview")
                        elif key == '2':
                            state.set_tab("Client Health")
                        elif key == '3':
                            state.set_tab("Modules")
                        elif key == '4':
                            state.set_tab("Logs")
                        elif key == '5':
                            state.set_tab("TUI Details")
                        elif state.active_tab == "Modules":
                            num_modules = len(state.modules)
                            if state.selected_module is None:
                                if key == 'left' or key == 'p':
                                    state.module_selection_index = (state.module_selection_index - 1 + num_modules) % num_modules
                                elif key == 'right' or key == 'n':
                                    state.module_selection_index = (state.module_selection_index + 1) % num_modules
                                elif key == 'enter' and num_modules > 0:
                                    state.select_module(state.modules[state.module_selection_index])
                            elif key == 'b' or key == 'B':
                                state.deselect_module()
                        elif state.active_tab == "Logs":
                            if key == 'f':
                                log_levels = ["ALL", "INFO", "WARNING", "ERROR"]
                                current_index = log_levels.index(state.log_filter)
                                state.log_filter = log_levels[(current_index + 1) % len(log_levels)]
                            elif key == 's':
                                state.is_searching = True
                            elif key == 'r':
                                state.log_filter = "ALL"
                                state.log_search_term = ""
                
                await asyncio.sleep(0.01)

    live = Live(await create_main_layout(state), screen=True, refresh_per_second=10, vertical_overflow="visible")
    
    key_reader_task = asyncio.create_task(read_keys())

    with live:
        while True:
            live.update(await create_main_layout(state))
            await asyncio.sleep(0.1)
            
            if key_reader_task.done():
                if key_reader_task.result() == "quit":
                    break
    
    input_thread.close()
    console.print("[bold green]TUI stopped.[/]")

if __name__ == "__main__":
    asyncio.run(main_tui())