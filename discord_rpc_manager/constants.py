# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

APP_TITLE = "Discord RPC Manager"
DEFAULT_INTERVAL = 10
DEFAULT_CDP_PORT = 9222
CDP_GAME_TARGET_HINT = "kcs2/index.php"
CDP_KCSAPI_HINT = "/kcsapi/"

VARIANT_DEFAULTS = {
    "enabled": True,
    "app_name": "Variant",
    "name": "",
    "client_id": "",
    "details": "",
    "state": "",
    "large_image": "",
    "large_text": "",
    "large_url": "",
    "small_image": "",
    "small_text": "",
    "small_url": "",
    "show_timer": True,
    "weight": 1,
    "party_current": 0,
    "party_max": 0,
    "party_current_dynamic": False,
    "button1_label": "",
    "button1_url": "",
    "button2_label": "",
    "button2_url": "",
}

DEFAULT_CONFIG = {
    "check_interval_seconds": DEFAULT_INTERVAL,
    "start_minimized_to_tray": False,
    "auto_start_monitoring": False,
    "start_with_windows": False,
    "groups": [],
}
