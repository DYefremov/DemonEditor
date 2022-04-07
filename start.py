#!/usr/bin/env python3
import os


def update_icon():
    need_update = False
    icon_name = "DemonEditor.desktop"

    with open(icon_name, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith("Icon="):
                icon_path = line.lstrip("Icon=")
                current_path = f"{os.getcwd()}/app/ui/icons/hicolor/96x96/apps/demon-editor.png"
                if icon_path != current_path:
                    need_update = True
                    lines[i] = f"Icon={current_path}\n"
                break

    if need_update:
        with open(icon_name, "w", encoding="utf-8") as f:
            f.writelines(lines)


if __name__ == "__main__":
    from app.ui.main import start_app

    update_icon()
    start_app()
