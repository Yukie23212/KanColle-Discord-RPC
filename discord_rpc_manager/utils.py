# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

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


class _SafeFormatDict(dict):
    """Used with str.format_map() so a template referencing a field we
    haven't seen data for yet (e.g. right after the process starts, before
    the first kcsapi response arrives) renders as '?' instead of raising
    KeyError and losing the whole presence update."""
    def __missing__(self, key):
        return "?"

def safe_format(template, snapshot):
    """Fill a Details/State template against a live-data snapshot. Falls
    back to the raw template on any formatting error (e.g. a stray '{' in
    text that was never meant as a placeholder) rather than crashing."""
    if not template:
        return template
    try:
        return template.format_map(_SafeFormatDict(snapshot or {}))
    except Exception:
        return template

