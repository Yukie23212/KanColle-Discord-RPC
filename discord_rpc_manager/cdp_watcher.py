# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import json
import os
import re
import sys
import threading
import time
import urllib.request
import urllib.error
import urllib.parse

from .constants import CDP_GAME_TARGET_HINT
from .constants import RUNTIME_DATA_DIR_NAME


MAP_EDGE_URL = (
    "https://raw.githubusercontent.com/kcwiki/kancolle-data/"
    "master/map/edge.json"
)
MAP_EDGE_CACHE_NAME = "kancolle_map_edges.json"
MAP_EDGE_REFRESH_SECONDS = 24 * 60 * 60

QUEST_TITLE_TRANSLATIONS_NAME = "quest_title_translations.json"
QUEST_TITLE_TRANSLATIONS_URL = (
    "https://raw.githubusercontent.com/Yukie23212/KanColle-Discord-RPC/"
    "refs/heads/main/discord_rpc_manager/quest_title_translations.json"
)

QUEST_ID_TRANSLATIONS_NAME = "kccp_quest_translations.json"
QUEST_ID_TRANSLATIONS_URL = (
    "https://raw.githubusercontent.com/Oradimi/KanColle-English-Patch-KCCP/"
    "refs/heads/master/EN-patch/kcs2/js/main.js/ignore-raw_text_translations/"
    "ignore-_quests.json"
)

SHIP_BANNER_ID_MAP_NAME = "ship_banner_id_map.json"
SHIP_BANNER_ID_MAP_URL = (
    "https://raw.githubusercontent.com/Yukie23212/KanColle-Discord-RPC/"
    "refs/heads/main/discord_rpc_manager/ship_banner_id_map.json"
)

# This is intentionally account-local runtime data. It is never downloaded
# from an upstream/community source.
SHIP_INSTANCE_MASTER_MAP_NAME = "ship_instance_master_map.json"

SHIP_NAME_CACHE_NAME = "kancolle_ship_names.json"
SHIP_MASTER_DATA_URL = (
    "https://raw.githubusercontent.com/kcwiki/kancolle-data/"
    "refs/heads/master/wiki/ship.json"
)

SOURCE_UPDATE_CHECK_SECONDS = 24 * 60 * 60
SOURCE_METADATA_NAME = "data_source_state.json"


def _runtime_data_path(name):
    return os.path.join(_data_cache_base_dir(), name)


def _data_cache_base_dir():
    base_dir = (
        os.path.dirname(sys.executable)
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    path = os.path.join(base_dir, RUNTIME_DATA_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _source_metadata_path():
    return _runtime_data_path(SOURCE_METADATA_NAME)


def _load_source_metadata():
    try:
        with open(_source_metadata_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_source_metadata(data):
    try:
        path = _source_metadata_path()
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except OSError:
        pass


def _load_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_file(path, data):
    try:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return True
    except OSError:
        return False


def _source_request(url, method="GET", headers=None, timeout=8):
    req_headers = {"User-Agent": "DiscordRPCManager/1.0"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "status": getattr(resp, "status", 200),
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
                "body": resp.read() if method != "HEAD" else b"",
            }
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return {
                "status": 304,
                "etag": e.headers.get("ETag"),
                "last_modified": e.headers.get("Last-Modified"),
                "body": b"",
            }
        raise


def _record_source_headers(metadata, name, url, response, checked_at=None):
    metadata[name] = {
        "url": url,
        "etag": response.get("etag"),
        "last_modified": response.get("last_modified"),
        "last_checked": checked_at if checked_at is not None else time.time(),
    }


def _sync_json_source(
    name,
    url,
    transform=lambda data: data,
    validate=lambda data: isinstance(data, dict),
    log_fn=None,
):
    if not url:
        if log_fn:
            log_fn(f"[Data] {name}: source URL not configured; using local/bundled copy.")
        return

    runtime_path = _runtime_data_path(name)
    local_data = _load_json_file(runtime_path)
    bundled_data = None
    if local_data is None:
        bundled_candidates = []
        if getattr(sys, "frozen", False):
            bundled_candidates.extend([
                os.path.join(getattr(sys, "_MEIPASS", ""), name),
                os.path.join(getattr(sys, "_MEIPASS", ""), "discord_rpc_manager", name),
            ])
        bundled_candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
        for candidate in bundled_candidates:
            if os.path.abspath(candidate) == os.path.abspath(runtime_path):
                continue
            bundled_data = _load_json_file(candidate)
            if bundled_data is not None:
                break

    metadata = _load_source_metadata()
    state = metadata.get(name) if isinstance(metadata.get(name), dict) else {}
    now = time.time()

    def _log(msg):
        if log_fn:
            log_fn(msg)

    # Missing/corrupt runtime file: download now. If that fails, restore the
    # bundled copy. This is the explicit recovery path requested for packaged
    # builds.
    if local_data is None:
        try:
            response = _source_request(url, method="GET")
            source = json.loads(response["body"].decode("utf-8"))
            transformed = transform(source)
            if validate(transformed) and _write_json_file(runtime_path, transformed):
                _record_source_headers(metadata, name, url, response, now)
                _save_source_metadata(metadata)
                _log(f"[Data] {name}: missing/invalid local file — downloaded from {url}.")
                return
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as e:
            _log(f"[Data] {name}: source download failed ({e}).")

        if bundled_data is not None:
            try:
                transformed_bundled = transform(bundled_data)
            except Exception:
                transformed_bundled = None
            if transformed_bundled is not None and validate(transformed_bundled) and _write_json_file(runtime_path, transformed_bundled):
                _log(f"[Data] {name}: restored from bundled recovery copy.")
                return
        return

    # Valid existing file: never replace it just because the app launched.
    # Only perform an upstream check when the interval has elapsed.
    try:
        last_checked = float(state.get("last_checked") or 0)
    except (TypeError, ValueError):
        last_checked = 0
    if now - last_checked < SOURCE_UPDATE_CHECK_SECONDS and state.get("url") == url:
        return

    conditional_headers = {}
    if state.get("url") == url:
        if state.get("etag"):
            conditional_headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            conditional_headers["If-Modified-Since"] = state["last_modified"]

    try:
        if not conditional_headers:
            try:
                head = _source_request(url, method="HEAD")
                _record_source_headers(metadata, name, url, head, now)
                _save_source_metadata(metadata)
                _log(f"[Data] {name}: source version recorded — {url}; existing local copy kept.")
                return
            except (urllib.error.URLError, TimeoutError, OSError, urllib.error.HTTPError):
                # Fall through to a normal conditional-less GET.
                pass

        response = _source_request(url, method="GET", headers=conditional_headers)
        if response["status"] == 304:
            _record_source_headers(metadata, name, url, response, now)
            _save_source_metadata(metadata)
            _log(f"[Data] {name}: source unchanged — local copy kept.")
            return

        source = json.loads(response["body"].decode("utf-8"))
        transformed = transform(source)
        if not validate(transformed):
            raise ValueError("source data failed validation")
        if _write_json_file(runtime_path, transformed):
            _record_source_headers(metadata, name, url, response, now)
            _save_source_metadata(metadata)
            _log(f"[Data] {name}: source updated — downloaded new version from {url}.")
    except (urllib.error.URLError, TimeoutError, OSError, urllib.error.HTTPError, json.JSONDecodeError, ValueError) as e:
        # A failed refresh must never destroy a working local dataset.
        metadata[name] = {
            **state,
            "url": url,
            "last_checked": now,
        }
        _save_source_metadata(metadata)
        _log(f"[Data] {name}: update check failed ({e}); keeping local copy.")


def _load_json_mapping(candidates):
    for path in candidates:
        if not path:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _data_file_candidates(name):
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), RUNTIME_DATA_DIR_NAME, name))
        candidates.append(os.path.join(os.path.dirname(sys.executable), name))
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", ""), name))
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", ""), "discord_rpc_manager", name))
    else:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), RUNTIME_DATA_DIR_NAME, name))
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
        candidates.append(os.path.join(os.path.dirname(sys.executable), name))
    return candidates


def _data_cache_path(name):
    return _runtime_data_path(name)




def _load_quest_title_translations(log_fn=None):
    _sync_json_source(
        QUEST_TITLE_TRANSLATIONS_NAME,
        QUEST_TITLE_TRANSLATIONS_URL,
        log_fn=log_fn,
    )
    return _load_json_mapping(_data_file_candidates(QUEST_TITLE_TRANSLATIONS_NAME))


def _transform_kccp_quest_translations(source):
    if not isinstance(source, dict):
        raise ValueError("KCCP quest source is not an object")

    keys = list(source.keys())
    result = {}
    marker_re = re.compile(r"^_quest_id_(\d+)$")

    for index, key in enumerate(keys):
        match = marker_re.fullmatch(str(key))
        if not match:
            continue

        quest_id = str(int(match.group(1)))
        entry = {"code": source.get(key, "")}

        title_key = keys[index + 1] if index + 1 < len(keys) else None
        description_key = keys[index + 2] if index + 2 < len(keys) else None

        if (
            title_key is not None
            and not marker_re.fullmatch(str(title_key))
            and title_key not in source
        ):
            title_key = None
        if (
            description_key is not None
            and not marker_re.fullmatch(str(description_key))
            and description_key not in source
        ):
            description_key = None

        if title_key is not None and not marker_re.fullmatch(str(title_key)):
            entry["title"] = source.get(title_key, "")
        if description_key is not None and not marker_re.fullmatch(str(description_key)):
            entry["description"] = source.get(description_key, "")

        if entry.get("title") not in (None, ""):
            result[quest_id] = entry

    if not result:
        raise ValueError("KCCP quest source contained no usable quest translations")
    return result


def _load_quest_id_translations(log_fn=None):
    _sync_json_source(
        QUEST_ID_TRANSLATIONS_NAME,
        QUEST_ID_TRANSLATIONS_URL,
        transform=_transform_kccp_quest_translations,
        validate=lambda data: isinstance(data, dict) and bool(data),
        log_fn=log_fn,
    )
    return _load_json_mapping(_data_file_candidates(QUEST_ID_TRANSLATIONS_NAME))


def _load_ship_banner_id_map(log_fn=None):
    _sync_json_source(
        SHIP_BANNER_ID_MAP_NAME,
        SHIP_BANNER_ID_MAP_URL,
        log_fn=log_fn,
    )
    return _load_json_mapping(_data_file_candidates(SHIP_BANNER_ID_MAP_NAME))


def _load_ship_instance_master_map():
    data = _load_json_mapping(_data_file_candidates(SHIP_INSTANCE_MASTER_MAP_NAME))
    normalized = {}
    for ship_id, entry in data.items():
        try:
            ship_key = str(int(ship_id))
        except (TypeError, ValueError):
            continue

        if isinstance(entry, dict):
            try:
                master_id = int(entry.get("master_id"))
            except (TypeError, ValueError):
                continue
            name = entry.get("name", "")
            normalized[ship_key] = {
                "master_id": master_id,
                "name": str(name) if name not in (None, "") else "",
            }
            continue

        try:
            normalized[ship_key] = {"master_id": int(entry), "name": ""}
        except (TypeError, ValueError):
            continue
    return normalized


def _load_ship_name_cache():
    return _load_json_mapping(_data_file_candidates(SHIP_NAME_CACHE_NAME))


EXPEDITION_DETAILS_TEMPLATE = "Expedition Complete: Fleet {fleet_name} 「{fleet_ship_count}/6 ships」"


_MAP_EDGES = None
_MAP_EDGES_LOADED_AT = 0.0
_MAP_EDGES_LOCK = threading.Lock()


def _map_edge_cache_path():
    return _runtime_data_path(MAP_EDGE_CACHE_NAME)


def _load_map_edges(log_fn=None):
    global _MAP_EDGES, _MAP_EDGES_LOADED_AT

    now = time.time()
    with _MAP_EDGES_LOCK:
        if _MAP_EDGES is not None and (now - _MAP_EDGES_LOADED_AT) < MAP_EDGE_REFRESH_SECONDS:
            return _MAP_EDGES

        cache_path = _map_edge_cache_path()
        local_data = _load_json_file(cache_path) or {}
        runtime_missing = not bool(local_data)

        if not local_data:
            bundled_candidates = _data_file_candidates(MAP_EDGE_CACHE_NAME)
            for candidate in bundled_candidates:
                if os.path.abspath(candidate) == os.path.abspath(cache_path):
                    continue
                candidate_data = _load_json_file(candidate)
                if candidate_data:
                    local_data = candidate_data
                    _write_json_file(cache_path, candidate_data)
                    if log_fn:
                        log_fn(f"[Data] {MAP_EDGE_CACHE_NAME}: missing/invalid local file — restored bundled recovery copy.")
                    break

        metadata = _load_source_metadata()
        state = metadata.get(MAP_EDGE_CACHE_NAME) if isinstance(metadata.get(MAP_EDGE_CACHE_NAME), dict) else {}

        try:
            last_checked = float(state.get("last_checked") or 0)
        except (TypeError, ValueError):
            last_checked = 0

        remote_data = None
        should_check = (
            runtime_missing
            or now - last_checked >= MAP_EDGE_REFRESH_SECONDS
            or state.get("url") != MAP_EDGE_URL
        )
        if should_check:
            conditional_headers = {}
            if state.get("url") == MAP_EDGE_URL:
                if state.get("etag"):
                    conditional_headers["If-None-Match"] = state["etag"]
                if state.get("last_modified"):
                    conditional_headers["If-Modified-Since"] = state["last_modified"]

            try:
                if not conditional_headers and not runtime_missing:
                    try:
                        head = _source_request(MAP_EDGE_URL, method="HEAD")
                        _record_source_headers(metadata, MAP_EDGE_CACHE_NAME, MAP_EDGE_URL, head, now)
                        _save_source_metadata(metadata)
                        if log_fn:
                            log_fn(f"[Data] {MAP_EDGE_CACHE_NAME}: source version recorded — {MAP_EDGE_URL}; existing local copy kept.")
                    except (urllib.error.URLError, TimeoutError, OSError, urllib.error.HTTPError):
                        response = _source_request(MAP_EDGE_URL, method="GET")
                        candidate = json.loads(response["body"].decode("utf-8"))
                        if isinstance(candidate, dict):
                            remote_data = candidate
                            _record_source_headers(metadata, MAP_EDGE_CACHE_NAME, MAP_EDGE_URL, response, now)
                            _save_source_metadata(metadata)
                elif not conditional_headers and runtime_missing:
                    response = _source_request(MAP_EDGE_URL, method="GET")
                    candidate = json.loads(response["body"].decode("utf-8"))
                    if isinstance(candidate, dict):
                        remote_data = candidate
                        _record_source_headers(metadata, MAP_EDGE_CACHE_NAME, MAP_EDGE_URL, response, now)
                        _save_source_metadata(metadata)
                else:
                    response = _source_request(MAP_EDGE_URL, method="GET", headers=conditional_headers)
                    if response["status"] == 304:
                        _record_source_headers(metadata, MAP_EDGE_CACHE_NAME, MAP_EDGE_URL, response, now)
                        _save_source_metadata(metadata)
                        if log_fn:
                            log_fn(f"[Data] {MAP_EDGE_CACHE_NAME}: source unchanged — local copy kept.")
                    else:
                        candidate = json.loads(response["body"].decode("utf-8"))
                        if isinstance(candidate, dict):
                            remote_data = candidate
                            _record_source_headers(metadata, MAP_EDGE_CACHE_NAME, MAP_EDGE_URL, response, now)
                            _save_source_metadata(metadata)
            except (urllib.error.URLError, TimeoutError, OSError, urllib.error.HTTPError, json.JSONDecodeError):
                metadata[MAP_EDGE_CACHE_NAME] = {**state, "url": MAP_EDGE_URL, "last_checked": now}
                _save_source_metadata(metadata)
                if log_fn:
                    log_fn(f"[Data] {MAP_EDGE_CACHE_NAME}: update check failed; keeping local copy.")

        if remote_data is not None:
            # Preserve a richer local dataset if the upstream currently has
            # fewer top-level maps, as the existing implementation did.
            if len(remote_data) >= len(local_data):
                local_data = remote_data
                if _write_json_file(cache_path, local_data) and log_fn:
                    log_fn(f"[Data] {MAP_EDGE_CACHE_NAME}: source updated — downloaded new version from {MAP_EDGE_URL}.")
            elif log_fn:
                log_fn(
                    f"[Data] {MAP_EDGE_CACHE_NAME}: source returned fewer maps "
                    f"({len(remote_data)} vs local {len(local_data)}); keeping local copy."
                )

        _MAP_EDGES = local_data or {}
        _MAP_EDGES_LOADED_AT = now
        return _MAP_EDGES


def get_map_node_label(map_area, map_info, api_no, log_fn=None):
    try:
        map_key = f"{int(map_area)}{int(map_info)}"
        cell_key = str(int(api_no))
    except (TypeError, ValueError):
        return ""

    edges = _load_map_edges(log_fn)
    edge = edges.get(map_key, {}).get(cell_key)

    
    
    
    if isinstance(edge, list) and len(edge) >= 2:
        return str(edge[1])
    return ""

try:
    import websocket
    CDP_AVAILABLE = True
except Exception:
    CDP_AVAILABLE = False


class KancolleCDPWatcher(threading.Thread):
    TRANSIENT_STATUS_HOLD_SECONDS = 45
    EXPEDITION_RESULT_HOLD_SECONDS = 10

    def __init__(self, cdp_port, log_fn):
        super().__init__(daemon=True)
        self._cdp_port = cdp_port
        self._log = log_fn
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self._snapshot = {
            "map_area": "-",
            "map_info": "-",
            "location_text": "",
            "map_cell_no": "-",
            "map_cell_id": "-",
            "api_no": "-",
            "api_id": "-",
            "map_node": "",
            "map_node_text": "",
            "battle_rank": "",
            "battle_rank_only": "",
            "fleet1_summary": "",
            "sortie_win": "?",
            "sortie_lose": "?",
            "expedition_success": "?",
            "expedition_count": "?",
            "expedition_result": "",
            "quest_count": "?",
            "quest_active_count": "?",
            "quest_tab_id": "?",
            "quest_id": "",
            "quest_title": "",
            "quest_category": "",
            "quest_type": "",
            "quest_state": "",
            "quest_progress": "",
            "quest_event": "",
            "quest_reward_fuel": "",
            "quest_reward_ammo": "",
            "quest_reward_steel": "",
            "quest_reward_bauxite": "",
            "quest_bonus_count": "",
            "quest_bonus_summary": "",
            "repair_dock_count": "?",
            "repair_active_count": "?",
            "repair_dock_id": "",
            "repair_ship_id": "",
            "repair_ship_master_id": "",
            "repair_ship_name": "",
            "repair_state": "",
            "repair_complete_time": "",
            "repair_complete_time_str": "",
            "repair_item1": "",
            "repair_item2": "",
            "repair_item3": "",
            "repair_item4": "",
            "repair_event": "",
            "presence_stage": "in_port",
            "presence_stage_hold_until": 0.0,
            "presence_stage_after_hold": "in_port",
            "fleet_hp_pct": "?",
            "fleet_damaged_count": "?",
            "fleet_ready_count": "?",
            "fleet_avg_level": "?",
            "flamethrower": "?",
            "bucket": "?",
            "dev_material": "?",
            "screw": "?",
            "resource_total": "?",
            "presence_details_override": "",
            "fleet_total_slots": "?",
            "api_id": "?",
        }
        self._warned_once = False
        self._seen_endpoints = set()
        self._seen_problems = set()
        self._known_fleets = {}
        self._known_ships = {}
        self._known_quests = {}
        self._quest_title_translations = _load_quest_title_translations(self._log)
        self._quest_id_translations = _load_quest_id_translations(self._log)
        self._ship_banner_id_map = _load_ship_banner_id_map(self._log)
        self._ship_instance_master_map = _load_ship_instance_master_map()
        self._ship_master_names = _load_ship_name_cache()
        self._ship_name_fetch_attempted = False
        self._refresh_ship_name_cache()
        self._repair_docks = {}
        self._repair_selected_dock_id = None
        self._last_ship_banner = None
        self._seen_ship_banner_entries = set()
        self._transient_status_until = 0.0
        self._fleet1_name = None
        self._fleet1_ship_count = None
        self._fleet1_total_slots = None
        self._presence_stage_context = {}
        self._kancolle_debug_last = None

    @staticmethod
    def _stage_display(stage):
        return {
            "in_port": "In Port",
            "on_sortie": "On Sortie",
            "in_battle": "In Battle",
            "night_battle": "Night Battle",
            "battle_result": "Battle Result",
            "quest": "Quest",
            "repair_dock": "Repair Dock",
            "exercise_opponent": "Exercise: Choose Opponent",
            "exercise_battle": "Exercise: Battle",
            "exercise_night_battle": "Exercise: Night Battle",
            "exercise_result": "Exercise: Result",
            "expedition_result": "Expedition Result",
        }.get(stage, str(stage or ""))

    @staticmethod
    def _quest_progress_text(value):
        try:
            flag = int(value)
        except (TypeError, ValueError):
            return "" if value in (None, "") else str(value)
        return {0: "0%", 1: "50%", 2: "80%", 100: "100%"}.get(flag, str(value))

    @staticmethod
    def _format_remaining(seconds):
        if seconds <= 0:
            return "Done"
        total = int(seconds)
        hours, rem = divmod(total, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes:02d}m {secs:02d}s"
        if minutes:
            return f"{minutes}m {secs:02d}s"
        return f"{secs}s"

    @classmethod
    def _repair_remaining_text(cls, value):
        try:
            raw = int(value)
        except (TypeError, ValueError):
            return ""
        # KanColle completion timestamps are milliseconds since epoch.
        return cls._format_remaining((raw / 1000.0) - time.time())

    @staticmethod
    def _map_display(snapshot):
        area = str(snapshot.get("map_area", "") or "").strip()
        info = str(snapshot.get("map_info", "") or "").strip()
        if not area or not info or area == "-" or info == "-":
            return ""
        text = f"World {area}-{info}"
        node = str(snapshot.get("map_node", "") or "").strip()
        if node:
            text += f" Node {node}"
        return text

    def _sync_ship_records(self, ships, persist_instance_master_map=False):
        if not isinstance(ships, list):
            return

        mapping_changed = False
        for ship in ships:
            if not isinstance(ship, dict):
                continue

            instance_id = ship.get("api_id")
            if instance_id in (None, ""):
                continue

            try:
                instance_key = str(int(instance_id))
            except (TypeError, ValueError):
                continue

            self._known_ships[instance_key] = ship

            master_id = ship.get("api_ship_id")
            if master_id in (None, ""):
                continue
            try:
                master_value = int(master_id)
            except (TypeError, ValueError):
                continue

            if not persist_instance_master_map:
                continue

            name = self._resolve_ship_name(master_value)
            current = self._ship_instance_master_map.get(instance_key)
            desired = {
                "master_id": master_value,
                "name": name,
            }
            if not isinstance(current, dict) or current != desired:
                self._ship_instance_master_map[instance_key] = desired
                mapping_changed = True

        if persist_instance_master_map and mapping_changed:
            self._persist_ship_instance_master_map()

    def _fleet1_computed_fields(self, ship_ids):
        hp_pairs = []
        levels = []
        for ship_id in ship_ids:
            record = self._known_ships.get(str(ship_id))
            if not isinstance(record, dict):
                continue
            try:
                now_hp = float(record.get("api_nowhp"))
                max_hp = float(record.get("api_maxhp"))
                if max_hp > 0:
                    hp_pairs.append((now_hp, max_hp))
            except (TypeError, ValueError):
                pass
            try:
                level = float(record.get("api_lv"))
                levels.append(level)
            except (TypeError, ValueError):
                pass

        if hp_pairs:
            total_now = sum(pair[0] for pair in hp_pairs)
            total_max = sum(pair[1] for pair in hp_pairs)
            hp_pct = round((total_now / total_max) * 100) if total_max else 0
            damaged = sum(1 for now_hp, max_hp in hp_pairs if now_hp < max_hp)
            ready = sum(1 for now_hp, max_hp in hp_pairs if now_hp >= max_hp)
        else:
            hp_pct = "?"
            damaged = "?"
            ready = "?"

        avg_level = round(sum(levels) / len(levels)) if levels else "?"
        return {
            "fleet_hp_pct": hp_pct,
            "fleet_damaged_count": damaged,
            "fleet_ready_count": ready,
            "fleet_avg_level": avg_level,
        }

    def _clear_quest_context(self):
        self._update_snapshot({
            "quest_count": "?",
            "quest_active_count": "?",
            "quest_tab_id": "?",
            "quest_id": "",
            "quest_title": "",
            "quest_category": "",
            "quest_type": "",
            "quest_state": "",
            "quest_progress": "",
            "quest_event": "",
            "quest_reward_fuel": "",
            "quest_reward_ammo": "",
            "quest_reward_steel": "",
            "quest_reward_bauxite": "",
            "quest_bonus_count": "",
            "quest_bonus_summary": "",
        })

    def _translate_quest_title(self, title, quest_id=None):
        if quest_id not in (None, ""):
            try:
                quest_key = str(int(quest_id))
            except (TypeError, ValueError):
                quest_key = str(quest_id)

            translated = self._quest_id_translations.get(quest_key)
            if isinstance(translated, dict):
                translated_title = translated.get("title", "")
                if translated_title not in (None, ""):
                    return str(translated_title)

        if not title:
            return ""
        return self._quest_title_translations.get(title, title)

    @staticmethod
    def _extract_ship_banner_master_id(url):
        try:
            path = urllib.parse.urlsplit(str(url)).path
        except (TypeError, ValueError):
            return None
        match = re.search(r"/kcs2/resources/ship/(?:banner|banner_dmg)/(\d{4})_\d+\.png$", path)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _record_ship_banner(self, url, start_time=None):
        master_id = self._extract_ship_banner_master_id(url)
        if master_id is None:
            return
        self._last_ship_banner = {
            "master_id": master_id,
            "url": str(url),
            "seen_at": time.time(),
            "start_time": start_time,
        }

    def _refresh_ship_name_cache(self):
        if self._ship_name_fetch_attempted:
            return

        def transform(source):
            if not isinstance(source, dict):
                raise ValueError("ship source is not an object")
            names = {}
            for entry in source.values():
                if not isinstance(entry, dict):
                    continue
                api_id = entry.get("_api_id")
                if api_id in (None, False, ""):
                    continue
                try:
                    key = str(int(api_id))
                except (TypeError, ValueError):
                    continue
                name = entry.get("_full_name") or entry.get("_name")
                if name:
                    names[key] = str(name)
            if not names:
                raise ValueError("ship source contained no usable API-ID/name entries")
            return names
        _sync_json_source(
            SHIP_NAME_CACHE_NAME,
            SHIP_MASTER_DATA_URL,
            transform=transform,
            validate=lambda data: isinstance(data, dict) and bool(data),
            log_fn=self._log,
        )

        self._ship_master_names = _load_ship_name_cache()
        self._ship_name_fetch_attempted = True

    def _resolve_ship_name(self, master_id):
        if master_id in (None, ""):
            return ""
        key = str(master_id)
        name = self._ship_master_names.get(key)
        if name:
            return str(name)
        self._refresh_ship_name_cache()
        return str(self._ship_master_names.get(key, ""))

    def _persist_ship_instance_master_map(self):
        try:
            with open(_data_cache_path(SHIP_INSTANCE_MASTER_MAP_NAME), "w", encoding="utf-8") as f:
                json.dump(
                    dict(sorted(self._ship_instance_master_map.items(), key=lambda item: int(item[0]))),
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except (OSError, ValueError):
            pass

    def _save_ship_instance_master_mapping(self, ship_id, master_id, name=None):
        """Update the persistent cache for a single instance.

        This helper is retained for compatibility, but authoritative callers
        should prefer _sync_ship_records(..., persist_instance_master_map=True)
        so /api_port/port remains the source of truth.
        """
        try:
            ship_key = str(int(ship_id))
            master_value = int(master_id)
        except (TypeError, ValueError):
            return

        current = self._ship_instance_master_map.get(ship_key)
        current_name = current.get("name", "") if isinstance(current, dict) else ""
        desired_name = current_name if name in (None, "") else str(name)
        desired = {"master_id": master_value, "name": desired_name}
        if current == desired:
            return

        self._ship_instance_master_map[ship_key] = desired
        self._persist_ship_instance_master_map()

    def _lookup_ship_instance_record(self, ship_id):
        if ship_id in (None, ""):
            return None
        try:
            entry = self._ship_instance_master_map.get(str(int(ship_id)))
        except (TypeError, ValueError):
            return None
        return entry if isinstance(entry, dict) else None

    def _lookup_ship_instance_master_id(self, ship_id):
        record = self._lookup_ship_instance_record(ship_id)
        return record.get("master_id") if record else None

    def _lookup_ship_instance_name(self, ship_id):
        record = self._lookup_ship_instance_record(ship_id)
        return record.get("name", "") if record else ""

    def _associate_repair_ship(self, dock_id, ship_id, master_id=None):
        if dock_id in (None, "") or ship_id in (None, ""):
            return
        dock_key = str(dock_id)
        ship_key = str(ship_id)
        if master_id in (None, ""):

            known_ship = self._known_ships.get(ship_key)
            if isinstance(known_ship, dict):
                master_id = known_ship.get("api_ship_id")

        persistent_name = ""
        if master_id in (None, ""):

            cached = self._lookup_ship_instance_record(ship_key)
            if cached:
                master_id = cached.get("master_id")
                persistent_name = cached.get("name", "")

        if master_id in (None, ""):

            latest = self._last_ship_banner
            if latest and (time.time() - float(latest.get("seen_at") or 0)) <= 8.0:
                master_id = latest.get("master_id")

        record = self._repair_docks.get(dock_key, {})
        if master_id not in (None, ""):
            master_id = int(master_id)
            record["master_id"] = master_id
            record["name"] = persistent_name or self._resolve_ship_name(master_id)
        record["dock_id"] = dock_key
        record["ship_id"] = ship_key
        record["state"] = 1
        self._repair_docks[dock_key] = record

    def _select_repair_record(self, docks):
        active_records = []
        for dock in docks:
            if not isinstance(dock, dict):
                continue
            dock_id = dock.get("api_id")
            if dock_id in (None, ""):
                continue
            dock_key = str(dock_id)
            state = dock.get("api_state")
            ship_id = dock.get("api_ship_id", "")
            if state == 1:
                record = self._repair_docks.get(dock_key, {})
                record.update({
                    "dock_id": dock_key,
                    "ship_id": str(ship_id) if ship_id not in (None, "") else "",
                    "state": state,
                    "complete_time": dock.get("api_complete_time", ""),
                    "complete_time_str": dock.get("api_complete_time_str", ""),
                    "item1": dock.get("api_item1", ""),
                    "item2": dock.get("api_item2", ""),
                    "item3": dock.get("api_item3", ""),
                    "item4": dock.get("api_item4", ""),
                })


                if not record.get("master_id") and record.get("ship_id"):
                    cached = self._lookup_ship_instance_record(record["ship_id"])
                    if cached:
                        record["master_id"] = cached.get("master_id", "")
                        record["name"] = cached.get("name", "")
                        if record.get("master_id") and not record.get("name"):
                            record["name"] = self._resolve_ship_name(record["master_id"])
                elif record.get("master_id") and not record.get("name"):
                    record["name"] = self._resolve_ship_name(record["master_id"])

                self._repair_docks[dock_key] = record
                active_records.append(record)
            else:
                self._repair_docks.pop(dock_key, None)

        selected = None
        if self._repair_selected_dock_id is not None:
            selected = self._repair_docks.get(str(self._repair_selected_dock_id))
            if not selected or selected.get("state") != 1:
                self._repair_selected_dock_id = None
                selected = None
        return selected or (active_records[0] if active_records else None)

    def _update_repair_snapshot_from_record(self, record):
        if not record:
            self._update_snapshot({
                "repair_dock_id": "",
                "repair_ship_id": "",
                "repair_ship_master_id": "",
                "repair_ship_name": "",
                "repair_state": "",
                "repair_complete_time": "",
                "repair_complete_time_str": "",
                "repair_item1": "",
                "repair_item2": "",
                "repair_item3": "",
                "repair_item4": "",
                "repair_event": "",
            })
            return
        self._update_snapshot({
            "repair_dock_id": record.get("dock_id", ""),
            "repair_ship_id": record.get("ship_id", ""),
            "repair_ship_master_id": record.get("master_id", ""),
            "repair_ship_name": record.get("name", ""),
            "repair_state": record.get("state", ""),
            "repair_complete_time": record.get("complete_time", ""),
            "repair_complete_time_str": record.get("complete_time_str", ""),
            "repair_item1": record.get("item1", ""),
            "repair_item2": record.get("item2", ""),
            "repair_item3": record.get("item3", ""),
            "repair_item4": record.get("item4", ""),
            "repair_event": "Repairing" if str(record.get("state", "")) == "1" else "",
        })

    def _debug(self, message):
        if self._log is not None:
            self._log(f"[CDP-DEBUG] {message}")

    @staticmethod
    def _format_k(val):
        try:
            num = int(val)
            return f"{round(num / 1000)}k" if num >= 1000 else str(num)
        except (ValueError, TypeError):
            return str(val)

    @staticmethod
    def _raw_material_value(mat_dict, item_id):
        value = mat_dict.get(item_id, "?")
        if value in (None, ""):
            return "?"
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _resource_fields(materials):
        mat_dict = {
            m.get("api_id"): m.get("api_value")
            for m in materials
            if isinstance(m, dict)
        }
        raw_values = []
        for item_id in (1, 2, 3, 4):
            value = mat_dict.get(item_id)
            try:
                raw_values.append(int(value))
            except (TypeError, ValueError):
                return {
                    "fuel": KancolleCDPWatcher._format_k(mat_dict.get(1, "?")),
                    "ammo": KancolleCDPWatcher._format_k(mat_dict.get(2, "?")),
                    "steel": KancolleCDPWatcher._format_k(mat_dict.get(3, "?")),
                    "bauxite": KancolleCDPWatcher._format_k(mat_dict.get(4, "?")),
                    "flamethrower": KancolleCDPWatcher._raw_material_value(mat_dict, 5),
                    "bucket": KancolleCDPWatcher._raw_material_value(mat_dict, 6),
                    "dev_material": KancolleCDPWatcher._raw_material_value(mat_dict, 7),
                    "screw": KancolleCDPWatcher._raw_material_value(mat_dict, 8),
                    "resource_total": "?",
                }
        return {
            "fuel": KancolleCDPWatcher._format_k(mat_dict.get(1, "?")),
            "ammo": KancolleCDPWatcher._format_k(mat_dict.get(2, "?")),
            "steel": KancolleCDPWatcher._format_k(mat_dict.get(3, "?")),
            "bauxite": KancolleCDPWatcher._format_k(mat_dict.get(4, "?")),
            "flamethrower": KancolleCDPWatcher._raw_material_value(mat_dict, 5),
            "bucket": KancolleCDPWatcher._raw_material_value(mat_dict, 6),
            "dev_material": KancolleCDPWatcher._raw_material_value(mat_dict, 7),
            "screw": KancolleCDPWatcher._raw_material_value(mat_dict, 8),
            "resource_total": sum(raw_values),
        }

    def stop(self):
        self._stop_event.set()

    def get_snapshot(self):
        with self._lock:
            self._expire_presence_stage_locked()
            snapshot = dict(self._snapshot)
            if (
                snapshot.get("presence_stage") == "expedition_result"
                and self._presence_stage_context
            ):
                snapshot.update(self._presence_stage_context)
            snapshot["stage"] = self._stage_display(snapshot.get("presence_stage"))
            snapshot["map_display"] = self._map_display(snapshot)
            snapshot["quest_progress_text"] = self._quest_progress_text(snapshot.get("quest_progress"))
            snapshot["repair_remaining"] = self._repair_remaining_text(snapshot.get("repair_complete_time"))
            return snapshot

    def _expire_presence_stage_locked(self):
        hold_until = float(self._snapshot.get("presence_stage_hold_until") or 0)
        if hold_until <= 0 or time.time() < hold_until:
            return
        after_hold = self._snapshot.get("presence_stage_after_hold") or "in_port"
        self._snapshot["presence_stage"] = after_hold
        self._snapshot["presence_stage_hold_until"] = 0.0
        self._snapshot["presence_stage_after_hold"] = after_hold
        self._presence_stage_context = {}
        if after_hold != "expedition_result":
            self._snapshot["expedition_result"] = ""
            self._snapshot["presence_details_override"] = None
            self._snapshot["presence_details_override_clear_pending"] = False
            self._snapshot["presence_details_override_hold_until"] = 0.0
            if self._snapshot.get("fleet_status", "").startswith("Expedition Complete:"):
                self._snapshot["fleet_status"] = "In Port"
            self._transient_status_until = 0.0

    def _set_presence_stage(self, stage, hold_seconds=0, after_hold=None, **updates):
        with self._lock:
            self._expire_presence_stage_locked()
            self._snapshot.update(updates)
            self._snapshot["presence_stage"] = stage
            self._snapshot["presence_stage_hold_until"] = (
                time.time() + hold_seconds if hold_seconds > 0 else 0.0
            )
            self._snapshot["presence_stage_after_hold"] = after_hold or stage
            if stage == "expedition_result":
                self._presence_stage_context = dict(updates)
            else:
                self._presence_stage_context = {}

    def _update_snapshot(self, updates):
        with self._lock:
            self._snapshot.update(updates)

    def _set_transient_status(self, text):
        self._update_snapshot({"fleet_status": text})
        self._transient_status_until = time.time() + self.TRANSIENT_STATUS_HOLD_SECONDS

    def _rebuild_fleet1_summary(self):
        if self._fleet1_name is None or self._fleet1_ship_count is None or self._fleet1_total_slots is None:
            self._update_snapshot({"fleet1_summary": ""})
            return
        self._update_snapshot({
            "fleet1_summary": (
                f"Fleet: {self._fleet1_name} —「{self._fleet1_ship_count}/{self._fleet1_total_slots} ships」"
            )
        })

    def _set_details_override(self, text):
        self._update_snapshot({
            "presence_details_override": text,
            "presence_details_override_clear_pending": False,
            "presence_details_override_hold_until": time.time() + self.EXPEDITION_RESULT_HOLD_SECONDS,
        })

    def _request_clear_details_override(self):
        """Request clearing after the monitor has had a chance to render it."""
        self._update_snapshot({
            "presence_details_override_clear_pending": True,
        })

    def acknowledge_details_override(self):
        """Clear the legacy expedition override after its minimum hold time."""
        with self._lock:
            hold_until = float(self._snapshot.get("presence_details_override_hold_until") or 0)
            if self._snapshot.get("presence_details_override_clear_pending") and time.time() >= hold_until:
                self._snapshot["presence_details_override"] = None
                self._snapshot["presence_details_override_clear_pending"] = False
                self._snapshot["presence_details_override_hold_until"] = 0.0
                self._snapshot["fleet1_summary"] = (
                    f"Fleet: {self._fleet1_name} — 「{self._fleet1_ship_count}/{self._fleet1_total_slots} ships」"
                    if self._fleet1_name is not None and self._fleet1_ship_count is not None and self._fleet1_total_slots is not None
                    else ""
                )

    def _identify_fleet(self, ship_ids):
        if not isinstance(ship_ids, list):
            return None
        wanted = {s for s in ship_ids if isinstance(s, int) and s > 0}
        if not wanted:
            return None
        for fid, info in self._known_fleets.items():
            have = {s for s in info.get("ships", []) if isinstance(s, int) and s > 0}
            if have and have == wanted:
                return fid, info.get("name", "")
        return None

    
    def _find_game_target(self):
        url = f"http://127.0.0.1:{self._cdp_port}/json"
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                targets = json.loads(resp.read())
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            return None
        candidates = [t for t in targets if CDP_GAME_TARGET_HINT in t.get("url", "")]
        if not candidates:
            return None
        candidates.sort(key=lambda t: 0 if t.get("type") == "iframe" else 1)
        return candidates[0]

    @staticmethod
    def _parse_kcsapi_body(body_text):
        text = body_text
        if text.startswith("svdata="):
            text = text[len("svdata="):]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _parse_request_field(request_body, field_name):
        if request_body is None:
            return None
        if isinstance(request_body, (bytes, bytearray)):
            request_body = request_body.decode("utf-8", errors="replace")
        if not isinstance(request_body, str):
            return None
        try:
            values = urllib.parse.parse_qs(
                request_body,
                keep_blank_values=True,
            ).get(field_name)
        except (TypeError, ValueError):
            return None
        return values[0] if values else None

    def _handle_kcsapi(self, url, data, request_body=None):
        if not data:
            self._note_problem(url, "response body wasn't valid JSON after all")
            return
        if data.get("api_result") != 1:
            self._note_problem(
                url, f"api_result={data.get('api_result')} ({data.get('api_result_msg')})"
            )
            return
        payload = data.get("api_data")
        endpoint = url.split("/kcsapi/", 1)[-1].split("?", 1)[0]
        if endpoint in (
            "api_port/port",
            "api_get_member/deck_port",
            "api_req_mission/result",
        ):
            payload_keys = sorted(payload.keys()) if isinstance(payload, dict) else None
            request_preview = None
            if request_body is not None:
                request_preview = str(request_body)[:500]
            self._debug(
                f"endpoint=/{endpoint}, "
                f"payload_type={type(payload).__name__}, "
                f"payload_keys={payload_keys}, "
                f"request_body={request_preview!r}"
            )
        try:
            if "/api_get_member/record" in url or "/api_port/port" in url:
                if not isinstance(payload, dict):
                    self._note_problem(
                        url, f"api_data wasn't a dict (got {type(payload).__name__})"
                    )
                    return

                found = self._handle_port_bundle(
                    payload,
                    persist_instance_master_map=("/api_port/port" in url),
                )

                if not found:
                    self._note_problem(
                        url,
                        f"none of api_basic/api_deck_port/api_ship present -- "
                        f"keys were {sorted(payload.keys())}"
                    )

                
                
                
                if "/api_port/port" in url:
                    with self._lock:
                        current_stage = self._snapshot.get("presence_stage") or "in_port"

                    self._clear_quest_context()

                    if current_stage == "expedition_result":
                        with self._lock:
                            expedition_hold_until = float(
                                self._snapshot.get("presence_stage_hold_until") or 0
                            )
                        if expedition_hold_until > time.time():
                            self._debug(
                                "port refresh observed during expedition-result hold; "
                                f"keeping expedition result for {expedition_hold_until - time.time():.1f}s"
                            )
                            return

                    if self._snapshot.get("presence_details_override") is not None:
                        self._request_clear_details_override()

                    self._transient_status_until = 0.0
                    self._set_presence_stage(
                        "in_port",
                        fleet_status="In Port",
                        map_area="",
                        map_info="",
                        location_text="",
                        map_node="",
                        map_node_text="",
                        battle_rank="",
                        battle_rank_only="",
                        expedition_result="",
                    )

                return

            if "/api_get_member/basic" in url:
                self._update_snapshot({
                    "admiral_nickname": payload.get("api_nickname", "?"),
                    "admiral_level": payload.get("api_level", "?"),
                    "admiral_rank": payload.get("api_rank", "?"),
                    "sortie_win": payload.get("api_st_win", "?"),
                    "sortie_lose": payload.get("api_st_lose", "?"),
                    "expedition_success": payload.get("api_ms_success", "?"),
                    "expedition_count": payload.get("api_ms_count", "?"),
                })

            elif "/api_get_member/ship" in url:
                ships = payload if isinstance(payload, list) else payload.get("api_data", [])
                if ships:
                    self._sync_ship_records(ships, persist_instance_master_map=False)
                    self._update_snapshot({"ship_count": len(ships)})


            elif "/api_get_member/deck_port" in url:
                fleets = payload if isinstance(payload, list) else payload.get("api_deck_port", [])
                if fleets:
                    self._known_fleets = {
                        f.get("api_id"): {"name": f.get("api_name", ""), "ships": f.get("api_ship", [])}
                        for f in fleets if isinstance(f, dict) and f.get("api_id") is not None
                    }
                    fleet1_fields = self._fleet1_fields(fleets[0])
                    if time.time() < self._transient_status_until:
                        fleet1_fields.pop("fleet_status", None)
                    self._update_snapshot(fleet1_fields)

            
            elif "/api_req_map/start" in url or "/api_req_map/next" in url:
                map_area = payload.get("api_maparea_id", "?")
                map_info = payload.get("api_mapinfo_no", "?")
                api_no = payload.get("api_no", "?")
                api_id = payload.get("api_id", "?")
                map_node = get_map_node_label(map_area, map_info, api_no, self._log)
                map_node_text = f"Node {map_node}" if map_node else ""
                self._set_presence_stage(
                    "on_sortie",
                    fleet_status=f"On Sortie: World {map_area}-{map_info}",
                    map_area=map_area,
                    map_info=map_info,
                    location_text=f": {map_area}-{map_info}",
                    map_cell_no=api_no,
                    map_cell_id=api_no,
                    api_no=api_no,
                    api_id=api_id,
                    map_node=map_node,
                    map_node_text=map_node_text,
                    battle_rank="",
                    battle_rank_only="",
                    expedition_result="",
                )
                
            elif url.split("/kcsapi/", 1)[-1].split("?", 1)[0] == "api_req_sortie/battleresult":
                rank = payload.get("api_win_rank", "")
                map_area = self._snapshot.get("map_area", "")
                map_info = self._snapshot.get("map_info", "")
                world_text = (
                    f"World {map_area}-{map_info}"
                    if map_area != "" and map_info != ""
                    else ""
                )
                rank_only = f"「 {rank} 」" if rank else ""
                result_text = rank_only
                if world_text:
                    result_text += f": {world_text}"
                self._set_presence_stage(
                    "battle_result",
                    battle_rank=result_text,
                    battle_rank_only=rank_only,
                )
                self._set_transient_status("Battle Result:")

            elif url.split("/kcsapi/", 1)[-1].split("?", 1)[0] == "api_req_sortie/battle":
                map_area = self._snapshot.get("map_area", "")
                map_info = self._snapshot.get("map_info", "")
                world_text = (
                    f"World {map_area}-{map_info}"
                    if map_area != "" and map_info != ""
                    else ""
                )
                status = "Engaging In Battle:"
                if world_text:
                    status += f" {world_text}"
                self._set_presence_stage("in_battle", fleet_status=status)


            elif endpoint.startswith("api_req_battle_midnight/"):
                map_area = self._snapshot.get("map_area", "")
                map_info = self._snapshot.get("map_info", "")
                world_text = (
                    f"World {map_area}-{map_info}"
                    if map_area != "" and map_info != ""
                    else ""
                )
                status = "Engaging In Night Battle:"
                if world_text:
                    status += f" {world_text}"
                self._set_presence_stage("night_battle", fleet_status=status)
            elif url.split("/kcsapi/", 1)[-1].split("?", 1)[0] in (
                "api_req_combined_battle/battle",
                "api_req_combined_battle/airbattle",
                "api_req_combined_battle/battle_water",
                "api_req_combined_battle/ec_battle",
            ):
                map_area = self._snapshot.get("map_area", "")
                map_info = self._snapshot.get("map_info", "")
                world_text = (
                    f"World {map_area}-{map_info}"
                    if map_area != "" and map_info != ""
                    else ""
                )
                status = "Engaging In Battle:"
                if world_text:
                    status += f" {world_text}"
                self._set_presence_stage("in_battle", fleet_status=status)

            elif url.split("/kcsapi/", 1)[-1].split("?", 1)[0] in (
                "api_req_combined_battle/midnight_battle",
                "api_req_combined_battle/sp_midnight",
                "api_req_combined_battle/ec_midnight_battle",
            ):
                map_area = self._snapshot.get("map_area", "")
                map_info = self._snapshot.get("map_info", "")
                world_text = (
                    f"World {map_area}-{map_info}"
                    if map_area != "" and map_info != ""
                    else ""
                )
                status = "Engaging In Night Battle:"
                if world_text:
                    status += f" {world_text}"
                self._set_presence_stage("night_battle", fleet_status=status)

            elif url.split("/kcsapi/", 1)[-1].split("?", 1)[0] == "api_req_combined_battle/battleresult":
                rank = payload.get("api_win_rank", "")
                map_area = self._snapshot.get("map_area", "")
                map_info = self._snapshot.get("map_info", "")
                world_text = (
                    f"World {map_area}-{map_info}"
                    if map_area != "" and map_info != ""
                    else ""
                )
                rank_only = f"「 {rank} 」" if rank else ""
                result_text = rank_only
                if world_text:
                    result_text += f": {world_text}"
                self._set_presence_stage(
                    "battle_result",
                    battle_rank=result_text,
                    battle_rank_only=rank_only,
                )
                self._set_transient_status("Battle Result:")


            elif endpoint == "api_req_mission/result":
                request_deck_id = self._parse_request_field(request_body, "api_deck_id")
                identified = None
                if request_deck_id is not None:
                    try:
                        fid = int(request_deck_id)
                    except (TypeError, ValueError):
                        fid = None
                    if fid in self._known_fleets:
                        identified = (fid, self._known_fleets[fid].get("name", ""))


                if identified is None:
                    identified = self._identify_fleet(payload.get("api_ship_id"))

                self._debug(
                    f"expedition result: api_deck_id={request_deck_id!r}, "
                    f"api_ship_id={payload.get('api_ship_id')!r}, "
                    f"api_clear_result={payload.get('api_clear_result')!r}, "
                    f"known_fleets={self._known_fleets!r}"
                )
                self._debug(f"expedition fleet identification={identified!r}")

                if identified:
                    fid, fname = identified
                    fleet_name = fname or str(fid)
                else:
                    fleet_name = "?"

                result_labels = {
                    0: "Failure",
                    1: "Success",
                    2: "Great Success",
                }
                try:
                    clear_result = int(payload.get("api_clear_result"))
                except (TypeError, ValueError):
                    clear_result = None
                expedition_result = result_labels.get(clear_result, "Unknown")


                returning_ship_count = 0
                if identified:
                    try:
                        returning_ship_count = len(
                            [
                                ship_id
                                for ship_id in (self._known_fleets.get(identified[0], {}).get("ships", []) or [])
                                if ship_id and ship_id != -1
                            ]
                        )
                    except (AttributeError, TypeError):
                        returning_ship_count = 0
                elif isinstance(payload.get("api_ship_id"), list):
                    returning_ship_count = len(
                        [
                            ship_id
                            for ship_id in payload.get("api_ship_id", [])
                            if ship_id and ship_id != -1
                        ]
                    )

                expedition_status = EXPEDITION_DETAILS_TEMPLATE.format(
                    fleet_name=fleet_name,
                    fleet_ship_count=returning_ship_count,
                )

                self._set_presence_stage(
                    "expedition_result",
                    hold_seconds=self.EXPEDITION_RESULT_HOLD_SECONDS,
                    after_hold="in_port",
                    fleet_status=expedition_status,
                    expedition_result=expedition_result,
                    fleet_name=fleet_name,
                    fleet_ship_count=returning_ship_count,
                )
                self._set_transient_status(expedition_status)
                self._set_details_override(expedition_status)

            # Exercises (PVP practice battles) use their own Dynamic Stages.
            elif "/api_get_member/practice" in url:
                self._transient_status_until = 0.0
                self._set_presence_stage(
                    "exercise_opponent",
                    fleet_status="Exercise: Choosing Opponent",
                    map_area="",
                    map_info="",
                    location_text="",
                    map_node="",
                    map_node_text="",
                    battle_rank="",
                    battle_rank_only="",
                    expedition_result="",
                )

            elif endpoint == "api_req_practice/battle":
                self._set_presence_stage(
                    "exercise_battle",
                    fleet_status="Engaging In Exercise",
                )

            elif endpoint == "api_req_practice/midnight_battle":
                self._set_presence_stage(
                    "exercise_night_battle",
                    fleet_status="Engaging In Exercise Night Battle",
                )

            elif endpoint == "api_req_practice/battle_result":
                # Practice result uses the same api_win_rank field as the
                # sortie result path when available.
                rank = payload.get("api_win_rank", "")
                rank_only = f"「 {rank} 」" if rank else ""
                self._set_presence_stage(
                    "exercise_result",
                    battle_rank=rank_only,
                    battle_rank_only=rank_only,
                )
                self._set_transient_status("Exercise Result:")

            elif endpoint == "api_get_member/questlist":
                quest_data = payload if isinstance(payload, dict) else {}
                quest_list = quest_data.get("api_list") if isinstance(quest_data.get("api_list"), list) else []
                self._known_quests = {
                    q.get("api_no"): q
                    for q in quest_list
                    if isinstance(q, dict) and q.get("api_no") is not None
                }

                try:
                    quest_tab_id = int(self._parse_request_field(request_body, "api_tab_id"))
                except (TypeError, ValueError):
                    quest_tab_id = "?"

                active_count = sum(
                    1 for q in quest_list
                    if q.get("api_state") == 2
                )
                self._set_presence_stage(
                    "quest",
                    fleet_status="Quest Menu",
                    quest_count=quest_data.get("api_count", len(quest_list)),
                    quest_active_count=active_count,
                    quest_tab_id=quest_tab_id,
                )

            elif endpoint in ("api_req_quest/start", "api_req_quest/stop", "api_req_quest/clearitemget"):
                quest_id = self._parse_request_field(request_body, "api_quest_id")
                try:
                    quest_id_value = int(quest_id)
                except (TypeError, ValueError):
                    quest_id_value = quest_id or ""

                quest = self._known_quests.get(quest_id_value)
                if quest is None and quest_id is not None:
                    quest = self._known_quests.get(str(quest_id))

                if endpoint.endswith("/start"):
                    event = "Started"
                elif endpoint.endswith("/stop"):
                    event = "Cancelled"
                else:
                    event = "Completed"


                progress_value = ""
                if isinstance(quest, dict):
                    progress_value = quest.get("api_progress_flag", "")
                if event == "Completed":
                    progress_value = 100

                updates = {
                    "quest_id": quest_id_value,
                    "quest_event": event,

                    "quest_title": self._translate_quest_title(
                        quest.get("api_title", "") if isinstance(quest, dict) else "",
                        quest_id_value,
                    ),
                    "quest_progress": progress_value,
                }
                if isinstance(quest, dict):
                    updates.update({
                        "quest_category": quest.get("api_category", ""),
                        "quest_type": quest.get("api_type", ""),
                        "quest_state": quest.get("api_state", ""),
                    })

                if endpoint.endswith("/clearitemget"):
                    rewards = payload if isinstance(payload, dict) else {}
                    materials = rewards.get("api_material")
                    if isinstance(materials, list):
                        padded = list(materials[:4]) + [0] * max(0, 4 - len(materials))
                        updates.update({
                            "quest_reward_fuel": padded[0],
                            "quest_reward_ammo": padded[1],
                            "quest_reward_steel": padded[2],
                            "quest_reward_bauxite": padded[3],
                        })

                    bonuses = rewards.get("api_bounus")
                    if isinstance(bonuses, list):
                        summaries = []
                        for bonus in bonuses:
                            if not isinstance(bonus, dict):
                                continue
                            count = bonus.get("api_count", "")
                            item = bonus.get("api_item") or {}
                            item_id = item.get("api_id", "") if isinstance(item, dict) else ""
                            item_name = item.get("api_name", "") if isinstance(item, dict) else ""
                            bonus_type = bonus.get("api_type", "")

                            label = item_name or (f"Item {item_id}" if item_id != "" else "")
                            if label and count != "":
                                label = f"{count}x {label}"
                            elif label:
                                label = str(label)
                            elif count != "":
                                label = f"{count}x"

                            if bonus_type not in ("", None) and label:
                                label = f"Type {bonus_type}: {label}"
                            elif bonus_type not in ("", None):
                                label = f"Type {bonus_type}"

                            if label:
                                summaries.append(str(label))

                        updates["quest_bonus_count"] = rewards.get("api_bounus_count", len(bonuses))
                        updates["quest_bonus_summary"] = " | ".join(summaries)

                self._set_presence_stage(
                    "quest",
                    fleet_status=f"Quest: {event}",
                    **updates,
                )

            elif endpoint == "api_get_member/ndock":
                self._clear_quest_context()
                docks = payload if isinstance(payload, list) else []
                active_docks = [
                    d for d in docks
                    if isinstance(d, dict) and d.get("api_state") == 1
                ]
                self._update_snapshot({
                    "repair_dock_count": len(docks),
                    "repair_active_count": len(active_docks),
                })

                selected = self._select_repair_record(docks)
                self._update_repair_snapshot_from_record(selected)


                self._set_presence_stage(
                    "repair_dock",
                    fleet_status="Repair Dock",
                )

            elif endpoint == "api_req_nyukyo/start":
                dock_id = self._parse_request_field(request_body, "api_ndock_id")
                ship_id = self._parse_request_field(request_body, "api_ship_id")
                highspeed = self._parse_request_field(request_body, "api_highspeed")
                if dock_id not in (None, ""):
                    self._repair_selected_dock_id = str(dock_id)
                self._associate_repair_ship(dock_id or "", ship_id or "")
                record = self._repair_docks.get(str(dock_id)) if dock_id not in (None, "") else None
                if record:
                    record["state"] = 1
                    self._update_repair_snapshot_from_record(record)
                else:
                    self._update_snapshot({
                        "repair_dock_id": dock_id or "",
                        "repair_ship_id": ship_id or "",
                        "repair_state": "1",
                    })
                repair_event = "Highspeed repair" if highspeed == "1" else "Started"
                self._set_presence_stage(
                    "repair_dock",
                    fleet_status="Repair Dock",
                    repair_event=repair_event,
                )

            elif "/api_get_member/material" in url:
                materials = payload if isinstance(payload, list) else []
                self._update_snapshot(self._resource_fields(materials))
            

            elif self._log is not None:
                self._note_seen_endpoint(url)

            elif self._log is not None:
                
                
                
                self._note_seen_endpoint(url)
        except (KeyError, TypeError, AttributeError) as e:
            
            
            
            
            self._note_problem(url, f"unexpected data shape ({e})")

    def _handle_port_bundle(self, d, persist_instance_master_map=False):
        found_any = False
        basic = d.get("api_basic") or {}
        if basic:
            self._update_snapshot({
                "admiral_nickname": basic.get("api_nickname", "?"),
                "admiral_level": basic.get("api_level", "?"),
                "admiral_rank": basic.get("api_rank", "?"),
                "sortie_win": basic.get("api_st_win", "?"),
                "sortie_lose": basic.get("api_st_lose", "?"),
                "expedition_success": basic.get("api_ms_success", "?"),
                "expedition_count": basic.get("api_ms_count", "?"),
            })
            found_any = True

        
        materials = d.get("api_material")
        if isinstance(materials, list):
            self._update_snapshot(self._resource_fields(materials))
            found_any = True
        

        ships = d.get("api_ship")
        if isinstance(ships, list) and ships:
            # /api_port/port is the primary mapping source. Persist only new
            # instance -> master pairs found in this authoritative bundle.
            self._sync_ship_records(
                ships,
                persist_instance_master_map=persist_instance_master_map,
            )
            self._update_snapshot({"ship_count": len(ships)})
            found_any = True
        fleets = d.get("api_deck_port")
        if isinstance(fleets, list) and fleets:
            self._known_fleets = {
                f.get("api_id"): {"name": f.get("api_name", ""), "ships": f.get("api_ship", [])}
                for f in fleets if isinstance(f, dict) and f.get("api_id") is not None
            }
            fleet1_fields = self._fleet1_fields(fleets[0])
            if time.time() < self._transient_status_until:
                fleet1_fields.pop("fleet_status", None)
            self._update_snapshot(fleet1_fields)
            found_any = True
        return found_any

    def _fleet1_fields(self, fleet):
        mission = fleet.get("api_mission") or [0, 0, 0, 0]
        if mission[0]:
            
            
            
            
            
            status = "away on expedition" if (mission[3] / 1000) > time.time() else "returning"
        else:
            status = "In port"
        ship_ids = [s for s in fleet.get("api_ship", []) if s and s != -1]
        self._fleet1_name = fleet.get("api_name", "?")
        self._fleet1_ship_count = len(ship_ids)
        self._fleet1_total_slots = len(fleet.get("api_ship", []) or [])
        if self._snapshot.get("presence_details_override") is None:
            self._rebuild_fleet1_summary()
            self._log(repr(self._snapshot.get("fleet1_summary")))
        fields = {
            "fleet_name": self._fleet1_name,
            "fleet_status": status,
            "fleet_ship_count": self._fleet1_ship_count,
        }
        fields.update(self._fleet1_computed_fields(ship_ids))
        return fields

    def _note_seen_endpoint(self, url):
        key = url.split("/kcsapi/", 1)[-1].split("?", 1)[0]
        if key in self._seen_endpoints:
            return
        self._seen_endpoints.add(key)
        self._log(f"KanColle traffic seen (not used for presence yet): /kcsapi/{key}")

    def _note_problem(self, url, message):
        """Log a parsing/fetch problem for a given endpoint, but only the
        first time THAT exact problem shows up for THAT endpoint -- so a
        repeating failure (e.g. every ~30s from a periodic call) doesn't
        flood the log, while a genuinely new problem still gets surfaced."""
        key = (url.split("/kcsapi/", 1)[-1].split("?", 1)[0], message)
        if key in self._seen_problems:
            return
        self._seen_problems.add(key)
        self._log(f"KanColle: /kcsapi/{key[0]} -- {message}")

    
    
    
    
    
    
    
    
    
    _CAPTURE_SCRIPT = """
    (function() {
        var HOOK_VERSION = 2;
        if (window.__kcsapiHookVersion !== HOOK_VERSION) {
            window.__kcsapiHookVersion = HOOK_VERSION;
            window.__kcsapiHookInstalled = false;
        }
        if (!window.__kcsapiHookInstalled) {
            window.__kcsapiHookInstalled = true;
            window.__kcsapiQueue = window.__kcsapiQueue || [];
            var push = function(url, body) {
                try {
                    if (url && url.indexOf('/kcsapi/') !== -1) {
                        window.__kcsapiQueue.push({u: url, b: body});
                    }
                } catch (e) {}
            };
            var origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url) {
                this.__kcsapiUrl = url;
                return origOpen.apply(this, arguments);
            };
            var origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function(body) {
                var xhr = this;
                var url = this.__kcsapiUrl;
                this.__kcsapiRequestBody = body;
                this.addEventListener('load', function() {
                    try {
                        if (url && url.indexOf('/kcsapi/') !== -1) {
                            window.__kcsapiQueue.push({
                                u: url,
                                b: xhr.responseText,
                                r: xhr.__kcsapiRequestBody
                            });
                        }
                    } catch (e) {}
                });
                return origSend.apply(this, arguments);
            };
            if (window.fetch) {
                var origFetch = window.fetch;
                window.fetch = function(input, init) {
                    var url = (typeof input === 'string') ? input : (input && input.url);
                    var requestBody = init && init.body;
                    var p = origFetch.apply(this, arguments);
                    if (url && url.indexOf('/kcsapi/') !== -1) {
                        p.then(function(resp) {
                            resp.clone().text().then(function(text) {
                                try {
                                    window.__kcsapiQueue.push({
                                        u: url,
                                        b: text,
                                        r: requestBody
                                    });
                                } catch (e) {}
                            }).catch(function() {});
                        }).catch(function() {});
                    }
                    return p;
                };
            }
        }
        var q = window.__kcsapiQueue || [];
        window.__kcsapiQueue = [];
        var banners = [];
        try {
            if (performance && performance.setResourceTimingBufferSize) {
                performance.setResourceTimingBufferSize(5000);
            }
            window.__kcsBannerSeen = window.__kcsBannerSeen || {};
            var entries = performance.getEntriesByType('resource') || [];
            for (var i = 0; i < entries.length; i++) {
                var entry = entries[i];
                var name = entry && entry.name ? String(entry.name) : '';
                if (name.indexOf('/kcs2/resources/ship/banner/') === -1 &&
                    name.indexOf('/kcs2/resources/ship/banner_dmg/') === -1) continue;
                var key = name + '|' + String(entry.startTime);
                if (window.__kcsBannerSeen[key]) continue;
                window.__kcsBannerSeen[key] = true;
                banners.push({u: name, t: entry.startTime});
            }
        } catch (e) {}
        return JSON.stringify({api: q, banners: banners});
    })();
    """

    def run(self):
        while not self._stop_event.is_set():
            target = self._find_game_target()
            if target is None:
                self._stop_event.wait(3)
                continue
            try:
                ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10)
            except Exception as e:
                if not self._warned_once:
                    self._log(
                        f"KanColle live-data attach failed: {e}. Make sure "
                        f"damecon-browser.exe was launched with "
                        f"--remote-debugging-port={self._cdp_port} --remote-allow-origins=*."
                    )
                    self._warned_once = True
                self._stop_event.wait(5)
                continue

            self._log("KanColle live-data watcher attached.")
            self._warned_once = False
            next_id = 1

            def send_and_wait(method, params, timeout=5):
                nonlocal next_id
                msg_id = next_id
                next_id += 1
                ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        ws.settimeout(max(0.1, deadline - time.time()))
                        reply = json.loads(ws.recv())
                    except websocket.WebSocketTimeoutException:
                        break
                    if reply.get("id") == msg_id:
                        return reply
                    
                    
                    
                return None

            warned_eval_failure = False
            try:
                while not self._stop_event.is_set():
                    reply = send_and_wait(
                        "Runtime.evaluate",
                        {"expression": self._CAPTURE_SCRIPT, "returnByValue": True},
                        timeout=5,
                    )
                    if reply is None:
                        raise RuntimeError("Runtime.evaluate timed out (page busy or navigated?)")
                    result = reply.get("result", {})
                    if "exceptionDetails" in result:
                        if not warned_eval_failure:
                            self._log(f"KanColle: injected script threw an error: {result['exceptionDetails']}")
                            warned_eval_failure = True
                    else:
                        raw = (result.get("result") or {}).get("value")
                        if raw:
                            try:
                                items = json.loads(raw)
                            except json.JSONDecodeError:
                                items = []
                            if isinstance(items, dict):
                                api_items = items.get("api", [])
                                banner_items = items.get("banners", [])
                            else:
                                api_items = items
                                banner_items = []

                            for banner in banner_items:
                                if not isinstance(banner, dict):
                                    continue
                                key = (banner.get("u", ""), banner.get("t"))
                                if key in self._seen_ship_banner_entries:
                                    continue
                                self._seen_ship_banner_entries.add(key)
                                self._record_ship_banner(banner.get("u", ""), banner.get("t"))

                            for item in api_items:
                                url = item.get("u", "")
                                request_body = item.get("r")
                                data = self._parse_kcsapi_body(item.get("b", ""))
                                if data is None:
                                    self._note_problem(url, "couldn't parse JSON captured from page")
                                    continue
                                self._handle_kcsapi(url, data, request_body=request_body)
                    self._stop_event.wait(2.0)
            except Exception as e:
                if not self._stop_event.is_set():
                    self._log(f"KanColle live-data watcher disconnected ({e}); will retry.")
            finally:
                try:
                    ws.close()
                except Exception:
                    pass

