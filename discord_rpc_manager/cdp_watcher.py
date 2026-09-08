# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import json
import threading
import time
import urllib.request
import urllib.error

from .constants import CDP_GAME_TARGET_HINT


MAP_EDGE_URL = (
    "https://raw.githubusercontent.com/kcwiki/kancolle-data/"
    "master/map/edge.json"
)
MAP_EDGE_CACHE_NAME = "kancolle_map_edges.json"
MAP_EDGE_REFRESH_SECONDS = 24 * 60 * 60


_MAP_EDGES = None
_MAP_EDGES_LOADED_AT = 0.0
_MAP_EDGES_LOCK = threading.Lock()


def _map_edge_cache_path():
    
    
    import os
    import sys

    base_dir = (
        os.path.dirname(sys.executable)
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    return os.path.join(base_dir, MAP_EDGE_CACHE_NAME)


def _load_map_edges():
    global _MAP_EDGES, _MAP_EDGES_LOADED_AT

    now = time.time()
    with _MAP_EDGES_LOCK:
        if _MAP_EDGES is not None and (now - _MAP_EDGES_LOADED_AT) < MAP_EDGE_REFRESH_SECONDS:
            return _MAP_EDGES

        cache_path = _map_edge_cache_path()
        data = None

        
        
        try:
            req = urllib.request.Request(
                MAP_EDGE_URL,
                headers={"User-Agent": "DiscordRPCManager/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read()
            candidate = json.loads(raw.decode("utf-8"))
            if isinstance(candidate, dict):
                data = candidate
                try:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                except OSError:
                    pass
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass

        if data is None:
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    candidate = json.load(f)
                if isinstance(candidate, dict):
                    data = candidate
            except (OSError, json.JSONDecodeError):
                data = {}

        _MAP_EDGES = data or {}
        _MAP_EDGES_LOADED_AT = now
        return _MAP_EDGES


def get_map_node_label(map_area, map_info, api_no):
    try:
        map_key = f"{int(map_area)}{int(map_info)}"
        cell_key = str(int(api_no))
    except (TypeError, ValueError):
        return ""

    edges = _load_map_edges()
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
        }
        self._warned_once = False
        self._seen_endpoints = set()
        self._seen_problems = set()

    @staticmethod
    def _format_k(val):
        try:
            num = int(val)
            return f"{round(num / 1000)}k" if num >= 1000 else str(num)
        except (ValueError, TypeError):
            return str(val)

    def stop(self):
        self._stop_event.set()

    def get_snapshot(self):
        with self._lock:
            return dict(self._snapshot)

    def _update_snapshot(self, updates):
        with self._lock:
            self._snapshot.update(updates)

    
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

    def _handle_kcsapi(self, url, data):
        if not data:
            self._note_problem(url, "response body wasn't valid JSON after all")
            return
        if data.get("api_result") != 1:
            self._note_problem(
                url, f"api_result={data.get('api_result')} ({data.get('api_result_msg')})"
            )
            return
        payload = data.get("api_data")
        try:
            if "/api_get_member/record" in url or "/api_port/port" in url:
                if not isinstance(payload, dict):
                    self._note_problem(
                        url, f"api_data wasn't a dict (got {type(payload).__name__})"
                    )
                    return

                found = self._handle_port_bundle(payload)

                if not found:
                    self._note_problem(
                        url,
                        f"none of api_basic/api_deck_port/api_ship present -- "
                        f"keys were {sorted(payload.keys())}"
                    )

                
                
                
                if "/api_port/port" in url:
                    self._update_snapshot({
                        "fleet_status": "In Port",
                        "map_area": "",
                        "map_info": "",
                        "location_text": "",
                        "map_node": "",
                        "map_node_text": "",
                        "battle_rank": "",
                    })

                return

            if "/api_get_member/basic" in url:
                self._update_snapshot({
                    "admiral_nickname": payload.get("api_nickname", "?"),
                    "admiral_level": payload.get("api_level", "?"),
                    "admiral_rank": payload.get("api_rank", "?"),
                })

            elif "/api_get_member/ship" in url:  
                ships = payload if isinstance(payload, list) else payload.get("api_data", [])
                if ships:
                    self._update_snapshot({"ship_count": len(ships)})

            elif "/api_get_member/deck_port" in url:
                fleets = payload if isinstance(payload, list) else payload.get("api_deck_port", [])
                if fleets:
                    self._update_snapshot(self._fleet1_fields(fleets[0]))

            
            elif "/api_req_map/start" in url or "/api_req_map/next" in url:
                map_area = payload.get("api_maparea_id", "?")
                map_info = payload.get("api_mapinfo_no", "?")
                api_no = payload.get("api_no", "?")
                api_id = payload.get("api_id", "?")
                map_node = get_map_node_label(map_area, map_info, api_no)
                map_node_text = f"Node {map_node}" if map_node else ""
                self._update_snapshot({
                    "fleet_status": f"On Sortie: World {map_area}-{map_info}",
                    "map_area": map_area,
                    "map_info": map_info,
                    "location_text": f": {map_area}-{map_info}",
                    "map_cell_no": api_no,
                    "map_cell_id": api_id,
                    "api_no": api_no,
                    "api_id": api_id,
                    "map_node": map_node,
                    "map_node_text": map_node_text,
                    "battle_rank": "",
                })
                
            elif url.split("/kcsapi/", 1)[-1].split("?", 1)[0] == "api_req_sortie/battleresult":
                rank = payload.get("api_win_rank", "")
                map_area = self._snapshot.get("map_area", "")
                map_info = self._snapshot.get("map_info", "")
                world_text = (
                    f"World {map_area}-{map_info}"
                    if map_area != "" and map_info != ""
                    else ""
                )
                result_text = f"「 {rank} 」" if rank else ""
                if world_text:
                    result_text += f": {world_text}"
                self._update_snapshot({
                    "fleet_status": "Battle Result:",
                    "battle_rank": result_text,
                })

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
                self._update_snapshot({"fleet_status": status})

            
            
            
            
            elif "/api_port/port" in url:
                self._update_snapshot({
                    "fleet_status": "In Port",
                    "map_area": "",
                    "map_info": "",
                    "location_text": "",
                    "battle_rank": ""
                })
                
            elif "/api_get_member/material" in url:
                materials = payload if isinstance(payload, list) else []
                mat_dict = {m.get("api_id"): m.get("api_value") for m in materials if isinstance(m, dict)}
                self._update_snapshot({
                    "fuel": self._format_k(mat_dict.get(1, "?")),
                    "ammo": self._format_k(mat_dict.get(2, "?")),
                    "steel": self._format_k(mat_dict.get(3, "?")),
                    "bauxite": self._format_k(mat_dict.get(4, "?")),
                })
            

            elif self._log is not None:
                self._note_seen_endpoint(url)

            elif self._log is not None:
                
                
                
                self._note_seen_endpoint(url)
        except (KeyError, TypeError, AttributeError) as e:
            
            
            
            
            self._note_problem(url, f"unexpected data shape ({e})")

    def _handle_port_bundle(self, d):
        found_any = False
        basic = d.get("api_basic") or {}
        if basic:
            self._update_snapshot({
                "admiral_nickname": basic.get("api_nickname", "?"),
                "admiral_level": basic.get("api_level", "?"),
                "admiral_rank": basic.get("api_rank", "?"),
            })
            found_any = True

        
        materials = d.get("api_material")
        if isinstance(materials, list):
            mat_dict = {m.get("api_id"): m.get("api_value") for m in materials if isinstance(m, dict)}
            self._update_snapshot({
                "fuel": self._format_k(mat_dict.get(1, "?")),
                "ammo": self._format_k(mat_dict.get(2, "?")),
                "steel": self._format_k(mat_dict.get(3, "?")),
                "bauxite": self._format_k(mat_dict.get(4, "?")),
            })
            found_any = True
        

        ships = d.get("api_ship")
        if isinstance(ships, list) and ships:
            self._update_snapshot({"ship_count": len(ships)})
            found_any = True
        fleets = d.get("api_deck_port")
        if isinstance(fleets, list) and fleets:
            self._update_snapshot(self._fleet1_fields(fleets[0]))
            found_any = True
        return found_any

    @staticmethod
    def _fleet1_fields(fleet):
        
        
        
        mission = fleet.get("api_mission") or [0, 0, 0, 0]
        if mission[0]:
            
            
            
            
            
            status = "away on expedition" if (mission[3] / 1000) > time.time() else "returning"
        else:
            status = "In port"
        ship_ids = [s for s in fleet.get("api_ship", []) if s and s != -1]
        return {
            "fleet_name": fleet.get("api_name", "?"),
            "fleet_status": status,
            "fleet_ship_count": len(ship_ids),
        }

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
        if (!window.__kcsapiHookInstalled) {
            window.__kcsapiHookInstalled = true;
            window.__kcsapiQueue = [];
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
                this.addEventListener('load', function() {
                    push(url, xhr.responseText);
                });
                return origSend.apply(this, arguments);
            };
            if (window.fetch) {
                var origFetch = window.fetch;
                window.fetch = function(input, init) {
                    var url = (typeof input === 'string') ? input : (input && input.url);
                    var p = origFetch.apply(this, arguments);
                    if (url && url.indexOf('/kcsapi/') !== -1) {
                        p.then(function(resp) {
                            resp.clone().text().then(function(text) {
                                push(url, text);
                            }).catch(function() {});
                        }).catch(function() {});
                    }
                    return p;
                };
            }
        }
        var q = window.__kcsapiQueue || [];
        window.__kcsapiQueue = [];
        return JSON.stringify(q);
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
                            for item in items:
                                url = item.get("u", "")
                                data = self._parse_kcsapi_body(item.get("b", ""))
                                if data is None:
                                    self._note_problem(url, "couldn't parse JSON captured from page")
                                    continue
                                self._handle_kcsapi(url, data)
                    self._stop_event.wait(2.0)
            except Exception as e:
                if not self._stop_event.is_set():
                    self._log(f"KanColle live-data watcher disconnected ({e}); will retry.")
            finally:
                try:
                    ws.close()
                except Exception:
                    pass

