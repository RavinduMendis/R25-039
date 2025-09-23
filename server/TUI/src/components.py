from datetime import datetime
from typing import Any, Dict, List, Optional
import math
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.style import Style
from .config import MODULE_NAME_MAPPING
from .utils import sanitize_series, moving_average, line_points

console = Console()

def create_details_table(details: Dict[str, Any]) -> Table:
    table = Table(box=None, show_header=False, padding=0, expand=True)
    table.add_column(style="cyan", ratio=1)
    table.add_column(style="white", ratio=2)

    for key, value in details.items():
        key_name = key.replace('_', ' ').title()
        if isinstance(value, dict):
            sub_text = "\n".join([f"  {k.replace('_', ' ').title()}: {v}" for k,v in value.items()])
            table.add_row(f"[bold]{key_name}:[/]", sub_text)
        elif isinstance(value, list):
            value_str = ", ".join(str(item) for item in value) if value else "[]"
            table.add_row(f"[bold]{key_name}:[/]", value_str)
        else:
            table.add_row(f"[bold]{key_name}:[/]", str(value))
    return table

def create_header_panel() -> Panel:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_table = Table.grid(expand=True)
    header_table.add_column(justify="left", ratio=3)
    header_table.add_column(justify="right", ratio=1)
    header_table.add_row(
        Text("Federated Learning Framework v2.0"),
        Text(f"{now}", style="bold white")
    )
    return Panel(header_table, border_style="blue", padding=(0, 1), expand=True)

def create_navigation_bar(state) -> Panel:
    tab_titles = ["Overview", "Model Manager", "Client Health", "Modules", "Logs", "TUI Details"]
    key_map = {title: i + 1 for i, title in enumerate(tab_titles)}
    
    tabs_text = Text()
    for i, title in enumerate(tab_titles):
        style = Style(color="cyan")
        if title == state.active_tab:
            style = Style(color="green", bold=True, underline=True)
        tabs_text.append(f"({key_map[title]}) {title}", style=style)

        if i < len(tab_titles) - 1:
            tabs_text.append(" | ", style="white")

    return Panel(Align.center(tabs_text), border_style="white", padding=(0, 1), expand=True)

def create_topic_bar(state) -> Panel:
    if state.active_tab == "Modules" and state.selected_module:
        title = MODULE_NAME_MAPPING.get(state.selected_module, state.selected_module).replace('_', ' ').title()
        return Panel(f"[white]{title}[/] ([cyan]b[/] to go back)", border_style="green", padding=(0,1), expand=True)
    elif state.active_tab == "Model Manager":
        nav_text = "[white]Model Manager[/] | "
        if state.show_plot:
            nav_text += "[cyan]t[/]: Table | [cyan]g[/]: Grid | [cyan]a[/]: Avg | [cyan]d[/]: Data | [cyan]+/-[/]: Zoom"
        else:
            nav_text += "[cyan]p[/]: Plot | [cyan]↑/↓[/]: Scroll"
        return Panel(nav_text, border_style="green", padding=(0,1), expand=True)
    else:
        return Panel(f"[white]{state.active_tab}[/]", border_style="green", padding=(0,1), expand=True)

def create_ascii_plot(
    metrics_history: List[Dict],
    plot_type: str = "accuracy",
    *,
    width: Optional[int] = None,
    height: int = 14,
    show_grid: bool = True,
    show_avg: bool = True,
    show_raw: bool = False,
    window: int = 100
) -> Group:
    """High-clarity ASCII plot that returns a renderable Group."""
    if not metrics_history:
        return Group(Text("No data available for plotting", style="italic"))

    plot_text = Text()
    total_width = width or max(50, min(100, console.size.width - 8))
    y_axis_w = 8
    inner_w = max(10, total_width - (y_axis_w + 2))
    inner_h = max(6, height - 4)

    rounds, raw_vals = [], []
    for m in metrics_history:
        rounds.append(m.get('round', len(rounds) + 1))
        metrics_data = m.get('metrics', {})
        raw_vals.append(metrics_data.get(plot_type, None))

    vals = sanitize_series(raw_vals)

    if window and len(vals) > window:
        vals, rounds = vals[-window:], rounds[-window:]

    valid = [v for v in vals if not math.isnan(v)]
    if not valid:
        return Group(Text(f"No valid numerical values for '{plot_type}' to plot", style="italic"))
        
    vmin, vmax = min(valid), max(valid)
    if math.isclose(vmin, vmax): vmin, vmax = vmin - 0.5, vmax + 0.5

    def ymap(v: float) -> int:
        ratio = (v - vmin) / (vmax - vmin) if (vmax - vmin) != 0 else 0.5
        return int(round((inner_h - 1) * (1 - ratio)))

    grid = [[' ' for _ in range(inner_w)] for _ in range(inner_h)]

    if show_grid:
        for frac in (0.25, 0.5, 0.75):
            r = int(round(frac * (inner_h - 1)))
            if 0 <= r < inner_h:
                for x in range(inner_w): grid[r][x] = '·'

    n = len(vals)
    def xmap(i: int) -> int:
        if n <= 1: return inner_w // 2
        return int(round(i * (inner_w - 1) / (n - 1)))

    if show_raw:
        prev = None
        for i, v in enumerate(vals):
            if math.isnan(v):
                prev = None; continue
            x, y = xmap(i), ymap(v)
            if prev is None:
                if 0 <= y < inner_h and 0 <= x < inner_w: grid[y][x] = '●'
            else:
                x0, y0 = prev
                for (xx, yy) in line_points(x0, y0, x, y):
                    if 0 <= yy < inner_h and 0 <= xx < inner_w:
                        grid[yy][xx] = '⣿' if grid[yy][xx] != '·' else '╪'
            prev = (x, y)

    if show_avg and n >= 3:
        ma = moving_average(vals, window=max(3, min(11, n // 8 or 3)))
        prev = None
        for i, v in enumerate(ma):
            if math.isnan(v):
                prev = None; continue
            x, y = xmap(i), ymap(v)
            if prev is not None:
                x0, y0 = prev
                for (xx, yy) in line_points(x0, y0, x, y):
                    if 0 <= yy < inner_h and 0 <= xx < inner_w:
                        grid[yy][xx] = '━'
            prev = (x, y)

    title_color = "bright_green" if plot_type == "accuracy" else "bright_red"
    y_axis_unit = " (%)" if plot_type == "accuracy" else ""
    y_axis_label = f" {plot_type.title()}{y_axis_unit} "
    
    title_bar = Text(" " * y_axis_w + "┌" + "─", style="dim")
    title_bar.append(y_axis_label, style="bold white on black")
    title_bar.append("─" * (inner_w - len(y_axis_label) - 1) + "┐", style="dim")
    plot_text.append(title_bar)
    plot_text.append("\n")

    y_labels = {0: vmax, inner_h // 2: (vmin + vmax) / 2, inner_h - 1: vmin}
    for r in range(inner_h):
        label_value = y_labels.get(r)
        lbl_str = f"{label_value:.3g}".rjust(y_axis_w) if label_value is not None else " " * y_axis_w
        
        plot_text.append(lbl_str, style="cyan"); plot_text.append("│", style="dim")
        
        row_text = Text()
        for char in grid[r]:
            if char == '━': row_text.append(char, style="bright_cyan")
            elif char in '⣿╪●': row_text.append(char, style=title_color)
            else: row_text.append(char, style="dim")
        plot_text.append(row_text)
        plot_text.append("│\n", style="dim")

    plot_text.append(" " * y_axis_w + "└" + "─" * inner_w + "┘\n", style="dim")
    
    if rounds:
        first, last = rounds[0], rounds[-1]
        x_label_str = f"{first}".ljust(inner_w - len(str(last))) + f"{last}"
        plot_text.append(" " * (y_axis_w + 1) + x_label_str + "\n", style="cyan")
        x_axis_label = "Round"
        plot_text.append(" " * (y_axis_w + 1 + (inner_w - len(x_axis_label)) // 2) + x_axis_label + "\n", style="white")

    legend_items = []
    if show_avg: legend_items.append("[bright_cyan]━ Trend (Avg)[/]")
    if show_raw: legend_items.append(f"[{title_color}]⣿ Raw Data[/]")
    
    stats_text = f"Min: {vmin:.3g} | Max: {vmax:.3g} | Latest: {valid[-1]:.3g}"
    
    footer_table = Table.grid(expand=True, padding=(0,1))
    footer_table.add_column(ratio=1)
    footer_table.add_column(justify="right")
    footer_table.add_row(" ".join(legend_items), stats_text)
    
    return Group(plot_text, footer_table)