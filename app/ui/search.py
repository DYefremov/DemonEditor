""" This is helper module for search features """
from app.commons import run_with_delay


class SearchProvider:
    def __init__(self, view, entry, down_button, up_button, columns=None):
        self._paths = []
        self._current_index = -1
        self._max_indexes = 0
        self._view = view
        self._entry = entry
        self._up_button = up_button
        self._down_button = down_button
        self._columns = columns

        entry.connect("changed", self.on_search)
        self._down_button.connect("clicked", self.on_search_down)
        self._up_button.connect("clicked", self.on_search_up)

    def search(self, text):
        self._current_index = -1
        self._paths.clear()
        model = self._view.get_model()
        selection = self._view.get_selection()
        if not selection:
            return

        selection.unselect_all()
        if not text:
            return

        text = text.upper()
        for r in model:
            data = [r[i] for i in self._columns] if self._columns else r[:]
            if next((s for s in data if text in str(s).upper()), False):
                path = r.path
                selection.select_path(r.path)
                self._paths.append(path)

        self._max_indexes = len(self._paths) - 1
        if self._max_indexes > 0:
            self.on_search_down()

        self.update_navigation_buttons()

    def scroll_to(self, index):
        self._view.scroll_to_cell(self._paths[index], None)
        self.update_navigation_buttons()

    def on_search_down(self, button=None):
        if self._current_index < self._max_indexes:
            self._current_index += 1
            self.scroll_to(self._current_index)

    def on_search_up(self, button=None):
        if self._current_index > -1:
            self._current_index -= 1
            self.scroll_to(self._current_index)

    def update_navigation_buttons(self):
        self._up_button.set_sensitive(self._current_index > 0)
        self._down_button.set_sensitive(self._current_index < self._max_indexes)

    @run_with_delay(1)
    def on_search(self, entry):
        self.search(entry.get_text())

    def on_search_toggled(self, action, value=None):
        self._entry.grab_focus() if action.get_active() else self._entry.set_text("")


if __name__ == "__main__":
    pass
