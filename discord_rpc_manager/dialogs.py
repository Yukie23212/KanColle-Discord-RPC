# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import tkinter as tk
from tkinter import ttk, messagebox

from .constants import DEFAULT_CDP_PORT, VARIANT_DEFAULTS
from .cdp_watcher import CDP_AVAILABLE
from .utils import safe_format


class GroupDialog(tk.Toplevel):
    def __init__(self, master, group=None):
        super().__init__(master)
        self.title("Edit Group" if group else "Add Group")
        self.resizable(False, False)
        self.result = None
        self.transient(master)
        self.grab_set()

        ttk.Label(self, text="Process Name:").grid(row=0, column=0, sticky="e", padx=8, pady=8)
        self.process_var = tk.StringVar(value=(group.get("process_name", "") if group else ""))
        ttk.Entry(self, textvariable=self.process_var, width=36).grid(row=0, column=1, padx=8, pady=8, sticky="w")
        ttk.Label(
            self, text="e.g. damecon-browser.exe -- must match Task Manager exactly",
            foreground="#888888", font=("Segoe UI", 8),
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=8)

        self.enabled_var = tk.BooleanVar(value=(group.get("enabled", True) if group else True))
        ttk.Checkbutton(self, text="Enabled", variable=self.enabled_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 4)
        )

        cdp_frame = ttk.LabelFrame(self, text="Live data (KanColle-style, via Chrome DevTools)", padding=(8, 6))
        cdp_frame.grid(row=3, column=0, columnspan=2, sticky="we", padx=8, pady=(4, 4))

        self.cdp_watch_var = tk.BooleanVar(value=(group.get("cdp_watch", False) if group else False))
        cdp_cb = ttk.Checkbutton(
            cdp_frame, text="Watch live game data (Admiral/fleet/ship) instead of static text",
            variable=self.cdp_watch_var,
            state=("normal" if CDP_AVAILABLE else "disabled"),
        )
        cdp_cb.pack(anchor="w")
        if not CDP_AVAILABLE:
            ttk.Label(
                cdp_frame, text="Unavailable -- install 'websocket-client' (pip install websocket-client)",
                foreground="#888888", font=("Segoe UI", 8),
            ).pack(anchor="w")

        port_row = ttk.Frame(cdp_frame)
        port_row.pack(anchor="w", pady=(4, 0))
        ttk.Label(port_row, text="CDP port:").pack(side="left")
        self.cdp_port_var = tk.StringVar(value=str(group.get("cdp_port", DEFAULT_CDP_PORT) if group else DEFAULT_CDP_PORT))
        ttk.Entry(port_row, textvariable=self.cdp_port_var, width=8).pack(side="left", padx=(4, 0))

        ttk.Label(
            cdp_frame,
            text=(
                "The browser must be launched with matching --remote-debugging-port\n"
                "AND --remote-allow-origins=* flags. When this is on, a Variant's\n"
                "Details/State can use placeholders: {admiral_nickname} {admiral_level}\n"
                "{admiral_rank} {ship_count} {fleet_name} {fleet_status} {fleet_ship_count}\n"
                "{sortie_win} {sortie_lose} {expedition_success} {expedition_count}\n"
                "{flamethrower} {bucket} {dev_material} {screw}"
            ),
            foreground="#888888", font=("Segoe UI", 8), justify="left",
        ).pack(anchor="w", pady=(4, 0))

        widget_frame = ttk.LabelFrame(self, text="Discord Widget V2 sync (profile field, not Rich Presence)", padding=(8, 6))
        widget_frame.grid(row=4, column=0, columnspan=2, sticky="we", padx=8, pady=(4, 4))

        self.widget_v2_enabled_var = tk.BooleanVar(value=(group.get("widget_v2_enabled", False) if group else False))
        ttk.Checkbutton(
            widget_frame, text="Push {admiral_level} to a Discord Application Profile field",
            variable=self.widget_v2_enabled_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        widget_fields = [
            ("widget_v2_app_id", "App ID:", False),
            ("widget_v2_user_id", "User ID:", False),
            ("widget_v2_bot_token", "Bot Token:", True),
            ("widget_v2_field_name", "Field Name:", False),
            ("widget_v2_value_template", "Value Template:", False),
        ]
        self.widget_v2_vars = {}
        for i, (key, label, is_secret) in enumerate(widget_fields, start=1):
            ttk.Label(widget_frame, text=label).grid(row=i, column=0, sticky="e", padx=(0, 4), pady=2)
            default_map = {"widget_v2_field_name": "HQ_level", "widget_v2_value_template": "{admiral_level}"}
            default = group.get(key, default_map.get(key, "")) if group else default_map.get(key, "")
            var = tk.StringVar(value=default)
            self.widget_v2_vars[key] = var
            entry = ttk.Entry(widget_frame, textvariable=var, width=42, show=("*" if is_secret else ""))
            entry.grid(row=i, column=1, sticky="w", pady=2)

        ttk.Label(
            widget_frame,
            text=(
                "Value Template accepts the same {admiral_level} etc. placeholders as\n"
                "Details/State -- add your own text around it, e.g. \"{admiral_level} [Taisho]\",\n"
                "and only re-type it yourself when the hand-written part needs to change.\n"
                "Only pushes when the rendered result actually changes -- this is a plain\n"
                "profile field update (separate from Rich Presence), and per Discord's own\n"
                "behavior, an already-open Discord client needs a restart to show it."
            ),
            foreground="#888888", font=("Segoe UI", 8), justify="left",
        ).grid(row=len(widget_fields) + 1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        note = (
            "A group holds one or more Variants (added afterwards). If a group\n"
            "has more than one variant, one is picked at random each time this\n"
            "process starts, and stays active until it closes."
        )
        ttk.Label(self, text=note, foreground="#888888", font=("Segoe UI", 8), justify="left").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8)
        )

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(4, 10))
        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

        self.bind("<Return>", lambda e: self._on_save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_save(self):
        process_name = self.process_var.get().strip()
        if not process_name:
            messagebox.showerror("Missing info", "Process Name is required (e.g. damecon-browser.exe).")
            return
        try:
            cdp_port = int(self.cdp_port_var.get())
        except ValueError:
            cdp_port = DEFAULT_CDP_PORT
        self.result = {
            "process_name": process_name,
            "enabled": self.enabled_var.get(),
            "cdp_watch": self.cdp_watch_var.get(),
            "cdp_port": cdp_port,
            "widget_v2_enabled": self.widget_v2_enabled_var.get(),
            "widget_v2_app_id": self.widget_v2_vars["widget_v2_app_id"].get().strip(),
            "widget_v2_user_id": self.widget_v2_vars["widget_v2_user_id"].get().strip(),
            "widget_v2_bot_token": self.widget_v2_vars["widget_v2_bot_token"].get().strip(),
            "widget_v2_field_name": self.widget_v2_vars["widget_v2_field_name"].get().strip(),
            "widget_v2_value_template": self.widget_v2_vars["widget_v2_value_template"].get().strip(),
        }
        self.destroy()


class VariantDialog(tk.Toplevel):
    
    SECTIONS = [
        ("Identity", [
            ("app_name", "Display Name", "Internal label only (shown in this app's list/log) -- NOT sent to Discord"),
            ("name", "Discord Name", "Activity title sent to Discord. Leave empty to use the Discord Application's registered name."),
            ("client_id", "Discord Client ID", "Client ID of the Discord Application used for this presence"),
        ]),
        ("Text", [
            ("details", "Details (top line)", "e.g. Browsing articles"),
            ("state", "State (second line)", "e.g. Focus Mode"),
        ]),
        ("Images", [
            ("large_image", "Large Image Key", "Asset key from Art Assets, OR a direct https:// image URL"),
            ("large_text", "Large Image Text", "Tooltip text shown on hover"),
            ("large_url", "Large Image URL", "Optional URL opened when clicking the large image"),
            ("small_image", "Small Image Key", "Optional -- asset key or direct https:// image URL"),
            ("small_text", "Small Image Text", "Optional tooltip shown on hover"),
            ("small_url", "Small Image URL", "Optional URL opened when clicking the small image"),
        ]),
        ("Party", [
            ("party_current", "Party Current", "Static value unless Dynamic Party Current is enabled below."),
            ("party_max", "Party Max", "e.g. 100 -- leave at 0 to hide the party count entirely"),
        ]),
        ("Buttons (visible to others viewing your profile, not to you)", [
            ("button1_label", "Button 1 Label", "e.g. \"Visit Website\" -- max 32 characters"),
            ("button1_url", "Button 1 URL", "Must start with http:// or https://"),
            ("button2_label", "Button 2 Label", "Optional second button"),
            ("button2_url", "Button 2 URL", "Must start with http:// or https://"),
        ]),
        ("Behavior", [
            ("weight", "Random Weight", "Higher = picked more often within this group. Default 1 = equal chance."),
        ]),
    ]

    def __init__(self, master, variant=None, sibling_client_ids=None):
        super().__init__(master)
        self.title("Edit Variant" if variant else "Add Variant")
        self.geometry("620x600")
        self.minsize(560, 400)
        self.result = None
        self.transient(master)
        self.grab_set()
        self.sibling_client_ids = sibling_client_ids or []

        variant = variant or {}
        self.vars = {}

        warn = (
            "Discord Name is the activity title sent by Rich Presence. If it is empty, "
            "Discord uses the Application name associated with the Client ID. Display "
            "Name remains an internal label for this manager only."
        )
        ttk.Label(
            self, text=warn, foreground="#b06000", font=("Segoe UI", 8, "italic"),
            justify="left", wraplength=580,
        ).pack(fill="x", padx=10, pady=(10, 4))

        if CDP_AVAILABLE:
            live_hint = (
                "If this group has 'Watch live game data' enabled, Details/State below "
                "are filled from live data instead of shown as literal text -- e.g. "
                "\"HQ Lv.{admiral_level}\" or \"{fleet_name}: {fleet_status}\"."
            )
            ttk.Label(
                self, text=live_hint, foreground="#888888", font=("Segoe UI", 8),
                justify="left", wraplength=580,
            ).pack(fill="x", padx=10, pady=(0, 6))

        
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=6)
        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        vscroll = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(_event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        for section_title, fields in self.SECTIONS:
            section = ttk.LabelFrame(body, text=section_title, padding=(10, 6))
            section.pack(fill="x", padx=6, pady=6)
            for i, (key, label, hint) in enumerate(fields):
                ttk.Label(section, text=label + ":").grid(row=i, column=0, sticky="e", padx=6, pady=3)
                default = variant.get(key, "")
                if key in ("weight", "party_current", "party_max"):
                    default = variant.get(key, VARIANT_DEFAULTS.get(key, 0))
                var = tk.StringVar(value=str(default))
                self.vars[key] = var
                ttk.Entry(section, textvariable=var, width=40).grid(
                    row=i, column=1, padx=6, pady=3, sticky="w"
                )
                ttk.Label(
                    section, text=hint, foreground="#888888", font=("Segoe UI", 8),
                    wraplength=220, justify="left",
                ).grid(row=i, column=2, sticky="w", padx=(4, 4))

        self.party_current_dynamic_var = tk.BooleanVar(
            value=variant.get("party_current_dynamic", False)
        )
        ttk.Checkbutton(
            body,
            text="Dynamic Party Current (use {ship_count})",
            variable=self.party_current_dynamic_var,
        ).pack(anchor="w", padx=12, pady=(0, 6))

        behavior_extra = ttk.Frame(body)
        behavior_extra.pack(fill="x", padx=6, pady=(0, 6))
        self.show_timer_var = tk.BooleanVar(value=variant.get("show_timer", True))
        ttk.Checkbutton(
            behavior_extra, text="Show elapsed-time timer", variable=self.show_timer_var
        ).pack(anchor="w")
        self.enabled_var = tk.BooleanVar(value=variant.get("enabled", True))
        ttk.Checkbutton(
            behavior_extra, text="Enabled (eligible to be picked)", variable=self.enabled_var
        ).pack(anchor="w")

        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=8)
        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(side="left", padx=(10, 6))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left")

        self.bind("<Return>", lambda e: self._on_save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_save(self):
        data = {k: v.get().strip() for k, v in self.vars.items()}
        if not data["app_name"]:
            messagebox.showerror("Missing info", "Display Name is required.")
            return
        if not data["client_id"]:
            if not messagebox.askyesno(
                "No Client ID",
                "No Discord Client ID was entered. You can still save this variant, "
                "but it will be skipped until you add one. Continue?",
            ):
                return
        elif data["client_id"] in self.sibling_client_ids:
            if not messagebox.askyesno(
                "Same Client ID as another variant",
                "Another variant in this group already uses this Client ID. Since "
                "Discord's displayed title comes from the Application tied to the "
                "Client ID (unless Discord Name is set), these two variants may look "
                "identical on Discord aside from Details/State text. Save anyway?",
            ):
                return

        try:
            data["weight"] = max(1, int(data.get("weight") or 1))
        except ValueError:
            data["weight"] = 1

        try:
            data["party_max"] = max(0, int(data.get("party_max") or 0))
        except ValueError:
            data["party_max"] = 0

        data["party_current_dynamic"] = self.party_current_dynamic_var.get()
        if data["party_current_dynamic"]:
            
            data["party_current"] = "{ship_count}"
        else:
            try:
                data["party_current"] = max(0, int(data.get("party_current") or 0))
            except ValueError:
                data["party_current"] = 0
            if data["party_current"] > data["party_max"]:
                data["party_current"] = data["party_max"]

        for label_key, url_key, btn_name in (
            ("button1_label", "button1_url", "Button 1"),
            ("button2_label", "button2_url", "Button 2"),
        ):
            label = data.get(label_key, "")
            url = data.get(url_key, "")
            if label and not url:
                messagebox.showerror("Missing info", f"{btn_name} has a label but no URL.")
                return
            if url and not label:
                messagebox.showerror("Missing info", f"{btn_name} has a URL but no label.")
                return
            if url and not (url.startswith("http://") or url.startswith("https://")):
                if not messagebox.askyesno(
                    "Unusual button URL",
                    f"{btn_name}'s URL doesn't start with http:// or https://, which "
                    "Discord requires for buttons to work. Save anyway?",
                ):
                    return

        data["show_timer"] = self.show_timer_var.get()
        data["enabled"] = self.enabled_var.get()
        self.result = data
        self.destroy()



class CustomTemplatesDialog(tk.Toplevel):
    """Manage user-defined reusable format templates."""

    def __init__(self, master, templates=None, get_preview_snapshot=None):
        super().__init__(master)
        self.title("Custom Templates")
        self.geometry("760x470")
        self.minsize(620, 380)
        self.result = None
        self.transient(master)
        self.grab_set()

        self.templates = dict(templates or {})
        self.get_preview_snapshot = get_preview_snapshot or (lambda: None)

        info = (
            "Create reusable placeholders such as {fleet_info}. The template value can "
            "contain built-in live-data placeholders (for example {fleet_name}, {fleet_status}) "
            "or other custom placeholders. Use the custom name inside braces when writing Details/State."
        )
        ttk.Label(
            self, text=info, foreground="#666666", font=("Segoe UI", 8),
            justify="left", wraplength=720,
        ).pack(fill="x", padx=10, pady=(10, 6))

        body = ttk.Frame(self, padding=(10, 0, 10, 0))
        body.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(body, columns=("template",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Placeholder")
        self.tree.heading("template", text="Template")
        self.tree.column("#0", width=170, minwidth=140)
        self.tree.column("template", width=520, minwidth=300)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._edit())

        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="left", fill="y")

        buttons = ttk.Frame(body, padding=(10, 0, 0, 0))
        buttons.pack(side="left", fill="y")
        ttk.Button(buttons, text="Add", command=self._add).pack(fill="x", pady=2)
        ttk.Button(buttons, text="Edit", command=self._edit).pack(fill="x", pady=2)
        ttk.Button(buttons, text="Delete", command=self._delete).pack(fill="x", pady=2)

        hint = (
            "Example:\n"
            "Name: fleet_info\n"
            "Template: Fleet: {fleet_name} — {fleet_status}\n\n"
            "Built-in live-data values are resolved first, so a custom template "
            "cannot override a real snapshot field with the same name."
        )
        ttk.Label(
            self, text=hint, foreground="#888888", font=("Segoe UI", 8),
            justify="left", wraplength=720,
        ).pack(fill="x", padx=10, pady=(6, 4))

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=(4, 10))
        ttk.Button(bottom, text="Save", command=self._save).pack(side="left", padx=(10, 6))
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="left")

        self._refresh()
        self.bind("<Escape>", lambda e: self.destroy())

    def _refresh(self, select_name=None):
        self.tree.delete(*self.tree.get_children())
        for name in sorted(self.templates, key=str.casefold):
            self.tree.insert("", "end", iid=name, text=f"{{{name}}}", values=(self.templates[name],))
        if select_name and self.tree.exists(select_name):
            self.tree.selection_set(select_name)
            self.tree.focus(select_name)
            self.tree.see(select_name)

    def _selected_name(self):
        selection = self.tree.selection()
        return selection[0] if selection else None

    def _add(self):
        self._open_editor()

    def _edit(self):
        name = self._selected_name()
        if name is None:
            messagebox.showinfo("Custom Templates", "Select a custom placeholder first.", parent=self)
            return
        self._open_editor(name)

    def _delete(self):
        name = self._selected_name()
        if name is None:
            messagebox.showinfo("Custom Templates", "Select a custom placeholder first.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete Custom Template",
            f"Delete custom placeholder '{{{name}}}'?",
            parent=self,
        ):
            return
        del self.templates[name]
        self._refresh()

    def _open_editor(self, original_name=None):
        dialog = _CustomTemplateEditor(
            self,
            original_name,
            self.templates.get(original_name, ""),
            get_preview_snapshot=self.get_preview_snapshot,
        )
        self.wait_window(dialog)
        if not dialog.result:
            return

        name, template = dialog.result
        if name != original_name and name in self.templates:
            messagebox.showerror(
                "Duplicate Placeholder",
                f"A custom placeholder named '{{{name}}}' already exists.",
                parent=self,
            )
            return

        if original_name is not None and original_name != name:
            del self.templates[original_name]
        self.templates[name] = template
        self._refresh(select_name=name)

    def _save(self):
        self.result = dict(self.templates)
        self.destroy()


class _CustomTemplateEditor(tk.Toplevel):
    """Editor for one custom template, with a live rendered preview."""

    _PREVIEW_EXAMPLE_SNAPSHOT = {
        "admiral_nickname": "Haru",
        "admiral_level": 120,
        "fleet_name": "1st Fleet",
        "fleet_status": "In Port",
        "fleet_ship_count": 6,
        "fleet_total_slots": 6,
        "fleet1_summary": "Fleet: 1st Fleet — 「6/6 ships」",
        "ship_count": 180,
        "fuel": "100k",
        "ammo": "100k",
        "steel": "100k",
        "bauxite": "100k",
        "flamethrower": 42,
        "bucket": 37,
        "dev_material": 58,
        "screw": 26,
        "sortie_win": 2232,
        "sortie_lose": 98,
        "expedition_success": 899,
        "expedition_count": 994,
        "location_text": "Home Port",
        "map_area": "1-1",
        "map_node_text": "Node 1",
        "battle_rank": "S",
        "expedition_result": "Great Success",
    }

    def __init__(self, master, original_name=None, template="", get_preview_snapshot=None):
        super().__init__(master)
        self.title("Edit Custom Template" if original_name is not None else "Add Custom Template")
        self.geometry("720x560")
        self.minsize(600, 470)
        self.result = None
        self.original_name = original_name
        self.get_preview_snapshot = get_preview_snapshot or (lambda: None)
        self._preview_after_id = None
        self.transient(master)
        self.grab_set()

        ttk.Label(self, text="Placeholder Name:").pack(anchor="w", padx=10, pady=(10, 2))
        self.name_var = tk.StringVar(value=original_name or "")
        name_entry = ttk.Entry(self, textvariable=self.name_var)
        name_entry.pack(fill="x", padx=10)
        name_entry.bind("<KeyRelease>", self._on_template_changed)

        ttk.Label(
            self,
            text="Use the name without braces here; it will be used as {name} in templates.",
            foreground="#888888", font=("Segoe UI", 8),
        ).pack(anchor="w", padx=10, pady=(2, 8))

        ttk.Label(self, text="Template:").pack(anchor="w", padx=10, pady=(0, 2))
        self.template_text = tk.Text(self, wrap="word", height=8, undo=True)
        self.template_text.pack(fill="both", expand=True, padx=10)
        self.template_text.insert("1.0", template)
        self.template_text.bind("<KeyRelease>", self._on_template_changed)

        ttk.Label(
            self,
            text=(
                "Example: Fleet: {fleet_name} — {fleet_status}\n"
                "You can also reference another custom placeholder, e.g. Status: {fleet_info}."
            ),
            foreground="#888888", font=("Segoe UI", 8), justify="left",
        ).pack(anchor="w", padx=10, pady=(6, 4))

        preview_frame = ttk.LabelFrame(self, text="Rendered Preview", padding=(8, 6))
        preview_frame.pack(fill="x", padx=10, pady=(2, 8))

        self.preview_status_var = tk.StringVar(
            value="Preview uses example values until live data is available."
        )
        ttk.Label(
            preview_frame,
            textvariable=self.preview_status_var,
            foreground="#888888",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 4))

        self.preview_text = tk.Text(
            preview_frame,
            height=4,
            wrap="word",
            state="disabled",
            relief="sunken",
            borderwidth=1,
        )
        self.preview_text.pack(fill="x", expand=False)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(4, 10))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left", padx=(10, 6))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="left")

        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Control-Return>", lambda e: self._save())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        name_entry.focus_set()
        self.after(50, self._refresh_preview)

    def _on_template_changed(self, _event=None):
        self._refresh_preview()

    def _current_preview_templates(self):
        templates = dict(getattr(self.master, "templates", {}) or {})
        name = self.name_var.get().strip()
        template = self.template_text.get("1.0", "end-1c")
        if self.original_name and self.original_name != name:
            templates.pop(self.original_name, None)
        if name:
            templates[name] = template
        return templates

    def _get_preview_snapshot(self):
        try:
            snapshot = self.get_preview_snapshot()
        except Exception:
            snapshot = None
        if isinstance(snapshot, dict) and snapshot:
            return snapshot, True
        return dict(self._PREVIEW_EXAMPLE_SNAPSHOT), False

    def _refresh_preview(self):
        if not self.winfo_exists():
            return

        template = self.template_text.get("1.0", "end-1c")
        snapshot, is_live = self._get_preview_snapshot()
        templates = self._current_preview_templates()
        try:
            rendered = safe_format(template, snapshot, templates)
        except Exception as e:
            rendered = f"Preview error: {e}"
        if not rendered:
            rendered = "(empty)"

        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", rendered)
        self.preview_text.configure(state="disabled")

        if is_live:
            self.preview_status_var.set(
                "Live preview — using the current snapshot from the running monitor."
            )
        else:
            self.preview_status_var.set(
                "Example preview — start monitoring with live CDP data to preview against the current game state."
            )

        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
        self._preview_after_id = self.after(750, self._refresh_preview)

    def _cancel(self):
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id = None
        self.destroy()

    def _save(self):
        name = self.name_var.get().strip()
        template = self.template_text.get("1.0", "end-1c").strip()

        if not name:
            messagebox.showerror("Missing info", "Placeholder Name is required.", parent=self)
            return
        if not name.replace("_", "a").isalnum() or name[0].isdigit():
            messagebox.showerror(
                "Invalid Placeholder Name",
                "Use letters, numbers, and underscores only, and do not start with a number.\n"
                "Example: fleet_info",
                parent=self,
            )
            return
        if not template:
            messagebox.showerror("Missing info", "Template cannot be empty.", parent=self)
            return

        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id = None

        self.result = (name, template)
        self.destroy()
