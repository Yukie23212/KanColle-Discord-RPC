# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

"""
Discord "Widget V2" profile field sync.

This is unrelated to Rich Presence (pypresence/IPC) -- it's a plain HTTPS
PATCH to Discord's bot-authenticated "application user profile" endpoint,
which is what lets a bot show custom fields (Spotify/Xbox-style) on a
user's Discord profile. Unlike Rich Presence, a value pushed here persists
on the profile without needing the game/app to stay open, but (per Haru's
own testing) Discord doesn't reflect an update to an already-open client
until it's restarted -- so this is meant for values that change rarely
(e.g. HQ level), not anything that needs to feel live.
"""

import json
import urllib.request
import urllib.error

PROFILE_API_URL = (
    "https://discord.com/api/v9/applications/{app_id}/users/{user_id}/identities/0/profile"
)


def push_dynamic_field(app_id, user_id, bot_token, field_name, value, field_type=1):
    url = PROFILE_API_URL.format(app_id=app_id, user_id=user_id)
    body = json.dumps({
        "data": {
            "dynamic": [
                {"type": field_type, "name": field_name, "value": str(value)}
            ]
        }
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bot {bot_token}",
            "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 1.0.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True, None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        return False, f"HTTP {e.code} {e.reason}" + (f" -- {detail[:250]}" if detail else "")
    except urllib.error.URLError as e:
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)
