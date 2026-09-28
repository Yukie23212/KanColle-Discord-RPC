# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import json
import os
import sys
import base64
import ctypes
from ctypes import wintypes
import uuid

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

CONFIG_PATH = os.path.join(get_data_dir(), "config.json")
LEGACY_CONFIG_PATH = os.path.join(get_base_dir(), "config.json")
SECRETS_PATH = os.path.join(get_data_dir(), "secrets.json")
LAST_CONFIG_PATH = os.path.join(get_data_dir(), "last_config.json")

def _get_launch_command():
    """Command line to relaunch the app in the same UI mode used now."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.abspath(sys.argv[0])

    # The HTML UI is normally started through Launch Web UI.vbs. When the
    # user enables Start with Windows from that mode, register the same
    # launcher so Windows opens the web interface instead of falling back
    # to the old Tkinter GUI. Keep a direct --web fallback when the VBS
    # launcher is not present.
    if "--web" in sys.argv:
        launcher = os.path.join(os.path.dirname(script), "Launch Web UI.vbs")
        if os.path.exists(launcher):
            windir = os.environ.get("WINDIR", r"C:\Windows")
            wscript = os.path.join(windir, "System32", "wscript.exe")
            return f'"{wscript}" "{launcher}"'
        return f'"{interpreter}" "{script}" --web'

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
        # Discord "Widget V2" profile field sync -- see widget_v2.py.
        # Sources its value from the same live-data snapshot as cdp_watch
        # (currently always {admiral_level}), so it only does anything
        # useful when cdp_watch is also on for this group.
        "widget_v2_enabled": bool(g.get("widget_v2_enabled", False)),
        "widget_v2_app_id": (g.get("widget_v2_app_id") or "").strip(),
        "widget_v2_user_id": (g.get("widget_v2_user_id") or "").strip(),
        # Secret ID is safe to share; the token itself lives only in secrets.json.
        "widget_v2_secret_id": str(g.get("widget_v2_secret_id") or "").strip() or _new_secret_id(),
        "widget_v2_bot_token": (g.get("widget_v2_bot_token") or "").strip(),
        "widget_v2_field_name": str(g.get("widget_v2_field_name", "HQ_level") or "").strip(),
        # Format-string template for the pushed value, resolved against the
        # same live-data snapshot as Details/State (see utils.safe_format).
        # Lets Haru keep hand-maintained text alongside the auto-updated
        # number, e.g. "{admiral_level} [Taisho]" -- the bracketed part is
        # never touched by the automation, only re-typed by hand when it
        # needs to change.
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
    raw_groups = data["groups"]
    had_secret_ids = all(
        isinstance(g, dict) and str(g.get("widget_v2_secret_id") or "").strip()
        for g in raw_groups
    )
    data["groups"] = [_normalize_group(g) for g in raw_groups if isinstance(g, dict)]
    _attach_secrets(data["groups"])
    # Save immediately when migrating an old config or when secret IDs were
    # generated so the on-disk config is ready to be shared safely.
    if migrated or not had_secret_ids or any(
        isinstance(g, dict) and str(g.get("widget_v2_bot_token") or "").strip()
        for g in data["groups"]
    ):
        save_config(data, path)
    return data

def save_config(data, path=None):
    path = path or CONFIG_PATH
    public = _strip_secrets_for_save(data)

    # Persist Widget V2 credentials separately. They never enter config.json.
    # Empty values do not erase an existing local credential.
    secrets = _load_secrets()
    for group in data.get("groups", []) if isinstance(data, dict) else []:
        if not isinstance(group, dict):
            continue
        secret_id = _secret_id_for_group(group)
        current = _normalize_secret_record(secrets.get(secret_id))
        for key in ("app_id", "user_id", "bot_token"):
            value = str(group.get({
                "app_id": "widget_v2_app_id",
                "user_id": "widget_v2_user_id",
                "bot_token": "widget_v2_bot_token",
            }[key]) or "").strip()
            if value and value != "__SET__":
                current[key] = value
        secrets[secret_id] = current
    _save_secrets(secrets)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(public, f, indent=2)
    os.replace(tmp, path)



def _new_secret_id():
    return uuid.uuid4().hex


def _dpapi_protect(raw):
    """Encrypt bytes using Windows DPAPI for the current Windows user."""
    if sys.platform != "win32":
        return None
    try:
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
            wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        in_buf = ctypes.create_string_buffer(raw)
        in_blob = DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_ubyte)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _dpapi_unprotect(raw):
    """Decrypt bytes protected by Windows DPAPI for the current Windows user."""
    if sys.platform != "win32":
        return None
    try:
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DATA_BLOB),
            wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        in_buf = ctypes.create_string_buffer(raw)
        in_blob = DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_ubyte)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _load_secrets():
    """Load local Widget V2 secrets. Windows uses DPAPI; fallback is JSON."""
    if not os.path.exists(SECRETS_PATH):
        return {}
    try:
        with open(SECRETS_PATH, "rb") as f:
            raw = f.read()
        if not raw:
            return {}

        # Current Windows format: DPAPI-encrypted JSON, base64 wrapped.
        if sys.platform == "win32":
            try:
                decoded = base64.b64decode(raw, validate=True)
                plain = _dpapi_unprotect(decoded)
                if plain is not None:
                    data = json.loads(plain.decode("utf-8"))
                    return data if isinstance(data, dict) else {}
            except Exception:
                pass

        # Plain JSON is retained as a compatibility fallback for non-Windows
        # platforms and for older development builds.
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _save_secrets(secrets):
    os.makedirs(os.path.dirname(SECRETS_PATH), exist_ok=True)
    payload = json.dumps(secrets if isinstance(secrets, dict) else {}, indent=2).encode("utf-8")
    protected = _dpapi_protect(payload)
    if protected is not None:
        raw = base64.b64encode(protected)
    else:
        raw = payload
    tmp = SECRETS_PATH + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, SECRETS_PATH)


def load_last_config_path():
    try:
        with open(LAST_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        path = data.get("path") if isinstance(data, dict) else None
        return path if isinstance(path, str) and path.strip() else None
    except (json.JSONDecodeError, OSError):
        return None


def save_last_config_path(path):
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(LAST_CONFIG_PATH), exist_ok=True)
        tmp = LAST_CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"path": os.path.abspath(path)}, f, indent=2)
        os.replace(tmp, LAST_CONFIG_PATH)
    except OSError:
        pass


def _secret_id_for_group(group):
    secret_id = str(group.get("widget_v2_secret_id") or "").strip()
    if not secret_id:
        secret_id = _new_secret_id()
        group["widget_v2_secret_id"] = secret_id
    return secret_id


def _normalize_secret_record(value):
    """Return the current Widget V2 credential record shape."""
    if isinstance(value, dict):
        return {
            "app_id": str(value.get("app_id") or "").strip(),
            "user_id": str(value.get("user_id") or "").strip(),
            "bot_token": str(value.get("bot_token") or "").strip(),
        }
    # Backward compatibility with the first 10.1 secret-store format, which
    # stored the bot token directly as the secret value.
    if isinstance(value, str):
        return {"app_id": "", "user_id": "", "bot_token": value.strip()}
    return {"app_id": "", "user_id": "", "bot_token": ""}


def _attach_secrets(groups):
    """Hydrate runtime Widget V2 credentials from the machine-local secret store."""
    secrets = _load_secrets()
    changed = False
    for group in groups:
        if not isinstance(group, dict):
            continue

        secret_id = _secret_id_for_group(group)
        current = _normalize_secret_record(secrets.get(secret_id))

        # Migrate any credentials embedded in legacy/shareable configs. A
        # locally stored value always takes precedence over the legacy value.
        legacy_values = {
            "app_id": str(group.get("widget_v2_app_id") or "").strip(),
            "user_id": str(group.get("widget_v2_user_id") or "").strip(),
            "bot_token": str(group.get("widget_v2_bot_token") or "").strip(),
        }
        for key, legacy_value in legacy_values.items():
            if legacy_value and not current[key]:
                current[key] = legacy_value
                changed = True

        group["widget_v2_app_id"] = current["app_id"]
        group["widget_v2_user_id"] = current["user_id"]
        group["widget_v2_bot_token"] = current["bot_token"]

        if secrets.get(secret_id) != current:
            secrets[secret_id] = current
            changed = True

    if changed:
        _save_secrets(secrets)
    return groups


def _strip_secrets_for_save(data):
    """Return a shareable config copy with all Widget V2 credentials removed."""
    public = json.loads(json.dumps(data))
    private_keys = (
        "widget_v2_app_id",
        "widget_v2_user_id",
        "widget_v2_bot_token",
    )
    for group in public.get("groups", []):
        if isinstance(group, dict):
            for key in private_keys:
                group.pop(key, None)
    return public

