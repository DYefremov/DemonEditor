#!/usr/bin/env python3

if __name__ == "__main__":
    from multiprocessing import freeze_support
    from app.ui.main import start_app

    freeze_support()
    start_app()
