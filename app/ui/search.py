""" This is helper module for search features """
from app.ui.main_helper import get_base_model


class SearchProvider:
    def __init__(self, srv_view, fav_view, bqs_view, services, bouquets):
        self._paths = []
        self._current_index = -1
        self._max_indexes = 0
        self._srv_view = srv_view
        self._fav_view = fav_view
        self._bqs_view = bqs_view
        self._services = services
        self._bouquets = bouquets

    def search(self, text, ):
        self._current_index = -1
        self._paths.clear()
        for view in self._srv_view, self._fav_view:
            model = get_base_model(view.get_model())
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

    def on_search_down(self):
        if self._current_index < self._max_indexes:
            self._current_index += 1
            self.scroll_to(self._current_index)

    def on_search_up(self):
        if self._current_index > -1:
            self._current_index -= 1
            self.scroll_to(self._current_index)


if __name__ == "__main__":
    pass
