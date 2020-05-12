#!/usr/bin/env python3

try:
    from Cocoa import NSBundle
except ImportError as e:
    print(e)
else:
    ns_bundle = NSBundle.mainBundle()
    if ns_bundle:
        ns_bundle = ns_bundle.localizedInfoDictionary() or ns_bundle.infoDictionary()
        if ns_bundle:
            ns_bundle["CFBundleName"] = "DemonEditor"

if __name__ == "__main__":
    from multiprocessing import set_start_method
    from app.ui.main_app_window import start_app

    set_start_method("fork")  # For compatibility [Python > 3.7]
    start_app()
