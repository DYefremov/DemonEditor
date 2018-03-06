""" This is helper module for search features """
from app.ui.main_helper import get_base_model


def search(text, srv_view, fav_view, bqs_view, services, bouquets):
    for view in srv_view, fav_view:
        model = get_base_model(view.get_model())
        selection = view.get_selection()
        selection.unselect_all()
        if not text:
            continue
        paths = []
        text = text.upper()
        for r in model:
            if text in str(r[:]).upper():
                path = r.path
                selection.select_path(r.path)
                paths.append(path)

        if paths:
            view.scroll_to_cell(paths[0], None)


class SearchProvider:
    def __init__(self):
        pass


if __name__ == "__main__":
    pass
