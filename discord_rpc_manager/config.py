# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import json
import os
import sys

from .constants import DEFAULT_CONFIG, DEFAULT_INTERVAL, DEFAULT_CDP_PORT, RUNTIME_DATA_DIR_NAME, VARIANT_DEFAULTS, STAGE_TEMPLATE_DEFAULTS, STAGE_TEMPLATE_CONFIG_DEFAULTS

STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_NAME = "DiscordRPCManager"


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def get_data_dir():
    path = os.path.join(get_base_dir(), RUNTIME_DATA_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path

def _get_launch_command():
    """Command line to relaunch the app in the same UI mode used now."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.abspath(sys.argv[0])

    if "--web" in sys.argv:
        launcher = os.path.join(os.path.dirname(script), "Launch Web UI.vbs")
        if os.path.exists(launcher):
            windir = os.environ.get("WINDIR", r"C:\Windows")
            wscript = os.path.join(windir, "System32", "wscript.exe")
            return f'"{wscript}" "{launcher}"'
        return f'"{interpreter}" "{script}" --web'

    return f'"{interpreter}" "{script}"'

def set_start_with_windows(enabled):
    if sys.platform != "win32":
        raise RuntimeError("Start-with-Windows is only supported on Windows.")
    try:
        import winreg
    except ImportError as e:
        raise RuntimeError(f"Could not access the Windows registry: {e}")

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, STARTUP_REG_NAME, 0, winreg.REG_SZ, _get_launch_command())
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_REG_NAME)
                except FileNotFoundError:
                    pass  
    except OSError as e:
        raise RuntimeError(f"Could not update the Windows registry: {e}")


def _normalize_stage_template_map(raw_map):
    if not isinstance(raw_map, dict):
        raw_map = {}
    out = {}
    for stage, defaults in STAGE_TEMPLATE_CONFIG_DEFAULTS.items():
        raw = raw_map.get(stage, {})
        if not isinstance(raw, dict):
            raw = {}
        out[stage] = {
            "enabled": bool(raw.get("enabled", defaults["enabled"])),
            "details": str(raw.get("details", defaults["details"])),
            "state": str(raw.get("state", defaults["state"])),
        }
    return out

def _normalize_variant(v):
    out = dict(VARIANT_DEFAULTS)
    out.update(v or {})

    raw_stage_templates = out.get("stage_templates", {})
    if not isinstance(raw_stage_templates, dict):
        raw_stage_templates = {}
    stage_templates = {}
    for stage, defaults in STAGE_TEMPLATE_DEFAULTS.items():
        raw = raw_stage_templates.get(stage, {})
        if not isinstance(raw, dict):
            raw = {}
        stage_templates[stage] = {
            "enabled": bool(raw.get("enabled", defaults["enabled"])),
            "details": str(raw.get("details", defaults["details"])),
            "state": str(raw.get("state", defaults["state"])),
        }
    out["stage_templates"] = stage_templates

    if not out.get("app_name"):
        out["app_name"] = "Variant"
    try:
        out["weight"] = max(1, int(out.get("weight", 1)))
    except (TypeError, ValueError):
        out["weight"] = 1
    try:
        out["party_max"] = max(0, int(out.get("party_max", 0) or 0))
    except (TypeError, ValueError):
        out["party_max"] = 0
    out["party_current_dynamic"] = bool(out.get("party_current_dynamic", False))
    if out["party_current_dynamic"]:
        
        
        out["party_current"] = "{ship_count}"
    else:
        try:
            out["party_current"] = max(0, int(out.get("party_current", 0) or 0))
        except (TypeError, ValueError):
            out["party_current"] = 0
    return out

def _normalize_group(g):
    if not isinstance(g, dict):
        g = {}
    variants = g.get("variants", [])
    if not isinstance(variants, list):
        variants = []
    group = {
        "enabled": g.get("enabled", True),
        "process_name": (g.get("process_name") or "").strip(),
        "variants": [_normalize_variant(v) for v in variants if isinstance(v, dict)],
        
        
        
        
        "cdp_watch": bool(g.get("cdp_watch", False)),
        "cdp_port": g.get("cdp_port", DEFAULT_CDP_PORT),
        "widget_v2_enabled": bool(g.get("widget_v2_enabled", False)),
        "widget_v2_app_id": (g.get("widget_v2_app_id") or "").strip(),
        "widget_v2_user_id": (g.get("widget_v2_user_id") or "").strip(),
        "widget_v2_bot_token": (g.get("widget_v2_bot_token") or "").strip(),
        "widget_v2_field_name": str(g.get("widget_v2_field_name", "HQ_level") or "").strip(),
        "widget_v2_value_template": str(g.get("widget_v2_value_template", "{admiral_level}") or "").strip(),
    }
    try:
        group["cdp_port"] = int(group["cdp_port"])
    except (TypeError, ValueError):
        group["cdp_port"] = DEFAULT_CDP_PORT
    if not group["variants"]:
        group["variants"] = [_normalize_variant({"app_name": group["process_name"] or "Variant"})]
    return group

def _migrate_flat_profiles_to_groups(profiles):
    """Convert the old one-profile-per-process format into the new
    groups/variants format (one group per process, each with a single
    variant), so existing config.json files from earlier versions keep
    working without the user losing their setup."""
    groups = []
    for p in profiles if isinstance(profiles, list) else []:
        if not isinstance(p, dict):
            continue
        groups.append({
            "enabled": p.get("enabled", True),
            "process_name": (p.get("process_name") or "").strip(),
            "variants": [_normalize_variant({
                "enabled": True,
                "app_name": p.get("app_name", p.get("process_name", "Variant")),
                "name": p.get("name", ""),
                "client_id": p.get("client_id", ""),
                "details": p.get("details", ""),
                "state": p.get("state", ""),
                "large_image": p.get("large_image", ""),
                "large_text": p.get("large_text", ""),
                "large_url": p.get("large_url", ""),
                "small_image": p.get("small_image", ""),
                "small_text": p.get("small_text", ""),
                "small_url": p.get("small_url", ""),
                "show_timer": p.get("show_timer", True),
                "weight": 1,
            })],
        })
    return groups

def load_config(path=None):
    requested_default = path is None
    path = path or CONFIG_PATH
    migrated = False
    data = None
    if requested_default and not os.path.exists(path) and os.path.exists(LEGACY_CONFIG_PATH):
        try:
            with open(LEGACY_CONFIG_PATH, "r", encoding="utf-8") as f:
                legacy_data = json.load(f)
            if isinstance(legacy_data, dict):
                data = legacy_data
                migrated = True
        except (json.JSONDecodeError, OSError):
            pass
    if not os.path.exists(path):
        if data is None:
            save_config(DEFAULT_CONFIG, path)
            return json.loads(json.dumps(DEFAULT_CONFIG))
    if data is None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = None
    if not isinstance(data, dict):
        backup = path + ".bak"
        try:
            os.replace(path, backup)
        except OSError:
            pass
        save_config(DEFAULT_CONFIG, path)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    data.setdefault("check_interval_seconds", DEFAULT_INTERVAL)
    data.setdefault("start_minimized_to_tray", False)
    data.setdefault("auto_start_monitoring", False)
    data.setdefault("start_with_windows", False)
    data.setdefault("light_theme", False)
    data.setdefault("idle_auto_stop_minutes", 0)
    data["stage_template_defaults"] = _normalize_stage_template_map(
        data.get("stage_template_defaults", {})
    )

    custom_templates = data.get("custom_templates", {})
    if not isinstance(custom_templates, dict):
        custom_templates = {}
    data["custom_templates"] = {
        str(name).strip(): str(template)
        for name, template in custom_templates.items()
        if str(name).strip()
    }

    if "groups" not in data and "profiles" in data:
        data["groups"] = _migrate_flat_profiles_to_groups(data.get("profiles", []))
        data.pop("profiles", None)

    data.setdefault("groups", [])
    if not isinstance(data["groups"], list):
        data["groups"] = []
    data["groups"] = [_normalize_group(g) for g in data["groups"] if isinstance(g, dict)]
    if migrated:
        save_config(data, path)
    return data

def save_config(data, path=None):
    path = path or CONFIG_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


CONFIG_PATH = os.path.join(get_data_dir(), "config.json")
LEGACY_CONFIG_PATH = os.path.join(get_base_dir(), "config.json")
