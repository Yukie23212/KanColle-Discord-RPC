// Copyright (c) 2026 harunoyukie
// Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

const UI_STATE_KEY = 'rpc-ui-state';
const ACTIVITY_CLEAR_KEY = 'rpc-activity-cleared-through';
const savedUIState = (() => {
  try { return JSON.parse(localStorage.getItem(UI_STATE_KEY) || '{}'); } catch (_) { return {}; }
})();

function persistUIState() {
  try {
    localStorage.setItem(UI_STATE_KEY, JSON.stringify({
      currentPage: state.currentPage,
      selectedTemplate: state.selectedTemplate,
      templateDirty: state.templateDirty,
      templateNew: state.templateNew,
      templateDraftName: state.templateDraftName,
      templateDraftBody: state.templateDraftBody,
    }));
  } catch (_) {}
}

function readActivityClearMarker() {
  try { return localStorage.getItem(ACTIVITY_CLEAR_KEY) || ''; } catch (_) { return ''; }
}

function applyActivityClearMarker(logs) {
  const marker = readActivityClearMarker();
  if (!marker || !Array.isArray(logs)) return logs;
  const markerIndex = logs.lastIndexOf(marker);
  return markerIndex >= 0 ? logs.slice(markerIndex + 1) : logs;
}

const state = {
  data: null,
  selectedTemplate: savedUIState.selectedTemplate || null,
  templateDirty: !!savedUIState.templateDirty,
  templateNew: !!savedUIState.templateNew,
  templateDraftName: savedUIState.templateDraftName || '',
  templateDraftBody: savedUIState.templateDraftBody || '',
  editingGroupIndex: null,
  currentPage: savedUIState.currentPage || 'dashboard',
  quitting: false,
};

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? '').replace(/[&<>\"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;' }[c]));

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(message, type = 'info') {
  const el = $('toast');
  el.textContent = message;
  el.className = `toast show ${type}`;
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => el.classList.remove('show'), 2400);
}

function showPage(name) {
  state.currentPage = name;
  persistUIState();
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.page === name));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === `page-${name}`));
  const titles = {
    dashboard: ['OVERVIEW', 'Dashboard'],
    groups: ['CONFIGURATION', 'Groups & Variants'],
    templates: ['TEMPLATES', 'Custom Templates'],
    settings: ['PREFERENCES', 'Settings'],
    activity: ['RUNTIME', 'Activity Log'],
    help: ['REFERENCE', 'Help'],
  };
  $('pageEyebrow').textContent = titles[name][0];
  $('pageTitle').textContent = titles[name][1];
}

document.querySelectorAll('.nav-item').forEach(b => b.addEventListener('click', () => showPage(b.dataset.page)));

function statusClass(monitoring) {
  return monitoring ? 'status-live' : 'status-idle';
}

function renderDashboard() {
  const d = state.data;
  const cfg = d.config;
  const enabledGroups = cfg.groups.filter(g => g.enabled).length;
  const enabledVariants = cfg.groups.reduce((n, g) => n + (g.variants || []).filter(v => v.enabled !== false).length, 0);

  $('groupCount').textContent = cfg.groups.length;
  $('enabledGroupCount').textContent = enabledGroups;
  $('templateCount').textContent = Object.keys(cfg.custom_templates || {}).length;
  $('variantCount').textContent = enabledVariants;
  $('monitorStatus').textContent = d.status || (d.monitoring ? 'Monitoring' : 'Idle');
  $('monitorDetail').textContent = d.active_process
    ? `Active process: ${d.active_process}`
    : (d.monitoring ? 'Waiting for a matching process…' : 'Monitoring is not running.');
  $('monitorToggle').textContent = d.monitoring ? 'Stop Monitoring' : 'Start Monitoring';
  $('monitorToggle').classList.toggle('danger', d.monitoring);
  $('monitorPulse').className = `live-pulse ${statusClass(d.monitoring)}`;
  $('monitorBadge').textContent = d.monitoring ? 'LIVE' : 'IDLE';
  $('monitorBadge').className = `status-badge ${statusClass(d.monitoring)}`;
  $('lastUpdated').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const presence = d.active_variant;
  const rendered = d.rendered_presence;
  const imageValue = rendered?.large_image || presence?.large_image || '';
  const imageIsUrl = /^https?:\/\//i.test(imageValue);
  const imageHtml = imageIsUrl
    ? `<img class="presence-render-image" src="${esc(imageValue)}" alt="Rich Presence large image" onerror="this.style.display='none';this.nextElementSibling.classList.add('show')">`
    : '';
  const fallbackClass = imageIsUrl ? 'presence-render-fallback' : 'presence-render-fallback show';
  const renderedButtons = rendered?.buttons?.length
    ? `<div class="discord-render-buttons">${rendered.buttons.map(b => `<span>${esc(b.label)}</span>`).join('')}</div>`
    : '';
  const renderedParty = rendered?.party_max > 0
    ? `<span class="discord-render-party">${esc(rendered.party_current)} / ${esc(rendered.party_max)}</span>`
    : '';
  $('presenceCard').innerHTML = presence ? `
    <div class="configured-presence">
      <div class="presence-section-label">CONFIGURED RPC</div>
      <div class="presence">
        <div class="presence-art"><div class="presence-art-inner">RPC</div></div>
        <div class="presence-main">
          <div class="presence-title">${esc(presence.app_name || 'Untitled Presence')}</div>
          <div class="presence-subtitle">${esc(presence.name || 'Discord Rich Presence')}</div>
          <div class="presence-detail-line"><span>Details</span><strong>${esc(presence.details || '')}</strong></div>
          <div class="presence-detail-line"><span>State</span><strong>${esc(presence.state || '')}</strong></div>
        </div>
        <div class="presence-side"><span>CLIENT ID</span><strong>${esc(presence.client_id || 'Not set')}</strong></div>
      </div>
    </div>
    <div class="discord-rendered-section">
      <div class="presence-section-label">DISCORD PREVIEW <span>${rendered?.source === 'live' ? 'LIVE DATA' : 'CONFIGURATION'}</span></div>
      <div class="discord-render-card">
        <div class="discord-render-media">
          ${imageHtml}
          <div class="${fallbackClass}">RPC</div>
          ${rendered?.small_image && /^https?:\/\//i.test(rendered.small_image) ? `<img class="discord-render-small" src="${esc(rendered.small_image)}" alt="Small image">` : ''}
        </div>
        <div class="discord-render-main">
          <div class="discord-render-app">${esc(rendered?.name || presence.name || presence.app_name || 'Discord Rich Presence')}</div>
          <div class="discord-render-title">${esc(rendered?.app_name || presence.app_name || 'Untitled Presence')} ${renderedParty}</div>
          <div class="discord-render-line">${esc(rendered?.details || '')}</div>
          <div class="discord-render-line muted">${esc(rendered?.state || '')}</div>
          ${renderedButtons}
          <div class="discord-render-note">Rendered from the active RPC configuration${rendered?.source === 'live' ? ' using the current CDP snapshot' : ''}.</div>
        </div>
      </div>
    </div>` : `
    <div class="empty-visual"><div class="empty-icon">◌</div><div><strong>No active presence</strong><span>Start monitoring to see the active Discord profile here.</span></div></div>`;

  $('snapshotPreview').textContent = d.snapshot ? JSON.stringify(d.snapshot, null, 2) : 'No live snapshot.';
  $('snapshotState').textContent = d.snapshot ? 'Live' : 'Waiting';
  $('snapshotState').className = `mini-state ${d.snapshot ? 'live' : ''}`;
  $('copySnapshotBtn').disabled = !d.snapshot;
  $('connectionDot').className = 'connection-dot ok';
  $('connectionText').textContent = 'Python backend connected';
}

function renderGroups() {
  const groups = state.data.config.groups;
  $('groupsList').innerHTML = groups.map((g, gi) => `
    <section class="group-card ${g.enabled ? 'group-enabled' : 'group-disabled'}">
      <div class="group-head">
        <div class="group-heading">
          <div class="group-title-row"><span class="group-dot ${g.enabled ? 'on' : ''}"></span><div class="group-title">${esc(g.process_name || '(unnamed)')}</div></div>
          <div class="meta">${g.cdp_watch ? 'Live CDP enabled' : 'Static mode'} <span>·</span> Port ${esc(g.cdp_port)}</div>
        </div>
        <div class="group-actions"><button class="ghost" onclick="editGroup(${gi})">Edit</button><button class="ghost" onclick="copyGroup(${gi})">Copy</button><button class="ghost" onclick="toggleGroup(${gi})">${g.enabled ? 'Disable' : 'Enable'}</button><button class="ghost" onclick="addVariant(${gi})">＋ Variant</button><button class="ghost danger-ghost" onclick="deleteGroup(${gi})">Delete</button></div>
      </div>
      <div class="variant-list">
        ${(g.variants || []).map((v, vi) => `<div class="variant-row ${v.enabled === false ? 'variant-disabled' : ''}">
          <div class="variant-primary"><div class="variant-name">${esc(v.app_name || 'Variant')}</div><div class="variant-meta">${esc(v.client_id || 'No Client ID')}</div></div>
          <span class="pill ${v.enabled !== false ? 'on' : ''}">${v.enabled !== false ? 'Enabled' : 'Off'}</span>
          <span class="pill">Weight ${esc(v.weight || 1)}</span>
          <div class="variant-copy"><div>${esc(v.details || 'No Details')}</div><div class="variant-meta">${esc(v.state || 'No State')}</div></div>
          <div class="group-actions"><button class="ghost" onclick="editVariant(${gi},${vi})">Edit</button><button class="ghost" onclick="copyVariant(${gi},${vi})">Copy</button><button class="ghost" onclick="toggleVariant(${gi},${vi})">${v.enabled !== false ? 'Disable' : 'Enable'}</button><button class="ghost danger-ghost" onclick="deleteVariant(${gi},${vi})">Delete</button></div>
        </div>`).join('') || '<div class="empty-list">No variants configured yet. Use ＋ Variant to add one.</div>'}
      </div>
    </section>`).join('') || '<section class="card empty-state-card"><div class="empty-icon">＋</div><strong>No groups configured</strong><span>Create a group to start building a Rich Presence profile.</span></section>';
}

const BUILTIN_PLACEHOLDERS = [
  'admiral_nickname', 'admiral_level', 'admiral_rank', 'sortie_win', 'sortie_lose', 'expedition_success', 'expedition_count',
  'fleet_name', 'fleet_status', 'fleet_ship_count', 'ship_count', 'fleet1_summary',
  'map_area', 'map_info', 'location_text', 'map_node', 'map_node_text',
  'api_no', 'map_cell_no', 'map_cell_id',
  'battle_rank', 'expedition_result', 'battle_rank_only',
  'quest_count', 'quest_active_count', 'quest_tab_id', 'quest_id', 'quest_title',
  'quest_category', 'quest_type', 'quest_state', 'quest_progress', 'quest_event','quest_progress_text',
  'quest_reward_fuel', 'quest_reward_ammo', 'quest_reward_steel', 'quest_reward_bauxite',
  'quest_bonus_count', 'quest_bonus_summary',
  'repair_dock_count', 'repair_active_count', 'repair_dock_id', 'repair_ship_id',
  'repair_state', 'repair_complete_time', 'repair_complete_time_str',
  'repair_item1', 'repair_item2', 'repair_item3', 'repair_item4',
  'repair_ship_master_id', 'repair_ship_name', 'repair_event', 'repair_remaining',
  'fuel', 'ammo', 'steel', 'bauxite', 'resource_total', 'flamethrower', 'bucket', 'dev_material', 'screw',
  'fleet_hp_pct', 'fleet_damaged_count', 'fleet_ready_count', 'fleet_avg_level',
  'map_display', 'stage', 'presence_stage', 'api_id', 'presence_stage_hold_until', 'presence_stage_after_hold'
];

function renderPlaceholderHints() {
  const custom = state.data.config.custom_templates || {};
  const keys = [...new Set([...BUILTIN_PLACEHOLDERS, ...Object.keys(custom)])].sort();
  $('placeholderHints').innerHTML = keys.map(name => `<button class="placeholder-chip" type="button" data-placeholder="${esc(name)}" title="Insert {${esc(name)}}">{${esc(name)}}</button>`).join('');
}

function renderBuiltinPlaceholderReference() {
  const groups = [
    {
      title: 'Admiral',
      rows: [
        ['admiral_nickname', 'Admiral nickname from the live game data.', 'Yourname'],
        ['admiral_level', 'Admiral level from the live game data.', '120'],
        ['admiral_rank', 'Admiral rank value reported by the game.', '1'],
      ]
    },
    {
      title: 'KanColle Statistics',
      rows: [
        ['sortie_win', 'Sortie victory count from api_basic.api_st_win.', '2232'],
        ['sortie_lose', 'Sortie loss count from api_basic.api_st_lose.', '98'],
        ['expedition_success', 'Successful expedition/mission count from api_basic.api_ms_success.', '899'],
        ['expedition_count', 'Total expedition/mission count from api_basic.api_ms_count.', '994'],
      ]
    },
    {
      title: 'Fleet & Ships',
      rows: [
        ['fleet_name', 'Fleet #1 name.', '1st Fleet'],
        ['fleet_status', 'Current high-level status, including port, sortie, battle, exercise, or event-result states.', 'On Sortie: World 1-5'],
        ['fleet_ship_count', 'Ships currently assigned to Fleet #1.', '4'],
        ['fleet_hp_pct', 'Combined current HP of known Fleet #1 ships as a percentage of their combined maximum HP.', '83%'],
        ['fleet_damaged_count', 'Known Fleet #1 ships whose current HP is below maximum HP.', '2'],
        ['fleet_ready_count', 'Known Fleet #1 ships currently at maximum HP.', '2'],
        ['fleet_avg_level', 'Average level of known Fleet #1 ships, rounded to the nearest whole level.', '42'],
        ['ship_count', 'Total ships currently reported in the ship list.', '120'],
        ['fleet1_summary', 'Ready-made Fleet #1 summary built by the watcher.', 'Fleet: 1st Fleet — 「4/6 ships」'],
      ]
    },
    {
      title: 'Map & Node',
      rows: [
        ['map_area', 'World/area number.', '1'],
        ['map_info', 'Map number within that world.', '5'],
        ['location_text', 'Ready-made combined location text in the form `: {map_area}-{map_info}`.', ': 1-5'],
        ['map_node', 'Player-facing node label resolved from the community map data.', 'J'],
        ['map_node_text', 'The resolved node label with `Node` added.', 'Node J'],
        ['map_display', 'Combined world/map display with the node when available.', 'World 1-5 Node J'],
      ]
    },
    {
      title: 'Raw Map-Cell Values',
      rows: [
        ['api_no', 'Raw current map-cell number reported by the game.', '12'],
        ['map_cell_no', 'Alias of the current raw map-cell number.', '12'],
        ['map_cell_id', 'Alias of the current raw map-cell number (`api_no`). KanColle map start/next identifies the current cell with `api_no`.', '12'],
      ]
    },
    {
      title: 'Quests',
      rows: [
        ['quest_count', 'Number of quests returned by the latest quest-list response.', '103'],
        ['quest_active_count', 'Number of quest entries currently reported with api_state 2 in the latest quest-list response.', '5'],
        ['quest_tab_id', 'Quest-list tab/filter ID supplied when the quest list was requested.', '0'],
        ['quest_id', 'Quest ID from the most recent quest start/cancel/finish request.', '503'],
        ['quest_title', 'Translated title of the most recent started/cancelled/finished quest when a KCCP translation exists; otherwise the original title.', 'Mass Fleet Servicing!'],
        // ['quest_category', 'Raw api_category value of the most recent selected quest.', '2'],
        // ['quest_type', 'Raw api_type value of the most recent selected quest.', '1'],
        // ['quest_state', 'Raw api_state value of the most recent selected quest.', '2'],
        ['quest_progress', 'Raw api_progress_flag: 0 = no progress/blank (including completed), 1 = 50% or more, 2 = 80% or more.', '1'],
        ['quest_progress_text', 'Human-readable quest progress derived from api_progress_flag.', '50%'],
        ['quest_event', 'Watcher event generated by the most recent quest start/cancel/finish request.', 'Completed'],
        ['quest_reward_fuel', 'Fuel awarded by the most recent quest finish response.', '40'],
        ['quest_reward_ammo', 'Ammo awarded by the most recent quest finish response.', '40'],
        ['quest_reward_steel', 'Steel awarded by the most recent quest finish response.', '40'],
        ['quest_reward_bauxite', 'Bauxite awarded by the most recent quest finish response.', '40'],
        ['quest_bonus_count', 'Number of bonus reward entries in the most recent quest finish response.', '2'],
        ['quest_bonus_summary', 'Compact summary of bonus rewards from the most recent quest finish response.', 'Type 1: 1x Item 7 | Type 1: 1x Item 5'],
      ]
    },
    {
      title: 'Repair / Docks',
      rows: [
        ['repair_dock_count', 'Number of repair docks returned by the latest ndock response.', '4'],
        ['repair_active_count', 'Number of docks currently reporting api_state 1.', '1'],
        ['repair_dock_id', 'Dock ID of the first currently active repair, or the dock from the latest repair-start request.', '1'],
        // ['repair_ship_id', 'Owned ship instance ID assigned to the active repair, or the ship from the latest repair-start request.', '1412'],
        // ['repair_ship_master_id', 'Master ship ID resolved from the ship banner/banner_dmg resource.', '898'],
        ['repair_ship_name', 'Ship master name resolved from the master ship data.', 'Kaiboukan No.22'],
        ['repair_event', 'Last repair event generated by the watcher.', 'Started'],
        ['repair_state', 'Raw repair dock state. The captured active-repair response uses 1.', '1'],
        // ['repair_complete_time', 'Raw repair completion timestamp from the active dock.', '1790134205597'],
        // ['repair_complete_time_str', 'Formatted repair completion time reported by the game.', '2026-09-23 12:30:05'],
        // ['repair_item1', 'Raw repair-dock item1 value for the active dock.', '19'],
        // ['repair_item2', 'Raw repair-dock item2 value for the active dock.', '0'],
        // ['repair_item3', 'Raw repair-dock item3 value for the active dock.', '35'],
        // ['repair_item4', 'Raw repair-dock item4 value for the active dock.', '0'],
        ['repair_remaining', 'Approximate time remaining until the active repair completion timestamp.', '12m 34s'],
      ]
    },
    {
      title: 'Battle & Results',
      rows: [
        ['battle_rank', 'Battle result rank text. It is empty until a battle result is received, then may include the current world.', '「 S 」: World 1-5'],
        ['battle_rank_only', 'Battle result rank only, without world information.', '「 S 」'],
        ['expedition_result', 'Expedition result text set when an expedition returns.', 'Great Success'],
      ]
    },
    {
      title: 'Resources',
      rows: [
        ['fuel', 'Current fuel amount, formatted with `k` for thousands.', '12k'],
        ['ammo', 'Current ammo amount, formatted with `k` for thousands.', '12k'],
        ['steel', 'Current steel amount, formatted with `k` for thousands.', '12k'],
        ['bauxite', 'Current bauxite amount, formatted with `k` for thousands.', '12k'],
        ['flamethrower', 'Current instant-repair consumable (material ID 5).', '42'],
        ['bucket', 'Current instant-repair bucket count (material ID 6).', '37'],
        ['dev_material', 'Current Development Material count (material ID 7).', '58'],
        ['screw', 'Current Improvement Material / screw count (material ID 8).', '26'],
        ['resource_total', 'Combined raw amount of fuel, ammo, steel, and bauxite.', '48250'],
      ]
    },
    {
      title: 'Presence',
      rows: [
        ['presence_stage', 'Internal presence stage name used by the watcher.', 'in_port'],
        ['stage', 'Human-readable current presence stage derived from the internal stage name.', 'In Battle'],
      ]
    },
    {
      title: 'Debugging & Testing',
      rows: [
        ['repair_item1', 'Raw repair-dock item1 value for the active dock.', '19'],
        ['repair_item2', 'Raw repair-dock item2 value for the active dock.', '0'],
        ['repair_item3', 'Raw repair-dock item3 value for the active dock.', '35'],
        ['repair_item4', 'Raw repair-dock item4 value for the active dock.', '0'],
        ['api_id', 'Raw numeric map-cell/node number reported directly by KanColle. Primarily useful for debugging', 'Unknown value for now. but it is a part of the raw api data.'],
        ['presence_stage_hold_until', 'Timestamp indicating when the current presence stage hold expires. Used internally to keep temporary result stages visible for a defined period.', '0,  1790313687.392135'],
        ['presence_stage_after_hold', "The presence stage to transition to after the current stage's hold period expires. Used internally for temporary result or transition stages.", 'in_port'],
        ['quest_category', 'Raw api_category value of the most recent selected quest.', '2'],
        ['quest_type', 'Raw api_type value of the most recent selected quest.', '1'],
        ['quest_state', 'Raw api_state value of the most recent selected quest.', '2'],
        ['repair_complete_time', 'Raw repair completion timestamp from the active dock.', '1790134205597'],
        ['repair_complete_time_str', 'Formatted repair completion time reported by the game.', '2026-09-23 12:30:05'],
        ['repair_ship_id', 'Owned ship instance ID assigned to the active repair, or the ship from the latest repair-start request.', '1412'],
        ['repair_ship_master_id', 'Master ship ID resolved from the ship banner/banner_dmg resource.', '898'],
      ]
    }
  ];

  $('builtinPlaceholderReference').innerHTML = groups.map(group => `
    <div class="placeholder-reference-group">
      <div class="placeholder-reference-title">${esc(group.title)}</div>
      <div class="placeholder-reference-table">
        <div class="placeholder-reference-row placeholder-reference-header"><span>Placeholder</span><span>What it contains</span><span>Example</span></div>
        ${group.rows.map(([name, description, example]) => `
          <div class="placeholder-reference-row">
            <button class="placeholder-reference-name" type="button" title="Insert {${esc(name)}}" onclick="insertPlaceholder(${JSON.stringify(name)})">{${esc(name)}}</button>
            <span>${esc(description)}</span>
            <code>${esc(example)}</code>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
}

function renderTemplates() {
  const t = state.data.config.custom_templates || {};
  const names = Object.keys(t);
  if (state.selectedTemplate && !names.includes(state.selectedTemplate)) {
    state.selectedTemplate = null;
    state.templateNew = true;
  }
  if (!state.selectedTemplate && !state.templateNew && names.length) state.selectedTemplate = names[0];

  $('templateList').innerHTML = names.length
    ? names.map(n => `<button type="button" class="template-item ${state.selectedTemplate === n ? 'active' : ''}" data-template-name="${esc(n)}">
        <span class="template-item-top"><strong>{${esc(n)}}</strong><span class="template-chevron">›</span></span>
        <span>${esc(t[n])}</span>
      </button>`).join('')
    : '<div class="empty-list">No custom templates yet.<br><small>Create one to build reusable sentences.</small></div>';

  // The page polls the backend every 1.5s. Never overwrite an editor that is
  // currently being created/edited. This keeps a draft intact while the
  // backend state refreshes in the background.
  if (state.templateDirty || state.templateNew) {
    $('previewSource').textContent = state.templateNew ? 'New template' : 'Editing';
    renderGlobalStageTemplates();
    renderPlaceholderHints();
    return;
  }

  if (state.selectedTemplate) {
    $('templateName').value = state.selectedTemplate;
    $('templateBody').value = t[state.selectedTemplate] || '';
    state.templateDraftName = $('templateName').value;
    state.templateDraftBody = $('templateBody').value;
    previewTemplate(false);
  } else {
    $('templateName').value = '';
    $('templateBody').value = '';
    $('templatePreview').textContent = 'Select or create a template.';
    $('previewSource').textContent = 'Waiting for a template';
  }
  renderGlobalStageTemplates();
  renderPlaceholderHints();
}

function renderGlobalStageTemplates() {
  const editor = $('globalStageTemplateEditor');
  if (!editor) return;
  const source = state.data.config.stage_template_defaults || {};
  editor.innerHTML = STAGE_TEMPLATE_META.map(([key, label, help]) => {
    const t = source[key] && typeof source[key] === 'object' ? source[key] : {};
    const enabled = !!t.enabled;
    return `<div class="stage-template-card global-stage-template-card">
      <div class="stage-template-head">
        <div><strong>${esc(label)}</strong><span>${esc(help)}</span></div>
        <label class="stage-mode"><span>Mode</span><select id="globalStageMode_${key}">
          <option value="normal" ${enabled ? '' : 'selected'}>Use normal template</option>
          <option value="override" ${enabled ? 'selected' : ''}>Override this stage globally</option>
        </select></label>
      </div>
      <div class="stage-template-grid">
        <div class="field"><label for="globalStageDetails_${key}">Details</label><textarea id="globalStageDetails_${key}" rows="2" placeholder="Optional stage-specific Details"></textarea><small>Supports built-in and custom placeholders.</small></div>
        <div class="field"><label for="globalStageState_${key}">State</label><textarea id="globalStageState_${key}" rows="2" placeholder="Optional stage-specific State"></textarea><small>Leave blank to hide State during this stage.</small></div>
      </div>
    </div>`;
  }).join('');

  for (const [key] of STAGE_TEMPLATE_META) {
    const t = source[key] && typeof source[key] === 'object' ? source[key] : {};
    $('globalStageDetails_'+key).value = t.details || '';
    $('globalStageState_'+key).value = t.state || '';
    const update = () => {
      const custom = $('globalStageMode_'+key).value === 'override';
      $('globalStageDetails_'+key).disabled = !custom;
      $('globalStageState_'+key).disabled = !custom;
      $('globalStageDetails_'+key).closest('.field').classList.toggle('stage-field-disabled', !custom);
      $('globalStageState_'+key).closest('.field').classList.toggle('stage-field-disabled', !custom);
    };
    $('globalStageMode_'+key).addEventListener('change', update);
    update();
  }
}

function readGlobalStageTemplates() {
  const out = {};
  for (const [key] of STAGE_TEMPLATE_META) {
    out[key] = {
      enabled: $('globalStageMode_'+key).value === 'override',
      details: $('globalStageDetails_'+key).value,
      state: $('globalStageState_'+key).value,
    };
  }
  return out;
}

window.selectTemplate = (name) => {
  if (state.templateDirty && !confirm('Discard unsaved template changes?')) return;
  state.selectedTemplate = name;
  state.templateNew = false;
  state.templateDirty = false;
  state.templateDraftName = name;
  state.templateDraftBody = state.data.config.custom_templates?.[name] || '';
  persistUIState();
  renderTemplates();
};

$('templateList').addEventListener('click', (event) => {
  const item = event.target.closest('.template-item');
  if (!item) return;
  window.selectTemplate(item.dataset.templateName);
});

window.insertPlaceholder = (name) => {
  const field = $('templateBody');
  const token = `{${name}}`;
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? field.value.length;
  field.value = `${field.value.slice(0, start)}${token}${field.value.slice(end)}`;
  field.focus();
  field.selectionStart = field.selectionEnd = start + token.length;
  state.templateDirty = true;
  clearTimeout(window._previewTimer);
  window._previewTimer = setTimeout(() => previewTemplate(false), 100);
};

$('placeholderHints').addEventListener('click', (event) => {
  const chip = event.target.closest('.placeholder-chip');
  if (!chip) return;
  window.insertPlaceholder(chip.dataset.placeholder || '');
});

async function previewTemplate(showToast = true) {
  try {
    const out = await api('/api/preview', { method: 'POST', body: JSON.stringify({ template: $('templateBody').value }) });
    $('templatePreview').textContent = out.rendered;
    $('previewSource').textContent = out.source === 'live' ? 'Live preview · current CDP snapshot' : 'Example preview · no live snapshot';
    if (showToast) toast('Preview updated', 'success');
  } catch (e) {
    $('templatePreview').textContent = e.message;
    $('previewSource').textContent = 'Preview unavailable';
    if (showToast) toast(e.message, 'error');
  }
}

function renderSettings() {
  const c = state.data.config;
  $('intervalInput').value = c.check_interval_seconds;
  $('idleInput').value = c.idle_auto_stop_minutes;
  $('autoStartInput').checked = !!c.auto_start_monitoring;
  $('startWindowsInput').checked = !!c.start_with_windows;
  $('minTrayInput').checked = !!c.start_minimized_to_tray;
  $('lightThemeInput').checked = !!c.light_theme;
  $('configPath').textContent = state.data.active_config_path || 'Default config';
}

function renderActivity() {
  const log = (state.data.logs || []).join('\n');
  const el = $('activityLog');
  const renderedLog = log || 'No activity yet.';
  if (el.textContent === renderedLog) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  el.textContent = renderedLog;
  if (nearBottom) el.scrollTop = el.scrollHeight;
}

function render() {
  renderDashboard();
  renderGroups();
  renderTemplates();
  renderBuiltinPlaceholderReference();
  renderSettings();
  renderActivity();
}

async function load() {
  if (state.quitting) return;
  try {
    state.data = await api('/api/state');
    if (typeof state.data.config.light_theme === 'boolean') {
      applyTheme(state.data.config.light_theme);
    }
    state.data.logs = applyActivityClearMarker(state.data.logs || []);
    if (state.templateDirty || state.templateNew) {
      $('templateName').value = state.templateDraftName;
      $('templateBody').value = state.templateDraftBody;
    }
    render();
    showPage(state.currentPage);
  } catch (e) {
    if (state.quitting) return;
    $('connectionDot').className = 'connection-dot bad';
    $('connectionText').textContent = 'Backend unavailable';
    toast(e.message, 'error');
  }
}

$('refreshBtn').onclick = load;
$('copySnapshotBtn').onclick = async () => {
  if (!state.data?.snapshot) {
    toast('No live snapshot to copy.', 'error');
    return;
  }
  const text = JSON.stringify(state.data.snapshot, null, 2);
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const field = document.createElement('textarea');
      field.value = text;
      field.style.position = 'fixed';
      field.style.opacity = '0';
      document.body.appendChild(field);
      field.focus();
      field.select();
      document.execCommand('copy');
      field.remove();
    }
    toast('Live snapshot copied', 'success');
  } catch (e) {
    toast(`Could not copy snapshot: ${e.message}`, 'error');
  }
};
$('openConfigBtn').onclick = async () => {
  try {
    await api('/api/config/open', { method: 'POST', body: '{}' });
    await load();
    toast('Config loaded', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
};
$('monitorToggle').onclick = async () => {
  try { await api('/api/monitor/toggle', { method: 'POST', body: '{}' }); await load(); toast('Monitor state changed', 'success'); }
  catch (e) { toast(e.message, 'error'); }
};
$('quickTemplates').onclick = () => showPage('templates');
$('quickGroups').onclick = () => showPage('groups');
$('quickSettings').onclick = () => showPage('settings');
$('saveBtn').onclick = async () => {
  try { await api('/api/save', { method: 'POST', body: '{}' }); await load(); toast('Configuration saved', 'success'); }
  catch (e) { toast(e.message, 'error'); }
};
$('applyBtn').onclick = async () => {
  try { await api('/api/monitor/apply', { method: 'POST', body: '{}' }); await load(); toast('Changes applied', 'success'); }
  catch (e) { toast(e.message, 'error'); }
};
if ($('previewNow')) $('previewNow').onclick = () => previewTemplate(true);
$('templateBody').addEventListener('input', () => {
  state.templateDirty = true;
  state.templateDraftBody = $('templateBody').value;
  persistUIState();
  clearTimeout(window._previewTimer);
  window._previewTimer = setTimeout(() => previewTemplate(false), 180);
});
$('templateName').addEventListener('input', () => {
  state.templateDirty = true;
  state.templateDraftName = $('templateName').value;
  persistUIState();
});
$('addTemplateBtn').onclick = (event) => {
  event.preventDefault();
  state.selectedTemplate = null;
  state.templateNew = true;
  state.templateDirty = true;
  state.templateDraftName = '';
  state.templateDraftBody = '';
  persistUIState();
  $('templateName').value = '';
  $('templateBody').value = '';
  $('templatePreview').textContent = '';
  $('previewSource').textContent = 'Ready';
  $('templateName').focus();
};
$('saveGlobalStageTemplatesBtn').onclick = async () => {
  try {
    const stage_template_defaults = readGlobalStageTemplates();
    await api('/api/config', { method: 'POST', body: JSON.stringify({ stage_template_defaults }) });
    await load();
    toast('Global stage defaults saved', 'success');
  } catch (e) { toast(e.message, 'error'); }
};

$('saveTemplateBtn').onclick = async () => {
  const name = $('templateName').value.trim();
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
    toast('Use a name like fleet_info or battle_message.', 'error');
    $('templateName').focus();
    return;
  }
  const templates = { ...(state.data.config.custom_templates || {}) };
  if (state.selectedTemplate && state.selectedTemplate !== name) delete templates[state.selectedTemplate];
  templates[name] = $('templateBody').value;
  try {
    await api('/api/config', { method: 'POST', body: JSON.stringify({ custom_templates: templates }) });
    state.data.config.custom_templates = templates;
    state.selectedTemplate = name;
    state.templateNew = false;
    state.templateDirty = false;
    state.templateDraftName = name;
    state.templateDraftBody = templates[name];
    persistUIState();
    await load();
    showPage('templates');
    toast('Template saved', 'success');
  } catch (e) { toast(e.message, 'error'); }
};
$('deleteTemplateBtn').onclick = async () => {
  const name = state.selectedTemplate;
  if (!name) return;
  if (!confirm(`Delete {${name}}?`)) return;
  const templates = { ...(state.data.config.custom_templates || {}) };
  delete templates[name];
  try {
    await api('/api/config', { method: 'POST', body: JSON.stringify({ custom_templates: templates }) });
    state.data.config.custom_templates = templates;
    state.selectedTemplate = null;
    state.templateNew = false;
    state.templateDirty = false;
    state.templateDraftName = '';
    state.templateDraftBody = '';
    persistUIState();
    await load();
    toast('Template deleted', 'success');
  } catch (e) { toast(e.message, 'error'); }
};
$('copyLogBtn').onclick = async () => {
  const text = $('activityLog').textContent;
  if (!text || text === 'No activity yet.') {
    toast('No activity to copy.', 'error');
    return;
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const field = document.createElement('textarea');
      field.value = text;
      field.style.position = 'fixed';
      field.style.opacity = '0';
      document.body.appendChild(field);
      field.focus();
      field.select();
      document.execCommand('copy');
      field.remove();
    }
    toast('Activity log copied', 'success');
  } catch (e) {
    toast(`Could not copy activity log: ${e.message}`, 'error');
  }
};
$('clearLogBtn').onclick = () => {
  const logs = state.data?.logs || [];
  try {
    if (logs.length) localStorage.setItem(ACTIVITY_CLEAR_KEY, logs[logs.length - 1]);
    else localStorage.removeItem(ACTIVITY_CLEAR_KEY);
  } catch (_) {}
  $('activityLog').textContent = '';
  state.data.logs = [];
};
async function quitApplication() {
  if (state.quitting) return;
  state.quitting = true;
  $('quitModal').classList.remove('open');
  document.body.innerHTML = '';
  try {
    await api('/api/shutdown', { method: 'POST', body: '{}' });
  } catch (_) {
    // The backend may close before the shutdown response reaches the page.
  }
  try { window.close(); } catch (_) {}
}
$('quitBtn').onclick = () => $('quitModal').classList.add('open');
$('quitModalCancel').onclick = () => $('quitModal').classList.remove('open');
$('quitModalClose').onclick = () => $('quitModal').classList.remove('open');
$('quitModalConfirm').onclick = quitApplication;
$('quitModal').addEventListener('click', (event) => {
  if (event.target === $('quitModal')) $('quitModal').classList.remove('open');
});

$('intervalInput').onchange = async () => { try { await api('/api/config', { method: 'POST', body: JSON.stringify({ check_interval_seconds: $('intervalInput').value }) }); await load(); toast('Scan interval saved', 'success'); } catch (e) { toast(e.message, 'error'); } };
$('idleInput').onchange = async () => { try { await api('/api/config', { method: 'POST', body: JSON.stringify({ idle_auto_stop_minutes: $('idleInput').value }) }); await load(); toast('Idle-stop saved', 'success'); } catch (e) { toast(e.message, 'error'); } };
$('autoStartInput').onchange = async () => { try { await api('/api/setting', { method: 'POST', body: JSON.stringify({ key: 'auto_start_monitoring', value: $('autoStartInput').checked }) }); await load(); } catch (e) { toast(e.message, 'error'); } };
$('startWindowsInput').onchange = async () => { try { await api('/api/setting', { method: 'POST', body: JSON.stringify({ key: 'start_with_windows', value: $('startWindowsInput').checked }) }); await load(); } catch (e) { toast(e.message, 'error'); } };
$('minTrayInput').onchange = async () => { try { await api('/api/setting', { method: 'POST', body: JSON.stringify({ key: 'start_minimized_to_tray', value: $('minTrayInput').checked }) }); await load(); } catch (e) { toast(e.message, 'error'); } };

async function syncNativeWindowTheme(light) {
  try {
    await api('/api/window/theme', {
      method: 'POST',
      body: JSON.stringify({ light: !!light }),
    });
  } catch (_) {
    // Browser mode has no native pywebview title bar; ignore the 404/connection case.
  }
}

function applyTheme(light) {
  const isLight = !!light;
  document.documentElement.classList.toggle('light-theme', isLight);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = isLight ? '#f4f7fb' : '#0a0d14';
  try { localStorage.setItem('rpc-light-theme', isLight ? '1' : '0'); } catch (_) {}
  syncNativeWindowTheme(isLight);
}

const savedTheme = (() => {
  try { return localStorage.getItem('rpc-light-theme') === '1'; } catch (_) { return false; }
})();
applyTheme(savedTheme);
if ($('lightThemeInput')) {
  $('lightThemeInput').checked = savedTheme;
  $('lightThemeInput').onchange = async () => {
    const light = $('lightThemeInput').checked;
    applyTheme(light);
    try {
      await api('/api/setting', {
        method: 'POST',
        body: JSON.stringify({ key: 'light_theme', value: light }),
      });
    } catch (e) {
      toast(`Could not save theme preference: ${e.message}`, 'error');
    }
  };
}

function closeGroupModal() {
  state.editingGroupIndex = null;
  $('groupModal').classList.remove('open');
}

function openGroupModal(gi = null) {
  state.editingGroupIndex = gi;
  const g = gi === null ? {
    enabled: true, process_name: '', cdp_watch: false, cdp_port: 9222,
    widget_v2_enabled: false, widget_v2_app_id: '', widget_v2_user_id: '',
    widget_v2_bot_token: '', widget_v2_field_name: 'HQ_level',
    widget_v2_value_template: '{admiral_level}',
  } : state.data.config.groups[gi];

  $('groupModalTitle').textContent = gi === null ? 'Add Group' : 'Edit Group';
  $('groupModalSubtitle').textContent = gi === null
    ? 'Create a process profile and configure its live-data options.'
    : 'Edit the process, CDP, and Widget V2 settings for this group.';
  $('groupProcessName').value = g.process_name || '';
  $('groupEnabled').checked = g.enabled !== false;
  $('groupCdpWatch').checked = !!g.cdp_watch;
  $('groupCdpPort').value = g.cdp_port ?? 9222;
  $('groupWidgetEnabled').checked = !!g.widget_v2_enabled;
  $('groupWidgetAppId').value = g.widget_v2_app_id || '';
  $('groupWidgetUserId').value = g.widget_v2_user_id || '';
  const storedToken = g.widget_v2_bot_token || '';
  $('groupWidgetToken').value = storedToken && storedToken !== '__SET__' ? storedToken : '';
  $('groupWidgetToken').placeholder = storedToken === '__SET__' ? 'Saved token · leave blank to keep it' : 'Bot token';
  $('groupWidgetFieldName').value = g.widget_v2_field_name ?? 'HQ_level';
  $('groupWidgetValueTemplate').value = g.widget_v2_value_template ?? '{admiral_level}';
  $('groupModal').classList.add('open');
  requestAnimationFrame(() => $('groupProcessName').focus());
}

window.editGroup = (gi) => openGroupModal(gi);
window.copyGroup = async (gi) => {
  const source = state.data.config.groups[gi];
  if (!source) return;
  const copy = JSON.parse(JSON.stringify(source));
  copy.enabled = false;
  state.data.config.groups.splice(gi + 1, 0, copy);
  await saveGroups();
};
window.deleteGroup = (gi) => { if (!confirm('Delete this group and its variants?')) return; state.data.config.groups.splice(gi, 1); saveGroups(); };

$('addGroupBtn').onclick = () => openGroupModal(null);
$('groupModalCancel').onclick = closeGroupModal;
$('groupModalClose').onclick = closeGroupModal;
$('groupModal').addEventListener('click', (event) => {
  if (event.target === $('groupModal')) closeGroupModal();
});
$('groupModalSave').onclick = async () => {
  const processName = $('groupProcessName').value.trim();
  if (!processName) { toast('Process Name is required.', 'error'); $('groupProcessName').focus(); return; }
  const port = Number.parseInt($('groupCdpPort').value, 10);
  const group = {
    ...(state.editingGroupIndex === null ? {} : state.data.config.groups[state.editingGroupIndex]),
    process_name: processName,
    enabled: $('groupEnabled').checked,
    cdp_watch: $('groupCdpWatch').checked,
    cdp_port: Number.isInteger(port) && port > 0 && port <= 65535 ? port : 9222,
    widget_v2_enabled: $('groupWidgetEnabled').checked,
    widget_v2_app_id: $('groupWidgetAppId').value.trim(),
    widget_v2_user_id: $('groupWidgetUserId').value.trim(),
    widget_v2_field_name: $('groupWidgetFieldName').value.trim(),
    widget_v2_value_template: $('groupWidgetValueTemplate').value.trim(),
  };
  const token = $('groupWidgetToken').value.trim();
  group.widget_v2_bot_token = token || (state.editingGroupIndex === null ? '' : '__SET__');
  if (state.editingGroupIndex === null) {
    group.variants = group.variants || [];
    if (!group.variants.length) group.variants = [{ enabled: true, app_name: 'New Variant', name: '', client_id: '', details: '', state: '', large_image: '', large_text: '', large_url: '', small_image: '', small_text: '', small_url: '', show_timer: true, weight: 1, party_current: 0, party_max: 0, party_current_dynamic: false, button1_label: '', button1_url: '', button2_label: '', button2_url: '' }];
    state.data.config.groups.push(group);
  } else {
    state.data.config.groups[state.editingGroupIndex] = group;
  }
  closeGroupModal();
  await saveGroups();
};
let editingVariantIndex = null;
let editingVariantGroupIndex = null;

const defaultVariant = () => ({
  enabled: true, app_name: 'New Variant', name: '', client_id: '', details: '', state: '', stage_templates: stageTemplateDefaults(),
  large_image: '', large_text: '', large_url: '', small_image: '', small_text: '', small_url: '',
  show_timer: true, weight: 1, party_current: 0, party_max: 0, party_current_dynamic: false,
  button1_label: '', button1_url: '', button2_label: '', button2_url: ''
});

const STAGE_TEMPLATE_META = [
  ['in_port', 'In Port', 'Normal idle/harbor state.'],
  ['on_sortie', 'On Sortie', 'Map navigation and sortie state.'],
  ['in_battle', 'In Battle', 'Active daytime battle state.'],
  ['night_battle', 'Night Battle', 'Night-time battle stage.'],
  ['battle_result', 'Battle Result', 'Post-battle result before returning to normal.'],
  ['quest', 'Quest', 'Quest start, cancellation, and completion stage.'],
  ['repair_dock', 'Repair / Dock', 'Active repair-dock inspection stage.'],
  ['exercise_opponent', 'Exercise — Choosing Opponent', 'Practice opponent selection stage.'],
  ['exercise_battle', 'Exercise Battle', 'Active daytime practice battle stage.'],
  ['exercise_night_battle', 'Exercise Night Battle', 'Night-time practice battle stage.'],
  ['exercise_result', 'Exercise Result', 'Post-practice-battle result stage.'],
  ['expedition_result', 'Expedition Result', 'Mission/expedition return result.'],
];

function stageTemplateDefaults(source = {}) {
  const out = {};
  for (const [key] of STAGE_TEMPLATE_META) {
    const value = source[key] && typeof source[key] === 'object' ? source[key] : {};
    out[key] = {
      enabled: !!value.enabled,
      details: value.details || '',
      state: value.state || '',
    };
  }
  return out;
}

function renderStageTemplateEditor(source = {}) {
  const editor = $('stageTemplateEditor');
  if (!editor) return;
  const templates = stageTemplateDefaults(source);
  editor.innerHTML = STAGE_TEMPLATE_META.map(([key, label, help]) => {
    const t = templates[key];
    return `<div class="stage-template-card">
      <div class="stage-template-head">
        <div><strong>${esc(label)}</strong><span>${esc(help)}</span></div>
        <label class="stage-mode"><span>Mode</span><select id="stageMode_${key}">
          <option value="normal" ${t.enabled ? '' : 'selected'}>Use normal template</option>
          <option value="override" ${t.enabled ? 'selected' : ''}>Override this stage</option>
        </select></label>
      </div>
      <div class="stage-template-grid">
        <div class="field"><label for="stageDetails_${key}">Details</label><textarea id="stageDetails_${key}" rows="2" placeholder="Optional stage-specific Details"></textarea></div>
        <div class="field"><label for="stageState_${key}">State</label><textarea id="stageState_${key}" rows="2" placeholder="Optional stage-specific State"></textarea></div>
      </div>
    </div>`;
  }).join('');
  for (const [key] of STAGE_TEMPLATE_META) {
    $('stageDetails_'+key).value = templates[key].details;
    $('stageState_'+key).value = templates[key].state;
    const update = () => {
      const custom = $('stageMode_'+key).value === 'override';
      $('stageDetails_'+key).disabled = !custom;
      $('stageState_'+key).disabled = !custom;
      $('stageDetails_'+key).closest('.field').classList.toggle('stage-field-disabled', !custom);
      $('stageState_'+key).closest('.field').classList.toggle('stage-field-disabled', !custom);
    };
    $('stageMode_'+key).addEventListener('change', update);
    update();
  }
}

function readStageTemplates() {
  const out = {};
  for (const [key] of STAGE_TEMPLATE_META) {
    out[key] = {
      enabled: $('stageMode_'+key).value === 'override',
      details: $('stageDetails_'+key).value,
      state: $('stageState_'+key).value,
    };
  }
  return out;
}

function closeVariantModal() {
  editingVariantIndex = null;
  editingVariantGroupIndex = null;
  $('variantModal').classList.remove('open');
}

function openVariantModal(gi, vi = null) {
  editingVariantGroupIndex = gi;
  editingVariantIndex = vi;
  const source = vi === null ? defaultVariant() : (state.data.config.groups[gi].variants[vi] || defaultVariant());
  $('variantModalTitle').textContent = vi === null ? 'Add Variant' : 'Edit Variant';
  $('variantModalSubtitle').textContent = vi === null
    ? 'Create a complete Discord Rich Presence profile for this group.'
    : 'Edit every part of this Rich Presence profile.';
  const map = {
    variantEnabled: source.enabled !== false, variantAppName: source.app_name || '', variantName: source.name || '',
    variantClientId: source.client_id || '', variantDetails: source.details || '', variantState: source.state || '',
    variantLargeImage: source.large_image || '', variantLargeText: source.large_text || '', variantLargeUrl: source.large_url || '',
    variantSmallImage: source.small_image || '', variantSmallText: source.small_text || '', variantSmallUrl: source.small_url || '',
    variantShowTimer: source.show_timer !== false, variantWeight: source.weight ?? 1,
    variantPartyCurrent: source.party_current ?? 0, variantPartyMax: source.party_max ?? 0,
    variantPartyDynamic: !!source.party_current_dynamic, variantButton1Label: source.button1_label || '',
    variantButton1Url: source.button1_url || '', variantButton2Label: source.button2_label || '', variantButton2Url: source.button2_url || ''
  };
  for (const [id, value] of Object.entries(map)) {
    const el = $(id);
    if (el.type === 'checkbox') el.checked = !!value; else el.value = value;
  }
  renderStageTemplateEditor(source.stage_templates || {});
  $('variantModal').classList.add('open');
  requestAnimationFrame(() => $('variantAppName').focus());
}

window.editVariant = (gi, vi) => openVariantModal(gi, vi);
window.addVariant = (gi) => openVariantModal(gi, null);
window.copyVariant = async (gi, vi) => {
  const group = state.data.config.groups[gi];
  const source = group?.variants?.[vi];
  if (!source) return;
  const copy = JSON.parse(JSON.stringify(source));
  const baseName = copy.app_name || 'Variant';
  copy.app_name = `${baseName} (Copy)`;
  group.variants.splice(vi + 1, 0, copy);
  await saveGroups();
};
window.toggleVariant = (gi, vi) => {
  const v = state.data.config.groups[gi].variants[vi];
  v.enabled = v.enabled === false;
  saveGroups();
};
window.toggleGroup = (gi) => {
  const g = state.data.config.groups[gi];
  g.enabled = g.enabled === false;
  saveGroups();
};
window.deleteVariant = (gi, vi) => {
  if (!confirm('Delete this variant?')) return;
  const vs = state.data.config.groups[gi].variants;
  if (vs.length <= 1) { toast('A group needs at least one variant.', 'error'); return; }
  vs.splice(vi, 1);
  saveGroups();
};

$('variantModalCancel').onclick = closeVariantModal;
$('variantModalClose').onclick = closeVariantModal;
$('variantModal').addEventListener('click', (event) => {
  if (event.target === $('variantModal')) closeVariantModal();
});
$('variantModalSave').onclick = async () => {
  const gi = editingVariantGroupIndex;
  if (gi === null || !state.data.config.groups[gi]) return;
  const group = state.data.config.groups[gi];
  const variant = {
    ...(editingVariantIndex === null ? defaultVariant() : group.variants[editingVariantIndex]),
    enabled: $('variantEnabled').checked,
    app_name: $('variantAppName').value.trim() || 'Variant',
    name: $('variantName').value,
    client_id: $('variantClientId').value.trim(),
    details: $('variantDetails').value,
    state: $('variantState').value,
    stage_templates: readStageTemplates(),
    large_image: $('variantLargeImage').value.trim(),
    large_text: $('variantLargeText').value,
    large_url: $('variantLargeUrl').value.trim(),
    small_image: $('variantSmallImage').value.trim(),
    small_text: $('variantSmallText').value,
    small_url: $('variantSmallUrl').value.trim(),
    show_timer: $('variantShowTimer').checked,
    weight: Math.max(1, Number.parseInt($('variantWeight').value, 10) || 1),
    party_current: $('variantPartyCurrent').value,
    party_max: Math.max(0, Number.parseInt($('variantPartyMax').value, 10) || 0),
    party_current_dynamic: $('variantPartyDynamic').checked,
    button1_label: $('variantButton1Label').value.trim(), button1_url: $('variantButton1Url').value.trim(),
    button2_label: $('variantButton2Label').value.trim(), button2_url: $('variantButton2Url').value.trim(),
  };
  if (!variant.client_id) { toast('Discord Client ID is required.', 'error'); $('variantClientId').focus(); return; }
  if (editingVariantIndex === null) group.variants.push(variant);
  else group.variants[editingVariantIndex] = variant;
  closeVariantModal();
  await saveGroups();
};

async function saveGroups() { try { await api('/api/config', { method: 'POST', body: JSON.stringify({ groups: state.data.config.groups }) }); await load(); toast('Groups saved', 'success'); } catch (e) { toast(e.message, 'error'); } }

document.addEventListener('keydown', e => {
  // QoL: Delete clears the entire current editable field.
  // Left Alt + Delete also works because Delete alone is enough.
  if (e.key === 'Delete') {
    const el = document.activeElement;
    const isEditableField = el && !el.disabled && !el.readOnly && (
      el.tagName === 'TEXTAREA' ||
      (el.tagName === 'INPUT' && !/^(button|checkbox|color|file|hidden|image|radio|range|reset|submit)$/i.test(el.type)) ||
      el.isContentEditable
    );

    if (isEditableField) {
      e.preventDefault();
      if (el.isContentEditable) {
        el.textContent = '';
      } else {
        el.value = '';
      }
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault(); $('commandInput').focus(); $('commandPalette').classList.add('open');
  }
  if (e.key === 'Escape') $('commandPalette').classList.remove('open');
});
$('commandInput').addEventListener('input', e => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll('.command-item').forEach(item => item.hidden = q && !item.textContent.toLowerCase().includes(q));
});
document.querySelectorAll('.command-item').forEach(item => item.addEventListener('click', () => { showPage(item.dataset.page); $('commandPalette').classList.remove('open'); $('commandInput').value = ''; document.querySelectorAll('.command-item').forEach(x => x.hidden = false); }));
$('commandPalette').addEventListener('click', e => { if (e.target === $('commandPalette')) $('commandPalette').classList.remove('open'); });

setInterval(load, 1500);
load();
