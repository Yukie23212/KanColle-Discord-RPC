# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import json
import os
import sys

from .constants import DEFAULT_CONFIG, DEFAULT_INTERVAL, DEFAULT_CDP_PORT, VARIANT_DEFAULTS

STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_NAME = "DiscordRPCManager"


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(sys.argv[0]))

def _get_launch_command():
    """Command line to relaunch this app exactly as it's running now."""
    if getattr(sys, "frozen", False):
        
        return f'"{sys.executable}"'
    
    
    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.abspath(sys.argv[0])
    return f'"{interpreter}" "{script}"'

def set_start_with_windows(enabled):
    """Add/remove a HKCU Run key entry so the app launches on Windows login.
    Raises RuntimeError with a human-readable message on failure (including
    on non-Windows platforms, where this is simply unsupported)."""
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

def _normalize_variant(v):
    out = dict(VARIANT_DEFAULTS)
    out.update(v or {})
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
    group = {
        "enabled": g.get("enabled", True),
        "process_name": (g.get("process_name") or "").strip(),
        "variants": [_normalize_variant(v) for v in g.get("variants", [])],
        
        
        
        
        "cdp_watch": bool(g.get("cdp_watch", False)),
        "cdp_port": g.get("cdp_port", DEFAULT_CDP_PORT),
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
    for p in profiles:
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
    path = path or CONFIG_PATH
    if not os.path.exists(path):
        save_config(DEFAULT_CONFIG, path)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        
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

    if "groups" not in data and "profiles" in data:
        
        data["groups"] = _migrate_flat_profiles_to_groups(data.get("profiles", []))
        data.pop("profiles", None)

    data.setdefault("groups", [])
    data["groups"] = [_normalize_group(g) for g in data["groups"]]
    return data

def save_config(data, path=None):
    path = path or CONFIG_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


CONFIG_PATH = os.path.join(get_base_dir(), "config.json")
