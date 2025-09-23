import asyncio
import sys
from prompt_toolkit.input import create_input

class InputHandler:
    def __init__(self, state):
        self.state = state
        self.input_thread = create_input(sys.stdin)

    async def read_keys(self):
        with self.input_thread.raw_mode():
            while True:
                keys = self.input_thread.read_keys()
                if keys:
                    key = keys[0].key

                    if self.state.is_searching:
                        if key == 'enter' or key == 'escape':
                            self.state.is_searching = False
                        elif key == 'backspace':
                            self.state.log_search_term = self.state.log_search_term[:-1]
                        elif len(key) == 1:
                            self.state.log_search_term += key
                    else:
                        if key in ('q', 'Q'):
                            return "quit"

                        if key == '1': self.state.set_tab("Overview")
                        elif key == '2': self.state.set_tab("Model Manager")
                        elif key == '3': self.state.set_tab("Client Health")
                        elif key == '4': self.state.set_tab("Modules")
                        elif key == '5': self.state.set_tab("Logs")
                        elif key == '6': self.state.set_tab("TUI Details")

                        elif self.state.active_tab == "Modules":
                            self._handle_modules_navigation(key)
                        elif self.state.active_tab == "Logs":
                            self._handle_logs_navigation(key)
                        elif self.state.active_tab == "Model Manager":
                            self._handle_model_manager_navigation(key)

                await asyncio.sleep(0.01)

    def _handle_modules_navigation(self, key):
        num_modules = len(self.state.modules)
        if self.state.selected_module is None and num_modules > 0:
            if key in ('left', 'p'):
                self.state.module_selection_index = (self.state.module_selection_index - 1) % num_modules
            elif key in ('right', 'n'):
                self.state.module_selection_index = (self.state.module_selection_index + 1) % num_modules
            elif key == 'enter':
                self.state.select_module(self.state.modules[self.state.module_selection_index])
        elif key in ('b', 'B', 'escape'):
            self.state.deselect_module()

    def _handle_logs_navigation(self, key):
        if key == 'f':
            log_levels = ["ALL", "INFO", "WARNING", "ERROR"]
            current_index = log_levels.index(self.state.log_filter)
            self.state.log_filter = log_levels[(current_index + 1) % len(log_levels)]
        elif key == 's':
            self.state.is_searching = True
        elif key == 'r':
            self.state.log_filter = "ALL"
            self.state.log_search_term = ""

    def _handle_model_manager_navigation(self, key):
        if key == 'p': self.state.show_plot = True
        elif key == 't': self.state.show_plot = False
        elif key == 'g' and self.state.show_plot: self.state.show_grid = not self.state.show_grid
        elif key == 'a' and self.state.show_plot: self.state.show_avg = not self.state.show_avg
        elif key == 'd' and self.state.show_plot: self.state.show_raw_data = not self.state.show_raw_data
        elif key == '+' and self.state.show_plot: self.state.plot_window = max(20, int(self.state.plot_window * 0.8))
        elif key == '-' and self.state.show_plot: self.state.plot_window = min(2000, int(self.state.plot_window * 1.25))
        elif key == 'up' and not self.state.show_plot: self.state.metrics_scroll_index = max(0, self.state.metrics_scroll_index - 1)
        elif key == 'down' and not self.state.show_plot: self.state.metrics_scroll_index += 1

    def close(self):
        self.input_thread.close()