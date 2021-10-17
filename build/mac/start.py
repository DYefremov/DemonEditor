#!/usr/bin/env python3

if __name__ == "__main__":
    from multiprocessing import set_start_method
    from app.ui.main import start_app

    set_start_method("fork")  # For compatibility [Python > 3.7]
    start_app()
