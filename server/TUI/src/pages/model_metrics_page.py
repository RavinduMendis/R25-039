from typing import Dict, Any, List
import math
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from rich.text import Text
from ..components import create_ascii_plot

console = Console()

def create_scrollable_metrics_table(metrics_history: List[Dict], scroll_index: int, max_rows: int = 15) -> Table:
    """Create a scrollable metrics table"""
    table = Table(border_style="magenta", expand=True)
    table.add_column("Round", justify="center")
    table.add_column("Accuracy (%)", style="green", justify="center")
    table.add_column("Loss", style="red", justify="center")
    table.add_column("Agg. Method", style="yellow", justify="center")
    table.add_column("Timestamp", style="white", justify="center")

    if not metrics_history:
        table.add_row("[italic]No metrics history available yet.[/]", "", "", "", "")
        return table

    total_rows = len(metrics_history)
    start_idx = max(0, min(scroll_index, total_rows - max_rows))
    end_idx = min(start_idx + max_rows, total_rows)

    visible_metrics = metrics_history[start_idx:end_idx]

    for metric_entry in visible_metrics:
        metrics_data = metric_entry.get('metrics', {})
        accuracy = metrics_data.get('accuracy', 0.0)
        loss = metrics_data.get('loss', 0.0)
        
        # FIXED: Get 'aggregation_method' from the correct level (metric_entry).
        agg_method = metric_entry.get('aggregation_method', 'N/A')

        accuracy_str = f"{float(accuracy):.2f}" if isinstance(accuracy, (int, float)) and math.isfinite(accuracy) else "N/A"
        loss_str = f"{float(loss):.4f}" if isinstance(loss, (int, float)) and math.isfinite(loss) else "N/A"

        table.add_row(
            str(metric_entry.get("round", "N/A")), accuracy_str, loss_str,
            agg_method, str(metric_entry.get('timestamp', 'N/A'))
        )

    if total_rows > max_rows:
        table.caption = f"[dim]Showing rows {start_idx + 1}-{end_idx} of {total_rows}. Use ↑/↓ to scroll.[/dim]"

    return table

def create_model_manager_page(metrics_details: Dict[str, Any], state) -> Layout:
    layout = Layout(name="body")

    if "error" in metrics_details:
        panel = Panel(f"[bold red]Error:[/] {metrics_details['error']}", title="Model Manager", border_style="red", expand=True)
        layout.update(panel)
        return layout

    metrics_history = metrics_details.get("metrics_history", [])
    
    best_accuracy = 0.0
    best_loss = float('inf')
    if metrics_history:
        valid_accuracies = [m.get('metrics', {}).get('accuracy', 0.0) for m in metrics_history]
        valid_losses = [m.get('metrics', {}).get('loss', float('inf')) for m in metrics_history]
        if valid_accuracies: best_accuracy = max(valid_accuracies)
        if valid_losses: best_loss = min(valid_losses)

    model_version = metrics_details.get("model_version", "N/A")
    convergence_status = metrics_details.get("convergence_status", "N/A")
    last_update = metrics_details.get("last_model_update", "N/A")
    progress_data = metrics_details.get("training_progress", {})
    current_round, total_rounds = progress_data.get("current_round", 0), progress_data.get("total_rounds", 0)
    progress_percent = progress_data.get("progress_percentage", 0.0)

    # --- Panels are defined here for use in the table view ---
    progress_panel = Panel(f"Round {current_round}/{total_rounds} ({progress_percent:.2f}%)", title="Training Progress", border_style="cyan")
    
    status_text = (
        f"[white]Model Version:[/] [cyan]{model_version}[/]\n"
        f"[white]Convergence Status:[/] [cyan]{convergence_status}[/]\n"
        f"[white]Last Update:[/] [cyan]{last_update}[/]"
    )
    performance_text = (
         f"[bold]Best Performance[/]\n"
         f"  [green]Accuracy:[/] {best_accuracy:.2f}%\n"
         f"  [red]Loss:[/] {best_loss:.4f}"
    )
    status_table = Table.grid(expand=True)
    status_table.add_column(ratio=2)
    status_table.add_column(ratio=2)
    status_table.add_row(Text.from_markup(status_text), Text.from_markup(performance_text))
    status_panel = Panel(status_table, title="Model Status", border_style="yellow")

    if state.show_plot:
        # --- PLOT-ONLY VIEW ---
        # The entire screen is split horizontally to show only the two plots.
        layout.split_row(Layout(name="accuracy_plot"), Layout(name="loss_plot"))

        # --- MODIFIED SECTION START ---
        
        # Define overhead for external headers and the panel's own border.
        external_headers_height = 5  # Space for title, tabs, and menu bars.
        panel_vertical_overhead = 2  # For panel's top/bottom border.
        panel_horizontal_overhead = 4 # For panel's border and padding.

        # Height is the full console height, minus the headers and the panel's own overhead.
        available_h = max(10, console.size.height - external_headers_height - panel_vertical_overhead)
        
        # Width is half the console width, minus the panel's total horizontal overhead.
        available_w = max(10, (console.size.width // 2) - panel_horizontal_overhead)
        
        # --- MODIFIED SECTION END ---
        
        accuracy_plot = create_ascii_plot(
            metrics_history, "accuracy", width=available_w, height=available_h, 
            show_grid=state.show_grid, show_avg=state.show_avg, show_raw=state.show_raw_data, window=state.plot_window
        )
        loss_plot = create_ascii_plot(
            metrics_history, "loss", width=available_w, height=available_h, 
            show_grid=state.show_grid, show_avg=state.show_avg, show_raw=state.show_raw_data, window=state.plot_window
        )
        
        # Update the layouts with Panels that now include titles for clarity.
        layout["accuracy_plot"].update(Panel(accuracy_plot, title="Accuracy (%)", border_style="green"))
        layout["loss_plot"].update(Panel(loss_plot, title="Loss", border_style="red"))
    else:
        # --- TABLE VIEW ---
        # This view includes the status and progress panels above the metrics table.
        layout.split_column(
            Layout(name="top_info", size=7),
            Layout(name="metrics_table", ratio=1)
        )
        layout["top_info"].split_column(Layout(name="status", size=6), Layout(name="progress", size=3))
        
        scrollable_table = create_scrollable_metrics_table(metrics_history, state.metrics_scroll_index)
        layout["metrics_table"].update(Panel(scrollable_table, title="[bold]Metrics History[/] (p: plot, ↑/↓: scroll)"))
        
        # Update the status and progress layouts, which only exist in this view.
        layout["status"].update(status_panel)
        layout["progress"].update(progress_panel)

    return layout