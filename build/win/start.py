#!/usr/bin/env python3
import os
import ssl

if __name__ == "__main__":
    from multiprocessing import freeze_support
    from app.ui.main import start_app

    os.environ["PYTHONUTF8"] = "1"
    # TODO There needs to be a more "correct" way.
    ssl._create_default_https_context = ssl._create_unverified_context

    freeze_support()
    start_app()
