# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

APP_TITLE = "KanColle RPC Manager"
RUNTIME_DATA_DIR_NAME = "Do not delete"
DEFAULT_INTERVAL = 10
DEFAULT_CDP_PORT = 9222
CDP_GAME_TARGET_HINT = "kcs2/index.php"
CDP_KCSAPI_HINT = "/kcsapi/"

STAGE_TEMPLATE_DEFAULTS = {
    "in_port": {"enabled": False, "details": "", "state": ""},
    "on_sortie": {"enabled": False, "details": "", "state": ""},
    "in_battle": {"enabled": False, "details": "", "state": ""},
    "night_battle": {"enabled": False, "details": "", "state": ""},
    "battle_result": {"enabled": False, "details": "", "state": ""},
    "quest": {"enabled": False, "details": "", "state": ""},
    "repair_dock": {"enabled": False, "details": "", "state": ""},
    "exercise_opponent": {"enabled": False, "details": "", "state": ""},
    "exercise_battle": {"enabled": False, "details": "", "state": ""},
    "exercise_night_battle": {"enabled": False, "details": "", "state": ""},
    "exercise_result": {"enabled": False, "details": "", "state": ""},
    "expedition_result": {"enabled": False, "details": "", "state": ""},
}

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

STAGE_TEMPLATE_CONFIG_DEFAULTS = {
    "in_port": {"enabled": False, "details": "", "state": ""},
    "on_sortie": {"enabled": False, "details": "", "state": ""},
    "in_battle": {"enabled": False, "details": "", "state": ""},
    "night_battle": {"enabled": False, "details": "", "state": ""},
    "battle_result": {"enabled": False, "details": "", "state": ""},
    "quest": {"enabled": False, "details": "", "state": ""},
    "repair_dock": {"enabled": False, "details": "", "state": ""},
    "exercise_opponent": {"enabled": False, "details": "", "state": ""},
    "exercise_battle": {"enabled": False, "details": "", "state": ""},
    "exercise_night_battle": {"enabled": False, "details": "", "state": ""},
    "exercise_result": {"enabled": False, "details": "", "state": ""},
    "expedition_result": {"enabled": False, "details": "", "state": ""},
}

DEFAULT_CONFIG = {
    "check_interval_seconds": DEFAULT_INTERVAL,
    "start_minimized_to_tray": False,
    "auto_start_monitoring": False,
    "start_with_windows": False,
    "light_theme": False,
    "idle_auto_stop_minutes": 0,
    "custom_templates": {},
    "stage_template_defaults": STAGE_TEMPLATE_CONFIG_DEFAULTS,
    "groups": [],
}
