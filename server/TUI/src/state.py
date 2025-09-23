from typing import List

class TuiState:
    def __init__(self, modules: List[str]):
        self.active_tab = "Overview"
        self.selected_module = None
        self.module_selection_index = 0
        self.modules = modules
        self.log_filter = "ALL"
        self.log_search_term = ""
        self.is_searching = False
        # Model metrics page state
        self.metrics_scroll_index = 0
        self.show_plot = False
        # Plot options
        self.plot_window = 100
        self.show_grid = True
        self.show_avg = True
        # New state to control visibility of raw data points
        self.show_raw_data = False

    def set_tab(self, tab_name: str):
        if self.active_tab != tab_name:
            self.active_tab = tab_name
            self.selected_module = None
            self.module_selection_index = 0
            self.log_filter = "ALL"
            self.log_search_term = ""
            self.is_searching = False
            # Reset model metrics state
            self.metrics_scroll_index = 0
            self.show_plot = False

    def select_module(self, module_name: str):
        self.selected_module = module_name

    def deselect_module(self):
        self.selected_module = None
        self.is_searching = False