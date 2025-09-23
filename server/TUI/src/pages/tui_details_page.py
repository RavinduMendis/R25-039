from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

async def create_tui_details_page() -> Layout:
    layout = Layout(name="body")
    help_text = Text()
    
    # FIXED: Corrected navigation keys and names to match input_handler.py and other files
    help_text.append("Global Navigation:\n", style="bold green")
    help_text.append("  (1) Overview: Main dashboard with server status and summaries.\n")
    help_text.append("  (2) Model Manager: Detailed model performance, history, and plots.\n")
    help_text.append("  (3) Client Health: Detailed view of all connected clients.\n")
    help_text.append("  (4) Modules: Inspect the status of individual server modules.\n")
    help_text.append("  (5) Logs: Filter and search through recent server logs.\n")
    help_text.append("  (6) TUI Details: Display this help information.\n\n")
    
    help_text.append("Module Page Navigation:\n", style="bold green")
    help_text.append("  [left]/[right] or [p]/[n]: Cycle through modules.\n")
    help_text.append("  [Enter]: Select and view details for the highlighted module.\n")
    help_text.append("  [b]: Go back to the module list.\n\n")
    
    help_text.append("Logs Page Navigation:\n", style="bold green")
    help_text.append("  [f]: Cycle through log level filters (ALL, INFO, WARNING, ERROR).\n")
    help_text.append("  [s]: Enter search mode to filter logs by a term.\n")
    help_text.append("  [r]: Reset log filters and clear the search term.\n\n")
    
    help_text.append("Model Manager Page Navigation:\n", style="bold green")
    help_text.append("  [p]: Plot view (shows trends).  [t]: Table view.\n")
    help_text.append("  [g]: Toggle gridlines.  [a]: Toggle moving average overlay.\n")
    help_text.append("  [+]/[-]: Zoom plot window (how many recent points to show).\n")
    help_text.append("  [↑]/[↓]: Scroll up/down in table view.\n\n")
    
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