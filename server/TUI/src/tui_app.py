import asyncio
import aiohttp
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel

from .config import MODULE_NAME_MAPPING
from .state import TuiState
from .api_client import fetch_data
from .input_handler import InputHandler
from .components import create_header_panel, create_navigation_bar, create_topic_bar
from .pages.overview_page import create_overview_page
from .pages.client_health_page import create_client_health_page
from .pages.modules_page import create_modules_page
from .pages.logs_page import create_logs_page
from .pages.model_metrics_page import create_model_manager_page
from .pages.tui_details_page import create_tui_details_page

console = Console()

async def create_main_layout(state: TuiState) -> Layout:
    async with aiohttp.ClientSession() as session:
        tasks = {
            "overview": fetch_data(session, "/overview"),
            "model_metrics": fetch_data(session, "/model/metrics_details"),
            "client_health": fetch_data(session, "/client_health"),
            "logs": fetch_data(session, "/logs"),
            "status": fetch_data(session, "/status"),
        }
        
        all_module_keys = list(MODULE_NAME_MAPPING.keys())
        for module_name in all_module_keys:
             tasks[f"module_{module_name}"] = fetch_data(session, f"/module_status/{module_name}")
        
        results = await asyncio.gather(*tasks.values())
        data = dict(zip(tasks.keys(), results))
        
        if "error" in data.get("status", {}):
            error_panel = Panel(
                f"[bold red]Error connecting to server: {data['status']['error']}[/]",
                title="[bold red]Connection Error[/]",
                border_style="red"
            )
            error_layout = Layout()
            error_layout.update(error_panel)
            return error_layout

    overview_data = data["overview"]
    model_metrics_data = data["model_metrics"]
    client_health_data = data["client_health"]
    logs_data = data["logs"]
    status_data = data["status"]
    modules_status_data = {name: data.get(f"module_{name}", {}) for name in all_module_keys}

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

    active_tab = state.active_tab
    if active_tab == "Overview":
        body_content = await create_overview_page(overview_data, client_health_data, logs_data, status_data, modules_status_data, state)
    elif active_tab == "Model Manager":
        body_content = create_model_manager_page(model_metrics_data, state)
    elif active_tab == "Client Health":
        body_content = await create_client_health_page(client_health_data)
    elif active_tab == "Modules":
        body_content = await create_modules_page(state, modules_status_data)
    elif active_tab == "Logs":
        body_content = await create_logs_page(logs_data, state)
    elif active_tab == "TUI Details":
        body_content = await create_tui_details_page()
    else:
        body_content = Layout()

    layout["body"].update(body_content)
    return layout

async def main_tui():
    # FIXED: Filter out 'orchestrator' from the list passed to the Modules page
    modules_for_tab = sorted([k for k in MODULE_NAME_MAPPING.keys() if k not in ['mm', 'orchestrator']])
    state = TuiState(modules_for_tab)
    
    async with aiohttp.ClientSession() as session:
        status_data = await fetch_data(session, "/status")
        if "error" in status_data:
            console.print(f"[bold red]Error connecting to server: {status_data['error']}[/]")
            return
    
    input_handler = InputHandler(state)
    key_reader_task = asyncio.create_task(input_handler.read_keys())

    with Live(await create_main_layout(state), screen=True, refresh_per_second=4, vertical_overflow="crop") as live:
        while not key_reader_task.done():
            live.update(await create_main_layout(state))
            await asyncio.sleep(0.25)
        
        if key_reader_task.result() == "quit":
            pass

    input_handler.close()
    console.print("[bold green]TUI stopped.[/]")

