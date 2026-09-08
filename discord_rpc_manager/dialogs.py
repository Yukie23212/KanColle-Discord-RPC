# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import tkinter as tk
from tkinter import ttk, messagebox

from .constants import DEFAULT_CDP_PORT, VARIANT_DEFAULTS
from .cdp_watcher import CDP_AVAILABLE


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
                "{admiral_rank} {ship_count} {fleet_name} {fleet_status} {fleet_ship_count}"
            ),
            foreground="#888888", font=("Segoe UI", 8), justify="left",
        ).pack(anchor="w", pady=(4, 0))

        note = (
            "A group holds one or more Variants (added afterwards). If a group\n"
            "has more than one variant, one is picked at random each time this\n"
            "process starts, and stays active until it closes."
        )
        ttk.Label(self, text=note, foreground="#888888", font=("Segoe UI", 8), justify="left").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8)
        )

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(4, 10))
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

