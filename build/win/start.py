#!/usr/bin/env python3
import sys

if __name__ == "__main__":
    if hasattr(sys, "_MEIPASS"):
        import os
        import ssl
        from multiprocessing import freeze_support

        os.environ["PYTHONUTF8"] = "1"
        freeze_support()
        # TODO There needs to be a more "correct" way.
        ssl._create_default_https_context = ssl._create_unverified_context

    from app.ui.main import start_app

    start_app()
