""" This is helper module for search features """


class SearchProvider:
    def __init__(self, views, down_button, up_button):
        self._paths = []
        self._current_index = -1
        self._max_indexes = 0
        self._views = views
        self._up_button = up_button
        self._down_button = down_button

    def search(self, text):
        self._current_index = -1
        self._paths.clear()
        for view in self._views:
            model = view.get_model()
            selection = view.get_selection()
            selection.unselect_all()
            if not text:
                continue

            text = text.upper()
            for r in model:
                if text in str(r[:]).upper():
                    path = r.path
                    selection.select_path(r.path)
                    self._paths.append((view, path))

        self._max_indexes = len(self._paths) - 1
        if self._max_indexes > 0:
            self.on_search_down()

    def scroll_to(self, index):
        view, path = self._paths[index]
        view.scroll_to_cell(path, None)
        self.update_navigation_buttons()

    def on_search_down(self):
        if self._current_index < self._max_indexes:
            self._current_index += 1
            self.scroll_to(self._current_index)

    def on_search_up(self):
        if self._current_index > -1:
            self._current_index -= 1
            self.scroll_to(self._current_index)

    def update_navigation_buttons(self):
        self._up_button.set_sensitive(self._current_index > 0)
        self._down_button.set_sensitive(self._current_index < self._max_indexes)


if __name__ == "__main__":
    pass
