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

from app.ui.main_app_window import start_app

start_app()
