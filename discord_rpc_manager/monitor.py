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


class RPCMonitor(threading.Thread):
    """
    Polls running processes on an interval and matches them against the
    configured groups. The first time a group's process is seen running
    (i.e. it just started), a variant is randomly chosen from that group
    and stays active for as long as the process keeps running. When the
    process closes, the choice is forgotten so the next launch can re-roll.

    Because each Discord "Application" has its own Client ID, switching
    from one active variant to another requires closing the old RPC
    connection and opening a fresh one for the new Client ID.
    """

    def __init__(self, get_groups, get_interval, log_queue, status_queue):
        super().__init__(daemon=True)
        self._get_groups = get_groups
        self._get_interval = get_interval
        self._log_queue = log_queue
        self._status_queue = status_queue
        self._stop_event = threading.Event()
        self._rpc = None
        self._connect_time = None

        
        
        
        self._process_was_running = {}
        self._chosen_variant = {}  

        
        self._active_process = None
        self._active_variant = None

        
        
        
        self._cdp_watcher = None
        self._cdp_watcher_owner = None

    def stop(self):
        self._stop_event.set()

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

    def _apply_variant(self, process_name, variant, live_snapshot=None, announce=True):
        """Connect (or reconnect if the client id changed) and push presence.
        If live_snapshot is given, the variant's state/details are treated
        as format-string templates (e.g. "HQ Lv.{admiral_level}") filled
        from that snapshot instead of used as literal text. announce=False
        suppresses the activity-log line, for silent periodic live-data
        refreshes of an already-active variant (otherwise the log would
        get a new line every scan interval just because HP ticked up)."""
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

        name_text = safe_format(variant.get("name"), live_snapshot) if live_snapshot is not None else variant.get("name")
        state_text = safe_format(variant.get("state"), live_snapshot) if live_snapshot is not None else variant.get("state")
        details_text = safe_format(variant.get("details"), live_snapshot) if live_snapshot is not None else variant.get("details")

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
            payload["start"] = self._connect_time or int(time.time())

        try:
            party_max = int(variant.get("party_max") or 0)
        except (TypeError, ValueError):
            party_max = 0
        if party_max > 0:
            if variant.get("party_current_dynamic", False) and live_snapshot is not None:
                try:
                    party_current = int(safe_format("{ship_count}", live_snapshot))
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

        try:
            self._rpc.update(**payload)
            self._active_process = process_name
            self._active_variant = variant
            if announce:
                self.log(f"Rich Presence active: '{variant.get('app_name')}'.")
            return True
        except Exception as e:
            self.log(f"Failed to update Discord presence: {e}")
            return False

    def run(self):
        self.log("Monitor started.")
        self.set_status("Monitoring - waiting for a match...")
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
                is_new_activation = (
                    self._active_process != match_process or self._active_variant is not match_variant
                )
                snapshot = (
                    self._cdp_watcher.get_snapshot()
                    if match_group.get("cdp_watch") and self._cdp_watcher is not None
                    else None
                )
                if is_new_activation:
                    self._apply_variant(match_process, match_variant, live_snapshot=snapshot)
                    self.set_status(f"Active: {match_variant.get('app_name')}")
                elif snapshot is not None:
                    
                    
                    
                    self._apply_variant(match_process, match_variant, live_snapshot=snapshot, announce=False)
            else:
                if self._active_process is not None:
                    self.log(f"'{self._active_process}' closed. Clearing activity.")
                    self._disconnect()
                    self.set_status("Monitoring - waiting for a match...")

            interval = max(2, int(self._get_interval() or DEFAULT_INTERVAL))
            self._stop_event.wait(interval)

        self._disconnect()
        self._ensure_cdp_watcher(None, None)
        self.log("Monitor stopped.")
        self.set_status("Stopped")

