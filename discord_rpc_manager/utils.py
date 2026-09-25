# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import random


def choose_variant(group):
    """Randomly pick one enabled variant from a group, weighted by its
    'weight' field (default 1 = equal chance). Falls back to any variant
    if none are marked enabled."""
    candidates = [v for v in group.get("variants", []) if v.get("enabled", True)]
    if not candidates:
        candidates = group.get("variants", [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    weights = [max(1, int(v.get("weight", 1))) for v in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


_KNOWN_LIVE_FIELDS = {
    "admiral_nickname",
    "admiral_level",
    "admiral_rank",
    "sortie_win",
    "sortie_lose",
    "expedition_success",
    "expedition_count",
    "expedition_result",
    "quest_count",
    "quest_active_count",
    "quest_tab_id",
    "quest_id",
    "quest_title",
    "quest_category",
    "quest_type",
    "quest_state",
    "quest_progress",
    "quest_event",
    "quest_reward_fuel",
    "quest_reward_ammo",
    "quest_reward_steel",
    "quest_reward_bauxite",
    "quest_bonus_count",
    "quest_bonus_summary",
    "repair_dock_count",
    "repair_active_count",
    "repair_dock_id",
    "repair_ship_id",
    "repair_ship_master_id",
    "repair_ship_name",
    "repair_state",
    "repair_complete_time",
    "repair_complete_time_str",
    "repair_item1",
    "repair_item2",
    "repair_item3",
    "repair_item4",
    "repair_event",
    "fleet_hp_pct",
    "fleet_damaged_count",
    "fleet_ready_count",
    "fleet_avg_level",
    "flamethrower",
    "bucket",
    "dev_material",
    "screw",
    "resource_total",
    "fleet_total_slots",
    "api_id",
    "map_area",
    "map_info",
    "location_text",
    "map_cell_no",
    "map_cell_id",
    "api_no",
    "map_node",
    "map_node_text",
    "battle_rank",
    "battle_rank_only",
    "fleet1_summary",
    "fleet_name",
    "fleet_status",
    "fleet_ship_count",
    "ship_count",
    "fuel",
    "ammo",
    "steel",
    "bauxite",
    "presence_stage",
    "presence_stage_hold_until",
    "presence_stage_after_hold",
    "presence_details_override",
    "presence_details_override_clear_pending",
    "presence_details_override_hold_until",
    "repair_remaining",
    "stage",
    "map_display",
    "quest_progress_text",
}


class _SafeFormatDict(dict):
    """Mapping used by the template renderer.

    Built-in live-data fields come from the snapshot first. If a field is not
    present there, a user-defined custom template with the same name may be
    expanded. Anything still unknown becomes ``Unknown``.
    """

    def __init__(self, snapshot=None, custom_templates=None, resolving=None, depth=0):
        super().__init__(snapshot or {})
        self._custom_templates = custom_templates or {}
        self._resolving = set(resolving or ())
        self._depth = depth

    def __missing__(self, key):
        if key in self._custom_templates:
            if key in self._resolving or self._depth >= 32:
                return "Unknown"
            template = self._custom_templates.get(key)
            next_resolving = set(self._resolving)
            next_resolving.add(key)
            return _render_template(
                template,
                self,
                self._custom_templates,
                next_resolving,
                self._depth + 1,
            )
        if key in _KNOWN_LIVE_FIELDS:
            return "?"
        return "Unknown"


def _render_template(template, snapshot, custom_templates, resolving=None, depth=0):
    if not template:
        return template
    try:
        mapping = _SafeFormatDict(
            snapshot=snapshot,
            custom_templates=custom_templates,
            resolving=resolving,
            depth=depth,
        )
        return str(template).format_map(mapping)
    except Exception:
        return template


def safe_format(template, snapshot, custom_templates=None):
    return _render_template(template, snapshot or {}, custom_templates or {})
