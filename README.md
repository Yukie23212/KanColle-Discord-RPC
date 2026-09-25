# Discord RPC Manager

## Features

### Discord Rich Presence

- Publishes a configurable **Discord Rich Presence** when a monitored process is running.
- Supports custom **Discord Name**, **Details**, and **State** text.
- Supports **Client ID** selection per Variant, allowing different Discord Applications to be used for different profiles.
- Supports **Large Image** and **Small Image** values, optional hover text, and optional image URLs.
- Supports up to **two clickable Discord buttons**, with configurable labels and URLs.
- Supports the Discord **party size** display with either a fixed count or a dynamic count from live KanColle data.
- Supports an optional **elapsed-time timer**. The timer is tied to the monitored process session, so changing presence content or reconnecting to Discord does not reset it.

### Groups and Variants

- A **Group** represents one monitored process and can contain multiple **Variants**.
- Multiple Variants under the same process are useful for rotating different Rich Presence layouts for each process session.
- When a process starts, one enabled Variant is selected randomly and remains active for that process session.
- Each Variant has an independent **Random Weight**, allowing weighted selection instead of equal probability.
- Copy, enable/disable, edit, and delete operations are available for both Groups and Variants.
- A Group always keeps at least one Variant through the UI.

### Template System

The Template System lets you build reusable text from live placeholders instead of repeatedly writing the same formatting in every Variant.

- Supports live placeholders directly inside **Discord Name, Details, State, and Widget V2 values**.
- Built-in live values can be combined into normal format strings such as:

```text
KanColle — {admiral_nickname} (Lv.{admiral_level})
Fleet: {fleet_name} ({fleet_ship_count}/6 ships)
Resource: {fuel} | {ammo} | {steel} | {bauxite}
```

- Supports **Custom Templates** that become reusable placeholders of your own.
- A Custom Template can contain both built-in placeholders and other Custom Templates, so templates can be chained together and composed into larger formats.

For example, create this Custom Template:

```text
Placeholder: test_fleet_info
Template: {fleet_name} | {fleet_ship_count}/6 | {fleet_status}
```

Using `{test_fleet_info}` in another field renders the current live values, for example:

```text
1st Fleet | 6/6 | In Port
```

You can then create another Custom Template that uses the first one:

```text
Placeholder: fleet_display
Template: [Main] {test_fleet_info} | Level {admiral_level}
```

Now `{fleet_display}` becomes something like:

```text
[Main] 1st Fleet | 6/6 | In Port | Level 120
```

This allows you to build small reusable pieces first and combine them into larger templates later. A single custom placeholder can therefore act as a building block for many different Rich Presence layouts.

- Custom Templates can be added, edited, renamed, deleted, and reused anywhere the template system accepts placeholders.
- Built-in live-data fields take precedence over Custom Template names with the same name, so a custom template cannot replace a real live-data field.
- Recursive or cyclic references are protected and safely stop expanding instead of causing an infinite loop.

#### Why a placeholder can show `?` or `Unknown`

Seeing `?` is normal while the watcher is waiting for a known live field to receive usable data. The watcher learns the live state from KanColle API requests observed through CDP, and different placeholders are populated by different requests.

The two values now have a clear distinction:

- `?` is used for a **known live-data field** whose value is not available yet. For example, fleet, quest, repair, resource, map, battle, and admiral fields that are known to the watcher can show `?` until the API response that supplies them has been observed.
- `Unknown` means the template renderer **could not resolve the placeholder as a known live field or a Custom Template**, or a Custom Template reference was blocked by the recursion/depth protection. It is not the normal value for a supported live field that simply has not been seen yet.

For example, before the corresponding API requests have been observed you may see:

```text
{fleet_hp_pct}      -> ?
{admiral_level}     -> ?
{fleet_name}        -> ?
{quest_title}       -> (empty until quest data is available)
```

After the game makes the corresponding API requests and the watcher captures them, the same placeholders can change to their real values:

```text
{fleet_hp_pct}      -> 100
{admiral_level}     -> 120
{fleet_name}        -> 1
{quest_title}       -> [translated quest title]
```

Entering the correct CDP port only gives the watcher access to the game's traffic; the specific API request that supplies a field still has to be observed before that value can be updated.

For example, `{repair_event}` is a known live field. It is empty when there is no current repair event, becomes `Started` (or `Highspeed repair`) when a repair-start request is observed, and becomes `Repairing` when an already-active repair is reconstructed from a later `ndock` response after a monitor/tab restart.

A genuinely unsupported or misspelled placeholder, such as `{fleett_name}`, resolves to `Unknown` because it is not a known live field and is not a defined Custom Template.


### Dynamic Stage Templates

Variants can define stage-specific **Details** and **State** templates. A stage override takes precedence over the Variant's normal text, while global stage defaults can be shared across all CDP Variants.

The watcher exposes these stages:

- **In Port**
- **On Sortie**
- **In Battle**
- **Night Battle**
- **Battle Result**
- **Quest**
- **Repair / Dock**
- **Exercise — Choosing Opponent**
- **Exercise Battle**
- **Exercise Night Battle**
- **Exercise Result**
- **Expedition Result**

Temporary result stages are held for a short period so a normal background refresh does not immediately overwrite the event that just happened.

### KanColle Live Data via Chrome DevTools Protocol

When **Watch live game data** is enabled for a Group, the application can inspect KanColle's browser-side API traffic through a configured **Chrome DevTools Protocol (CDP) port** instead of using fixed text.

The watcher can capture and expose:

#### Admiral data

- `{admiral_nickname}`
- `{admiral_level}`
- `{admiral_rank}`

#### Fleet and ship data

- `{fleet_name}`
- `{fleet_status}`
- `{fleet_ship_count}`
- `{ship_count}`
- `{fleet_hp_pct}`
- `{fleet_damaged_count}`
- `{fleet_ready_count}`
- `{fleet_avg_level}`
- `{fleet1_summary}`

#### Map and sortie data

- `{map_area}`
- `{map_info}`
- `{location_text}`
- `{map_node}`
- `{map_node_text}`
- `{map_display}`
- `{api_no}`
- `{map_cell_no}`
- `{map_cell_id}`
- `{api_id}`

Map node labels are resolved from the bundled/community map-edge data, with a local cache and periodic source refresh.

#### Battle data

- `{battle_rank}`
- `{battle_rank_only}`

The watcher detects normal daytime battles, normal night battles, combined-fleet battle phases, combined-fleet night battles, and their result stages.

#### Exercise / PvP data

- Opponent-selection stage
- Daytime practice battle stage
- Practice night-battle stage
- Practice battle result stage

#### Expedition data

- Detects expedition/mission return results.
- Identifies the returning fleet when possible using the requested fleet ID or known fleet composition.
- Exposes `{expedition_result}` with values such as `Failure`, `Success`, or `Great Success`.
- Uses the returning fleet's name and ship count for the temporary Expedition Result display.

#### Quest data

The watcher can track the quest list and quest lifecycle:

- `{quest_count}`
- `{quest_active_count}`
- `{quest_tab_id}`
- `{quest_id}`
- `{quest_title}`
- `{quest_progress}`
- `{quest_progress_text}`
- `{quest_event}`
- `{quest_reward_fuel}`
- `{quest_reward_ammo}`
- `{quest_reward_steel}`
- `{quest_reward_bauxite}`
- `{quest_bonus_count}`
- `{quest_bonus_summary}`

Quest start, cancellation, and completion events are detected. Quest titles can be resolved from the bundled/updated translation data by quest ID, and completion is treated as 100% for the presence layer.

#### Repair dock data

- `{repair_dock_count}`
- `{repair_active_count}`
- `{repair_dock_id}`
- `{repair_ship_id}`
- `{repair_ship_master_id}`
- `{repair_ship_name}`
- `{repair_state}`
- `{repair_complete_time}`
- `{repair_complete_time_str}`
- `{repair_remaining}`
- `{repair_event}`
- `{repair_item1}` through `{repair_item4}`

`{repair_event}` reports the lifecycle event observed by the watcher: `Started` or `Highspeed repair` when a repair-start request is captured, and `Repairing` when an already-active repair is reconstructed from live `ndock` data after a restart or tab refresh. Ship instance IDs can be resolved to master IDs and ship names using the live ship records and persistent local caches.

Entering the Repair Dock switches the presence stage to **Repair Dock**, while a real Port transition switches it back to **In Port**. Active repair data can continue to be tracked while the player is in Port without forcing the presence stage back to Repair Dock.

#### Resource data

- `{fuel}`
- `{ammo}`
- `{steel}`
- `{bauxite}`
- `{flamethrower}`
- `{bucket}`
- `{dev_material}`
- `{screw}`
- `{resource_total}`

Fuel, ammo, steel, and bauxite are automatically formatted for compact display (for example, `12k`).

### Persistent Live-Data Caches

The KanColle watcher maintains local runtime data for items that are expensive or impractical to resolve on every request, including:

- Ship master names
- Ship instance → master ID/name mappings
- Quest translations
- Quest ID translations
- Map edge/node data
- Upstream source metadata used for update checks

Existing valid cached data is used immediately. External JSON sources can be refreshed periodically with conditional requests, while bundled copies provide offline recovery when available.

### Discord Widget V2 Profile Field Sync

The project also contains an optional **Discord Widget V2 profile-field synchronisation** feature that is separate from Rich Presence IPC.

This feature has an important prerequisite: **it is only usable with a Discord application user/profile that has already been created and set up for Widget V2.** The RPC Manager does not create that application user/profile for you. If there is no existing Widget V2 application user to target, the sync will not work.

In practice, the Widget V2 section is an optional integration for an already-prepared Discord application user. Creating the user/profile, obtaining the required identifiers/credentials, and configuring the target profile field must be done outside the RPC Manager first. The RPC Manager only performs the update against that existing target.

Once a valid application user/profile already exists, the feature can:

- Send a bot-authenticated profile-field update through Discord's application-user profile endpoint.
- Use the same live snapshot/placeholder system as Rich Presence.
- Use the configurable target field name; the default is `HQ_level`.
- Use a configurable value template; the default is `{admiral_level}`.
- Combine live values with fixed text, for example `{admiral_level} [Taisho]`.
- Update only when the rendered value changes, avoiding unnecessary requests for an unchanged value.
- Retry a failed update only after a cooldown instead of repeatedly sending the same failed request.
- Detect missing CDP data or incomplete App ID/User ID/Bot Token credentials and log the problem without stopping the monitor.

Unlike Rich Presence, Widget V2 sync writes to the **Discord application-user profile field** itself. It is therefore a separate feature with separate credentials and requirements; enabling Rich Presence does not automatically create or enable Widget V2.

## License

Copyright © 2026 harunoyukie.

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0)**.

See the [LICENSE](LICENSE) file for full details.
Third-party components, libraries, and/or assets may be subject to their own licenses.
See [THIRD PARTY LICENSES](THIRD_PARTY_LICENSES.txt) for the applicable third-party licenses and attributions.

## Credits & Acknowledgments

- **Author & Maintainer:** harunoyukie (System Design, Architecture & Technical Direction)
- **Development:** Built with assistance from AI coding agents
