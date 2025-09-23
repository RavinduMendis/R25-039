from typing import Dict, Any
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.style import Style
from rich.table import Table
from rich.console import Group
from ..config import MODULE_NAME_MAPPING, FRIENDLY_NAME_MAPPING
from ..components import create_details_table

def create_module_navigation_bar(state) -> Panel:
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

def _render_aggregation_summary(summary: Dict[str, Any]) -> Group:
    """Renders the first and last aggregation summary."""
    groups = []
    for key, details in summary.items():
        if not details:
            continue
        title = "First Aggregation" if key == 'first_aggregation' else "Last Aggregation"
        
        metrics = details.get('metrics', {})
        metrics_text = ", ".join([f"{k}: {v}" for k, v in metrics.items()])
        
        summary_text = (
            f"[bold green]{title}[/]\n"
            f"  [bold]Version:[/] {details.get('version', 'N/A')}\n"
            f"  [bold]Round:[/] {details.get('round', 'N/A')}\n"
            f"  [bold]Timestamp:[/] {details.get('timestamp', 'N/A')}\n"
            f"  [bold]Metrics:[/] {metrics_text}"
        )
        groups.append(Panel(Text.from_markup(summary_text), border_style="dim", expand=True))
    return Group(*groups)

def create_module_details_panel(module_name: str, details: Dict[str, Any]) -> Panel:
    friendly_name = MODULE_NAME_MAPPING.get(module_name, module_name).replace('_', ' ').title()
    
    details_copy = details.copy()
    special_content = []

    # Handle special rendering for complex data structures
    if module_name == 'adrm' and 'blocked_client_details' in details_copy:
        blocked_clients = details_copy.pop('blocked_client_details')
        if blocked_clients:
            blocked_table = Table(title="[bold red]Currently Blocked Clients[/]", border_style="red", expand=True)
            blocked_table.add_column("Client ID", style="cyan")
            blocked_table.add_column("Reason", style="white", ratio=2)
            blocked_table.add_column("Blocked At", style="yellow")
            for cid, info in blocked_clients.items():
                blocked_table.add_row(cid, info.get('reason', 'N/A'), info.get('block_timestamp', 'N/A'))
            special_content.append(blocked_table)

    if module_name == 'orchestrator' and 'failed_updates_log' in details_copy:
        failed_logs = details_copy.pop('failed_updates_log')
        if failed_logs:
            failed_table = Table(title="[bold yellow]Client Update Failures[/]", border_style="yellow", expand=True)
            failed_table.add_column("Client ID", style="cyan")
            failed_table.add_column("Round", style="white")
            failed_table.add_column("Reason", style="red")
            failed_table.add_column("Timestamp", style="dim")
            for cid, entries in failed_logs.items():
                for entry in entries:
                    failed_table.add_row(cid, str(entry.get('round')), entry.get('reason'), entry.get('timestamp'))
            special_content.append(failed_table)

    if module_name == 'mm' and 'aggregation_summary' in details_copy:
        summary = details_copy.pop('aggregation_summary')
        if summary and (summary.get('first_aggregation') or summary.get('last_aggregation')):
            special_content.append(_render_aggregation_summary(summary))
    
    main_table = create_details_table(details_copy)
    content = Group(main_table, *special_content)
    
    return Panel(content, title=f"[bold yellow]{friendly_name} Details[/]", border_style="magenta", expand=True)

async def create_modules_page(state, modules_data: Dict[str, Any]) -> Layout:
    layout = Layout(name="body")

    # Handle case where API returns error for a specific module
    if state.selected_module and "error" in modules_data.get(state.selected_module, {}):
         error_panel = Panel(
            f"[bold red]Error fetching data for {state.selected_module}:[/]\n{modules_data[state.selected_module]['error']}",
            title="[bold red]Error[/]",
            border_style="red"
        )
         layout.update(error_panel)
         return layout

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