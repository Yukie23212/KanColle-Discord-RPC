# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import threading
import time
from datetime import datetime

import psutil
from pypresence import Presence

from .constants import DEFAULT_CDP_PORT, DEFAULT_INTERVAL
from .cdp_watcher import CDP_AVAILABLE, KancolleCDPWatcher
from .utils import choose_variant, safe_format
from .widget_v2 import push_dynamic_field


class RPCMonitor(threading.Thread):

    def __init__(self, get_groups, get_interval, log_queue, status_queue, get_idle_stop_minutes=None, get_custom_templates=None, get_stage_template_defaults=None):
        super().__init__(daemon=True)
        self._get_groups = get_groups
        self._get_interval = get_interval
        self._get_idle_stop_minutes = get_idle_stop_minutes or (lambda: 0)
        self._get_custom_templates = get_custom_templates or (lambda: {})
        self._get_stage_template_defaults = get_stage_template_defaults or (lambda: {})
        self._log_queue = log_queue
        self._status_queue = status_queue
        self._stop_event = threading.Event()
        self._rpc = None
        self._connect_time = None
        self._session_start_time = None
        self._session_process = None
        self._last_presence_signature = None

        
        
        
        self._process_was_running = {}
        self._chosen_variant = {}  

        
        self._active_process = None
        self._active_variant = None

        
        
        
        self._cdp_watcher = None
        self._cdp_watcher_owner = None

        self._widget_v2_state = {}
        self._widget_v2_warned_no_cdp = set()
        self._widget_v2_warned_no_creds = set()

    def stop(self):
        self._stop_event.set()

    def get_live_snapshot(self):
        """Return a copy of the current CDP snapshot for GUI preview use."""
        watcher = self._cdp_watcher
        if watcher is None:
            return None
        try:
            return watcher.get_snapshot()
        except Exception:
            return None

    def log(self, msg):
        self._log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def set_status(self, text):
        self._status_queue.put(text)

    def _ensure_cdp_watcher(self, process_name, group):
        """Start/stop the KanColle live-data watcher so exactly one runs,
        owned by whichever process currently needs it."""
        wants_watcher = process_name is not None and group is not None and group.get("cdp_watch")
        if wants_watcher and self._cdp_watcher_owner == process_name and self._cdp_watcher is not None:
            return  
        if self._cdp_watcher is not None:
            self._cdp_watcher.stop()
            self._cdp_watcher.join(timeout=2)
            self._cdp_watcher = None
            self._cdp_watcher_owner = None
        if wants_watcher:
            if not CDP_AVAILABLE:
                self.log(
                    "'cdp_watch' is enabled for a group, but the 'websocket-client' "
                    "package isn't installed. Run: pip install websocket-client"
                )
                return
            self._cdp_watcher = KancolleCDPWatcher(group.get("cdp_port", DEFAULT_CDP_PORT), self.log)
            self._cdp_watcher.start()
            self._cdp_watcher_owner = process_name

    _WIDGET_V2_RETRY_COOLDOWN = 60  # seconds to wait before retrying the SAME failed value

    def _maybe_push_widget_v2(self, process_name, group, snapshot):
        """Push {admiral_level} to Discord's Widget V2 profile field for
        this group, but only when the value actually changed since the
        last successful push (per Haru: level rarely changes, so most
        scan cycles should do nothing here at all)."""
        if not group.get("widget_v2_enabled"):
            return
        if snapshot is None:
            if process_name not in self._widget_v2_warned_no_cdp:
                self._widget_v2_warned_no_cdp.add(process_name)
                self.log(
                    "Widget V2 sync is on for a group, but 'Watch live game data' is "
                    "off -- there's no live value to push, so nothing will happen."
                )
            return

        value = snapshot.get("admiral_level")
        if value in (None, "?"):
            return  # no real data captured yet -- wait for the next kcsapi call

        template = group.get("widget_v2_value_template") or "{admiral_level}"
        rendered_value = safe_format(template, snapshot, self._get_custom_templates())

        app_id = group.get("widget_v2_app_id")
        user_id = group.get("widget_v2_user_id")
        bot_token = group.get("widget_v2_bot_token")
        field_name = group.get("widget_v2_field_name") or "HQ_level"
        if not (app_id and user_id and bot_token):
            if process_name not in self._widget_v2_warned_no_creds:
                self._widget_v2_warned_no_creds.add(process_name)
                self.log(
                    "Widget V2 sync is on for a group, but App ID/User ID/Bot Token "
                    "aren't all filled in -- skipping."
                )
            return

        state = self._widget_v2_state.get(process_name, {})
        now = time.time()
        if state.get("value") == rendered_value:
            if state.get("ok"):
                return  # already pushed this exact value successfully
            if (now - state.get("last_attempt", 0)) < self._WIDGET_V2_RETRY_COOLDOWN:
                return  # recently failed on this same value -- back off rather than spam

        ok, err = push_dynamic_field(app_id, user_id, bot_token, field_name, rendered_value)
        self._widget_v2_state[process_name] = {"value": rendered_value, "ok": ok, "last_attempt": now}
        if ok:
            self.log(f"Widget V2 updated: {field_name} = {rendered_value}")
        else:
            self.log(f"Widget V2 update failed: {err}")

    def _disconnect(self):
        if self._rpc is not None:
            try:
                self._rpc.clear()
                self._rpc.close()
            except Exception:
                pass
        self._rpc = None
        self._active_process = None
        self._active_variant = None
        self._connect_time = None
        self._last_presence_signature = None

    def _stage_template_value(self, variant, snapshot, field):
        stage = str((snapshot or {}).get("presence_stage") or "").strip()

        # A variant-specific override takes precedence. Global stage defaults
        # are managed from the Templates page and are used only when the
        # variant does not explicitly override the current stage.
        variant_templates = variant.get("stage_templates", {}) or {}
        entry = variant_templates.get(stage)
        if isinstance(entry, dict) and entry.get("enabled"):
            return safe_format(entry.get(field, ""), snapshot, self._get_custom_templates())

        global_templates = self._get_stage_template_defaults() or {}
        global_entry = global_templates.get(stage)
        if isinstance(global_entry, dict) and global_entry.get("enabled"):
            return safe_format(global_entry.get(field, ""), snapshot, self._get_custom_templates())

        return None

    def render_variant_text(self, variant, live_snapshot=None):
        """Render the user-facing name/details/state for UI previews and RPC."""
        if live_snapshot is None:
            return {
                "name": variant.get("name", ""),
                "details": variant.get("details", ""),
                "state": variant.get("state", ""),
            }

        name_text = safe_format(variant.get("name"), live_snapshot, self._get_custom_templates())
        stage_details = self._stage_template_value(variant, live_snapshot, "details")
        stage_state = self._stage_template_value(variant, live_snapshot, "state")
        details_override = live_snapshot.get("presence_details_override")
        if stage_details is not None:
            details_text = stage_details
        elif details_override is not None:
            details_text = str(details_override)
        else:
            details_text = safe_format(variant.get("details"), live_snapshot, self._get_custom_templates())
        state_text = stage_state if stage_state is not None else safe_format(variant.get("state"), live_snapshot, self._get_custom_templates())
        return {"name": name_text, "details": details_text, "state": state_text}

    def _apply_variant(self, process_name, variant, live_snapshot=None, announce=True, force=False):
        needs_new_connection = (
            self._rpc is None
            or self._active_variant is None
            or self._active_variant.get("client_id") != variant.get("client_id")
        )
        if needs_new_connection:
            self._disconnect()
            client_id = str(variant.get("client_id", "")).strip()
            if not client_id or client_id.upper().startswith("YOUR_DISCORD"):
                self.log(
                    f"Skipping '{variant.get('app_name')}': no valid Client ID set."
                )
                return False
            try:
                self._rpc = Presence(client_id)
                self._rpc.connect()
                self._connect_time = int(time.time())
                self.log(f"Connected to Discord for '{variant.get('app_name')}'.")
            except Exception as e:
                self.log(f"Failed to connect to Discord RPC: {e}")
                self._rpc = None
                return False

        rendered_text = self.render_variant_text(variant, live_snapshot)
        name_text = rendered_text["name"]
        details_text = rendered_text["details"]
        state_text = rendered_text["state"]

        payload = {}
        if name_text:
            payload["name"] = name_text
        if state_text:
            payload["state"] = state_text
        if details_text:
            payload["details"] = details_text
        if variant.get("large_image"):
            payload["large_image"] = variant["large_image"]
        if variant.get("large_text"):
            payload["large_text"] = variant["large_text"]
        if variant.get("large_url"):
            payload["large_url"] = variant["large_url"]

        if variant.get("small_image"):
            payload["small_image"] = variant["small_image"]
        if variant.get("small_text"):
            payload["small_text"] = variant["small_text"]
        if variant.get("small_url"):
            payload["small_url"] = variant["small_url"]
        if variant.get("show_timer", True):
            payload["start"] = self._session_start_time or self._connect_time or int(time.time())

        try:
            party_max = int(variant.get("party_max") or 0)
        except (TypeError, ValueError):
            party_max = 0
        if party_max > 0:
            if variant.get("party_current_dynamic", False) and live_snapshot is not None:
                try:
                    party_current = int(safe_format("{ship_count}", live_snapshot, self._get_custom_templates()))
                except (TypeError, ValueError):
                    party_current = 0
            else:
                try:
                    party_current = int(variant.get("party_current") or 0)
                except (TypeError, ValueError):
                    party_current = 0
            party_current = max(0, min(party_current, party_max))
            payload["party_id"] = f"party-{variant.get('client_id', 'default')}"
            payload["party_size"] = [party_current, party_max]

        buttons = []
        for label_key, url_key in (("button1_label", "button1_url"), ("button2_label", "button2_url")):
            label = str(variant.get(label_key, "")).strip()
            url = str(variant.get(url_key, "")).strip()
            if label and url:
                buttons.append({"label": label[:32], "url": url})
        if buttons:
            payload["buttons"] = buttons[:2]

        signature = tuple(
            sorted((key, repr(value)) for key, value in payload.items() if key != "start")
        )
        if (
            not force
            and self._last_presence_signature == signature
            and self._active_process == process_name
            and self._active_variant is not None
        ):
            return True

        try:
            self._rpc.update(**payload)
            if (
                live_snapshot is not None
                and live_snapshot.get("presence_details_override") is not None
                and self._cdp_watcher is not None
                and hasattr(self._cdp_watcher, "acknowledge_details_override")
            ):
                self._cdp_watcher.acknowledge_details_override()
            self._active_process = process_name
            self._active_variant = variant
            self._last_presence_signature = signature
            if announce:
                self.log(f"Rich Presence active: '{variant.get('app_name')}'.")
            return True
        except Exception as e:
            self.log(f"Failed to update Discord presence: {e}")
            return False

    def run(self):
        self.log("Monitor started.")
        self.set_status("Monitoring - waiting for a match...")
        self._last_match_time = time.time()
        stopped_idle = False
        while not self._stop_event.is_set():
            groups = [g for g in self._get_groups() if g.get("enabled") and g.get("process_name")]
            group_by_process = {g["process_name"].strip().lower(): g for g in groups}

            running_names = set()
            try:
                for proc in psutil.process_iter(["name"]):
                    try:
                        name = proc.info.get("name")
                        if name:
                            running_names.add(name.lower())
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            except Exception as e:
                self.log(f"Error scanning processes: {e}")

            
            
            for pname, group in group_by_process.items():
                running_now = pname in running_names
                was_running = self._process_was_running.get(pname, False)

                if running_now and not was_running:
                    variant = choose_variant(group)
                    self._chosen_variant[pname] = variant
                    total = len(group.get("variants", []))
                    if variant is not None:
                        note = f" (1 of {total} variant{'s' if total != 1 else ''})" if total > 1 else ""
                        self.log(f"'{pname}' started. Selected profile: '{variant.get('app_name')}'{note}.")
                elif not running_now and was_running:
                    self._chosen_variant.pop(pname, None)

                self._process_was_running[pname] = running_now

            
            
            for stale in list(self._chosen_variant.keys()):
                if stale not in group_by_process:
                    self._chosen_variant.pop(stale, None)

            
            
            
            match_process = None
            match_variant = None
            for pname in group_by_process:
                if pname in running_names and self._chosen_variant.get(pname):
                    match_process = pname
                    match_variant = self._chosen_variant[pname]
                    break

            match_group = group_by_process.get(match_process) if match_process else None
            self._ensure_cdp_watcher(match_process, match_group)

            if match_process is not None:
                self._last_match_time = time.time()
                is_new_activation = (
                    self._active_process != match_process or self._active_variant is not match_variant
                )
                snapshot = (
                    self._cdp_watcher.get_snapshot()
                    if match_group.get("cdp_watch") and self._cdp_watcher is not None
                    else None
                )
                if self._session_process != match_process or self._session_start_time is None:
                    self._session_process = match_process
                    self._session_start_time = int(time.time())

                if is_new_activation:
                    self._apply_variant(
                        match_process,
                        match_variant,
                        live_snapshot=snapshot,
                        force=True,
                    )
                    self.set_status(f"Active: {match_variant.get('app_name')}")
                elif snapshot is not None:
                    
                    
                    
                    self._apply_variant(match_process, match_variant, live_snapshot=snapshot, announce=False)
                self._maybe_push_widget_v2(match_process, match_group, snapshot)
            else:
                if self._active_process is not None:
                    self.log(f"'{self._active_process}' closed. Clearing activity.")
                    self._widget_v2_state.pop(self._active_process, None)
                    self._widget_v2_warned_no_cdp.discard(self._active_process)
                    self._widget_v2_warned_no_creds.discard(self._active_process)
                    self._session_process = None
                    self._session_start_time = None
                    self._last_presence_signature = None
                    self._disconnect()
                    self.set_status("Monitoring - waiting for a match...")

            try:
                idle_minutes = float(self._get_idle_stop_minutes() or 0)
            except (TypeError, ValueError):
                idle_minutes = 0
            if idle_minutes > 0 and (time.time() - self._last_match_time) >= idle_minutes * 60:
                self.log(
                    f"No monitored process found for {idle_minutes:g} minute(s) -- "
                    f"stopping automatically. Click Start Monitoring when you're ready again."
                )
                stopped_idle = True
                break

            interval = max(2, int(self._get_interval() or DEFAULT_INTERVAL))
            self._stop_event.wait(interval)

        self._session_process = None
        self._session_start_time = None
        self._last_presence_signature = None
        self._disconnect()
        self._ensure_cdp_watcher(None, None)
        self.log("Monitor stopped.")
        self.set_status("Stopped (idle timeout)" if stopped_idle else "Stopped")

