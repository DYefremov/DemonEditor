#!/usr/bin/env python3
import os


def update_icon():
    need_update = False
    icon_name = "DemonEditor.desktop"

    with open(icon_name, "r") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith("Icon="):
                icon_path = line.lstrip("Icon=")
                current_path = "{}/app/ui/icons/hicolor/96x96/apps/demon-editor.png".format(os.getcwd())
                if icon_path != current_path:
                    need_update = True
                    lines[i] = "Icon={}\n".format(current_path)
                break

    if need_update:
        with open(icon_name, "w") as f:
            f.writelines(lines)


if __name__ == "__main__":
    from app.ui.main_app_window import start_app

    update_icon()
    start_app()
