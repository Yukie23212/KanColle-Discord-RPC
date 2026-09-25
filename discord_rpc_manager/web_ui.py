# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import copy
import json
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import _normalize_group
from .utils import safe_format


WEB_DIR = Path(__file__).resolve().parent / "web"


def _set_webview_theme(light):
    """Best-effort bridge from the HTML theme toggle to the native pywebview title bar."""
    callback = getattr(_set_webview_theme, "theme_callback", None)
    if callback is not None:
        try:
            callback(bool(light))
        except Exception:
            pass


def _bring_webview_to_front():
    focus_callback = getattr(_bring_webview_to_front, "focus_callback", None)
    if focus_callback is not None:
        try:
            focus_callback()
            return
        except Exception:
            pass

    if os.name != "nt":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            user32.BringWindowToTop(hwnd)
    except Exception:
        pass


class _Bridge:
    def __init__(self, app):
        self.app = app

    def call(self, fn, timeout=10):
        done = threading.Event()
        box = {}
        self.app.web_command_queue.put((fn, done, box))
        if not done.wait(timeout):
            raise TimeoutError("The Python UI thread did not respond in time.")
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def state(self):
        def _read():
            config = copy.deepcopy(self.app.config_data)
            for group in config.get("groups", []):
                token = group.get("widget_v2_bot_token", "")
                group["widget_v2_bot_token"] = "" if not token else "__SET__"

            monitor = self.app.monitor
            snapshot = None
            active_process = None
            active_variant = None
            rendered_presence = None
            if monitor is not None:
                active_process = monitor._active_process
                active_variant = (
                    copy.deepcopy(monitor._active_variant)
                    if monitor._active_variant is not None else None
                )
                watcher = monitor._cdp_watcher
                if watcher is not None:
                    snapshot = watcher.get_snapshot()

                if active_variant is not None:
                    live = snapshot is not None
                    if snapshot is None:
                        snapshot = {}
                    rendered_text = monitor.render_variant_text(active_variant, snapshot)
                    rendered_name = rendered_text["name"]
                    rendered_details = rendered_text["details"]
                    rendered_state = rendered_text["state"]
                    rendered_buttons = []
                    for label_key, url_key in (("button1_label", "button1_url"), ("button2_label", "button2_url")):
                        label = str(active_variant.get(label_key, "")).strip()
                        url = str(active_variant.get(url_key, "")).strip()
                        if label and url:
                            rendered_buttons.append({"label": label[:32], "url": url})
                    try:
                        party_max = int(active_variant.get("party_max") or 0)
                    except (TypeError, ValueError):
                        party_max = 0
                    party_current = 0
                    if party_max > 0:
                        if active_variant.get("party_current_dynamic") and live:
                            try:
                                party_current = int(snapshot.get("ship_count", 0) or 0)
                            except (TypeError, ValueError):
                                party_current = 0
                        else:
                            try:
                                party_current = int(str(active_variant.get("party_current", 0)).strip())
                            except (TypeError, ValueError):
                                party_current = 0
                        party_current = max(0, min(party_current, party_max))
                    rendered_presence = {
                        "app_name": active_variant.get("app_name", ""),
                        "name": rendered_name,
                        "details": rendered_details,
                        "state": rendered_state,
                        "client_id": active_variant.get("client_id", ""),
                        "large_image": active_variant.get("large_image", ""),
                        "large_text": active_variant.get("large_text", ""),
                        "small_image": active_variant.get("small_image", ""),
                        "small_text": active_variant.get("small_text", ""),
                        "party_current": party_current,
                        "party_max": party_max,
                        "buttons": rendered_buttons,
                        "source": "live" if live else "config",
                        "stage": snapshot.get("presence_stage", "") if snapshot else "",
                    }

            return {
                "config": config,
                "active_config_path": self.app.active_config_path,
                "monitoring": bool(monitor and monitor.is_alive()),
                "status": self.app._web_status_text,
                "logs": list(self.app.web_log_buffer[-200:]),
                "active_process": active_process,
                "active_variant": active_variant,
                "rendered_presence": rendered_presence,
                "snapshot": snapshot,
            }
        return self.call(_read)

    def update_config(self, data):
        if not isinstance(data, dict):
            raise ValueError("Config body must be an object.")

        def _update():
            current = self.app.config_data
            if "check_interval_seconds" in data:
                try:
                    current["check_interval_seconds"] = max(2, min(300, int(data["check_interval_seconds"])))
                except (TypeError, ValueError):
                    raise ValueError("Invalid scan interval.")
            if "idle_auto_stop_minutes" in data:
                try:
                    current["idle_auto_stop_minutes"] = max(0, int(data["idle_auto_stop_minutes"]))
                except (TypeError, ValueError):
                    raise ValueError("Invalid idle-stop value.")
            if "custom_templates" in data:
                templates = data["custom_templates"]
                if not isinstance(templates, dict):
                    raise ValueError("custom_templates must be an object.")
                current["custom_templates"] = {
                    str(k).strip(): str(v)
                    for k, v in templates.items()
                    if str(k).strip()
                }
            if "stage_template_defaults" in data:
                stage_templates = data["stage_template_defaults"]
                if not isinstance(stage_templates, dict):
                    raise ValueError("stage_template_defaults must be an object.")
                normalized = {}
                for stage in ("in_port", "on_sortie", "in_battle", "night_battle", "battle_result", "quest", "repair_dock", "exercise_opponent", "exercise_battle", "exercise_night_battle", "exercise_result", "expedition_result"):
                    raw = stage_templates.get(stage, {})
                    if not isinstance(raw, dict):
                        raw = {}
                    normalized[stage] = {
                        "enabled": bool(raw.get("enabled", False)),
                        "details": str(raw.get("details", "")),
                        "state": str(raw.get("state", "")),
                    }
                current["stage_template_defaults"] = normalized
            if "groups" in data:
                groups = data["groups"]
                if not isinstance(groups, list):
                    raise ValueError("groups must be an array.")
                normalized_groups = []
                for index, raw_group in enumerate(groups):
                    if not isinstance(raw_group, dict):
                        continue
                    incoming = copy.deepcopy(raw_group)
                    if index < len(current.get("groups", [])):
                        old_group = current["groups"][index]
                        if incoming.get("widget_v2_bot_token") in (None, "", "__SET__"):
                            incoming["widget_v2_bot_token"] = old_group.get("widget_v2_bot_token", "")
                        old_variants = old_group.get("variants", [])
                        new_variants = incoming.get("variants", [])
                        for vi, variant in enumerate(new_variants):
                            if vi < len(old_variants) and isinstance(variant, dict):
                                if "client_id" not in variant:
                                    variant["client_id"] = old_variants[vi].get("client_id", "")
                    normalized_groups.append(_normalize_group(incoming))
                current["groups"] = normalized_groups
            self.app._save_config()
            self.app._load_config_into_ui()
            return True
        return self.call(_update)

    def set_setting(self, key, value):
        allowed = {
            "auto_start_monitoring",
            "start_minimized_to_tray",
            "start_with_windows",
            "light_theme",
        }
        if key not in allowed:
            raise ValueError("Unsupported setting.")

        def _set():
            if key == "auto_start_monitoring":
                self.app.auto_monitor_var.set(bool(value))
                self.app._save_auto_monitor()
            elif key == "start_minimized_to_tray":
                self.app.minimize_launch_var.set(bool(value))
                self.app._save_minimize_on_launch()
            elif key == "light_theme":
                self.app.config_data["light_theme"] = bool(value)
                self.app._save_config()
            else:
                self.app.start_with_windows_var.set(bool(value))
                self.app._save_start_with_windows()
            return True
        return self.call(_set)

    def toggle_monitor(self):
        return self.call(self.app._toggle_monitor)

    def apply_changes(self):
        return self.call(self.app._apply_changes)

    def save(self):
        def _save():
            self.app._save_config()
            self.app._append_log(f"Saved to {self.app.active_config_path}")
            return True
        return self.call(_save)

    def preview(self, template):
        template = str(template or "")

        def _preview():
            monitor = self.app.monitor
            snapshot = None
            if monitor is not None and monitor._cdp_watcher is not None:
                snapshot = monitor._cdp_watcher.get_snapshot()
            live = snapshot is not None
            if snapshot is None:
                snapshot = {
                    "admiral_nickname": "Commander",
                    "admiral_level": 120,
                    "admiral_rank": "Taisho",
                    "sortie_win": 2232,
                    "sortie_lose": 98,
                    "expedition_success": 899,
                    "expedition_count": 994,
                    "fleet_name": "1st Fleet",
                    "fleet_status": "In Port",
                    "fleet_ship_count": 6,
                    "fleet_total_slots": 6,
                    "ship_count": 120,
                    "fuel": "100k",
                    "ammo": "100k",
                    "steel": "100k",
                    "bauxite": "100k",
                    "flamethrower": 42,
                    "bucket": 37,
                    "dev_material": 58,
                    "screw": 26,
                    "location_text": "Port",
                    "map_node_text": "",
                    "battle_rank": "",
                }
            rendered = safe_format(template, snapshot, self.app.config_data.get("custom_templates", {}))
            return {
                "rendered": rendered,
                "source": "live" if live else "example",
                "snapshot": snapshot,
            }
        return self.call(_preview)

    def set_window_theme(self, light):
        _set_webview_theme(bool(light))
        return True

    def open_config(self):
        result = self.call(self.app._open_config)
        _bring_webview_to_front()
        return result

    def shutdown(self):
        return self.call(self.app._quit_app)


class _Handler(BaseHTTPRequestHandler):
    bridge = None

    def log_message(self, fmt, *args):
        return

    def _send_json(self, payload, status=HTTPStatus.OK):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise ValueError("Request body is too large.")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/state":
                self._send_json(self.bridge.state())
                return
            if path == "/":
                return self._serve_file("index.html", "text/html; charset=utf-8")
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                if ".." in Path(rel).parts:
                    raise ValueError("Invalid path")
                return self._serve_file(rel, None)
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as e:
            self._send_json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/config":
                self.bridge.update_config(body)
                return self._send_json({"ok": True})
            if path == "/api/setting":
                self.bridge.set_setting(body.get("key"), body.get("value"))
                return self._send_json({"ok": True})
            if path == "/api/monitor/toggle":
                self.bridge.toggle_monitor()
                return self._send_json({"ok": True})
            if path == "/api/monitor/apply":
                self.bridge.apply_changes()
                return self._send_json({"ok": True})
            if path == "/api/save":
                self.bridge.save()
                return self._send_json({"ok": True})
            if path == "/api/window/theme":
                self.bridge.set_window_theme(body.get("light", False))
                return self._send_json({"ok": True})
            if path == "/api/config/open":
                self.bridge.open_config()
                return self._send_json({"ok": True})
            if path == "/api/preview":
                return self._send_json(self.bridge.preview(body.get("template", "")))
            if path == "/api/shutdown":
                self.bridge.shutdown()
                return self._send_json({"ok": True})
            return self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except TimeoutError as e:
            self._send_json({"error": str(e)}, HTTPStatus.GATEWAY_TIMEOUT)
        except (ValueError, json.JSONDecodeError) as e:
            self._send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self._send_json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_file(self, relative, content_type):
        path = (WEB_DIR / relative).resolve()
        if not str(path).startswith(str(WEB_DIR.resolve())) or not path.is_file():
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        if content_type is None:
            suffix = path.suffix.lower()
            content_type = {
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".ico": "image/x-icon",
            }.get(suffix, "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def start_web_server(app, port=0, open_browser=True):
    bridge = _Bridge(app)

    class Handler(_Handler):
        pass

    Handler.bridge = bridge
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, name="WebUIServer", daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    print(f"Web UI: {url}")
    return server, url
