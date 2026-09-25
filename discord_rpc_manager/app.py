# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import copy
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .constants import APP_TITLE, DEFAULT_INTERVAL, DEFAULT_CONFIG
from .config import (
    CONFIG_PATH, load_config, save_config, _normalize_group, _normalize_variant,
    set_start_with_windows, get_data_dir,
)
from .cdp_watcher import CDP_AVAILABLE
from .dialogs import GroupDialog, VariantDialog, CustomTemplatesDialog
from .monitor import RPCMonitor


def resource_path(filename):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, filename)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, filename)

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except Exception:
    TRAY_AVAILABLE = False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.iconbitmap(resource_path("icon.ico"))

        self.active_config_path = CONFIG_PATH
        self.title(APP_TITLE)

        self.config_data = load_config()
        self.log_queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.monitor = None
        self.tray_icon = None
        self.log_window = None
        self.log_text = None
        self.show_log_window = tk.BooleanVar(value=False)
        self.web_command_queue = queue.Queue()
        self.web_log_buffer = []
        self._web_status_text = "Idle"
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        window_width = min(900, screen_width - 40)
        window_height = min(600, screen_height - 80)

        self.geometry(f"{window_width}x{window_height}")
        self.minsize(760, 460)

        self.log_queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.monitor = None
        self.tray_icon = None

        self._build_menu()
        self._build_ui()
        self._refresh_group_tree()
        self._poll_queues()
        self._update_title()

        self.protocol("WM_DELETE_WINDOW", self._on_close_button)

        
        
        
        if sys.platform == "win32" and self.config_data.get("start_with_windows"):
            try:
                set_start_with_windows(True)
            except RuntimeError as e:
                self._pending_startup_warning = str(e)

        
        
        self.after(250, self._apply_launch_options)

    def _update_title(self):
        self.title(f"{APP_TITLE} \u2014 {os.path.basename(self.active_config_path)}")

    def _save_config(self):
        save_config(self.config_data, self.active_config_path)

    
    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Config", command=self._new_config)
        file_menu.add_command(label="Open Config...", command=self._open_config)
        file_menu.add_command(label="Save", command=self._menu_save)
        file_menu.add_command(label="Save As...", command=self._save_config_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close_button)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

    def _confirm_discard_if_monitoring(self):
        if self.monitor and self.monitor.is_alive():
            return messagebox.askyesno(
                APP_TITLE,
                "Monitoring is currently running. Switching config files will stop it. Continue?",
            )
        return True

    def _new_config(self):
        if not self._confirm_discard_if_monitoring():
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "Start a new blank config? Any unsaved changes to the current one will be "
            "lost unless you Save or Save As first.",
        ):
            return
        if self.monitor and self.monitor.is_alive():
            self._toggle_monitor()
        self.config_data = json.loads(json.dumps(DEFAULT_CONFIG))
        self.active_config_path = CONFIG_PATH
        self._load_config_into_ui()
        self._append_log("Started a new blank config. Use Save As... to choose where to store it.")

    def _notify_config_dialog_open(self):
        """Play a short Windows system sound when the native file dialog opens."""
        if os.name != "nt":
            return
        try:
            import winsound
            winsound.PlaySound(
                "SystemExclamation",
                winsound.SND_ALIAS | winsound.SND_ASYNC,
            )
        except Exception:
            pass

    def _open_config(self):
        if not self._confirm_discard_if_monitoring():
            return
        self._notify_config_dialog_open()
        path = filedialog.askopenfilename(
            title="Open Config", filetypes=[("JSON config", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        if self.monitor and self.monitor.is_alive():
            self._toggle_monitor()
        self.config_data = load_config(path)
        self.active_config_path = path
        self._load_config_into_ui()
        self._append_log(f"Loaded config from {path}")

    def _menu_save(self):
        self._save_config()
        self._append_log(f"Saved to {self.active_config_path}")

    def _save_config_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Config As", defaultextension=".json",
            filetypes=[("JSON config", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self.active_config_path = path
        self._save_config()
        self._update_title()
        self._append_log(f"Saved to {path}")

    def _load_config_into_ui(self):
        """Refreshes every widget that mirrors self.config_data -- called
        after loading a different config file or starting a new blank one."""
        self.interval_var.set(str(self.config_data.get("check_interval_seconds", DEFAULT_INTERVAL)))
        self.idle_stop_var.set(str(self.config_data.get("idle_auto_stop_minutes", 0)))
        self.auto_monitor_var.set(self.config_data.get("auto_start_monitoring", False))
        self.minimize_launch_var.set(self.config_data.get("start_minimized_to_tray", False))
        self.start_with_windows_var.set(self.config_data.get("start_with_windows", False))
        self._refresh_group_tree()
        self._update_title()
        self.status_label.config(text="Status: Idle")
        self.start_stop_btn.config(text="Start Monitoring")

    def _apply_launch_options(self):
        if getattr(self, "_pending_startup_warning", None):
            messagebox.showwarning(APP_TITLE, self._pending_startup_warning)
            self._pending_startup_warning = None

        if self.config_data.get("auto_start_monitoring"):
            if any(g.get("enabled") for g in self.config_data["groups"]) and not (
                self.monitor and self.monitor.is_alive()
            ):
                self._toggle_monitor()
            elif not any(g.get("enabled") for g in self.config_data["groups"]):
                self._append_log(
                    "Auto-start monitoring is on, but no group is enabled yet -- add one to begin."
                )

        if self.config_data.get("start_minimized_to_tray") and TRAY_AVAILABLE:
            self._minimize_to_tray()

    
    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Scan interval (seconds):").pack(side="left")
        self.interval_var = tk.StringVar(value=str(self.config_data.get("check_interval_seconds", DEFAULT_INTERVAL)))
        interval_spin = ttk.Spinbox(
            top, from_=2, to=300, width=5, textvariable=self.interval_var,
            command=self._save_interval,
        )
        interval_spin.pack(side="left", padx=(4, 20))
        interval_spin.bind("<FocusOut>", lambda e: self._save_interval())

        ttk.Label(top, text="Auto-stop after idle (min, 0=never):").pack(side="left")
        self.idle_stop_var = tk.StringVar(value=str(self.config_data.get("idle_auto_stop_minutes", 0)))
        idle_spin = ttk.Spinbox(
            top, from_=0, to=1440, width=5, textvariable=self.idle_stop_var,
            command=self._save_idle_stop,
        )
        idle_spin.pack(side="left", padx=(4, 20))
        idle_spin.bind("<FocusOut>", lambda e: self._save_idle_stop())

        self.start_stop_btn = ttk.Button(top, text="Start Monitoring", command=self._toggle_monitor)
        self.start_stop_btn.pack(side="left")

        self.apply_changes_btn = ttk.Button(top, text="Apply Changes", command=self._apply_changes)
        self.apply_changes_btn.pack(side="left", padx=(6, 0))

        self.status_label = ttk.Label(top, text="Status: Idle", foreground="#555555")
        self.status_label.pack(side="left", padx=16)

        
        startup_frame = ttk.LabelFrame(self, text="Startup Options", padding=(10, 6))
        startup_frame.pack(fill="x", padx=10, pady=(0, 6))

        self.auto_monitor_var = tk.BooleanVar(value=self.config_data.get("auto_start_monitoring", False))
        ttk.Checkbutton(
            startup_frame, text="Auto-start monitoring on launch (no need to click Start)",
            variable=self.auto_monitor_var, command=self._save_auto_monitor,
        ).pack(anchor="w")

        ttk.Checkbutton(
            startup_frame,
            text="Show Activity Log in separate window",
            variable=self.show_log_window,
        ).pack(anchor="w")

        self.minimize_launch_var = tk.BooleanVar(value=self.config_data.get("start_minimized_to_tray", False))
        cb_text = "Minimize to tray immediately after launch"
        if not TRAY_AVAILABLE:
            cb_text += "  (unavailable -- install 'pystray' and 'pillow')"
        self.minimize_launch_cb = ttk.Checkbutton(
            startup_frame, text=cb_text, variable=self.minimize_launch_var,
            command=self._save_minimize_on_launch,
            state=("normal" if TRAY_AVAILABLE else "disabled"),
        )
        self.minimize_launch_cb.pack(anchor="w")

        self.start_with_windows_var = tk.BooleanVar(value=self.config_data.get("start_with_windows", False))
        cb_text2 = "Start with Windows (launch automatically at login)"
        if sys.platform != "win32":
            cb_text2 += "  (Windows only)"
        self.start_with_windows_cb = ttk.Checkbutton(
            startup_frame, text=cb_text2, variable=self.start_with_windows_var,
            command=self._save_start_with_windows,
            state=("normal" if sys.platform == "win32" else "disabled"),
        )
        self.start_with_windows_cb.pack(anchor="w")

        
        table_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        table_frame.pack(fill="both", expand=True)

        columns = ("info", "detail")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Process / Variant")
        self.tree.heading("info", text="On")
        self.tree.heading("detail", text="Client ID / Weight")
        self.tree.column("#0", width=280)
        self.tree.column("info", width=50, anchor="center")
        self.tree.column("detail", width=260)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._edit_selected())
        self.tree.bind("<Control-d>", lambda e: self._copy_selected())

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="left", fill="y")

        btn_col = ttk.Frame(table_frame, padding=(10, 0, 0, 0))
        btn_col.pack(side="left", fill="y")
        ttk.Label(btn_col, text="Groups", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Button(btn_col, text="Add Group", command=self._add_group).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Edit Group", command=self._edit_group).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Copy Group", command=self._copy_group).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Toggle Group On/Off", command=self._toggle_group_enabled).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Delete Group", command=self._delete_group).pack(fill="x", pady=2)
        ttk.Separator(btn_col, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(btn_col, text="Variants", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Button(btn_col, text="Add Variant", command=self._add_variant).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Edit Variant", command=self._edit_variant).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Copy Variant", command=self._copy_variant).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Toggle Variant On/Off", command=self._toggle_variant_enabled).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Delete Variant", command=self._delete_variant).pack(fill="x", pady=2)
        ttk.Separator(btn_col, orient="horizontal").pack(fill="x", pady=8)
        ttk.Button(btn_col, text="Custom Templates...", command=self._open_custom_templates).pack(fill="x", pady=2)
        ttk.Separator(btn_col, orient="horizontal").pack(fill="x", pady=8)
        ttk.Button(btn_col, text="Open config folder", command=self._open_config_folder).pack(fill="x", pady=2)
        if TRAY_AVAILABLE:
            ttk.Button(btn_col, text="Minimize to Tray", command=self._minimize_to_tray).pack(fill="x", pady=2)

        hint = (
            "Tip: add several Variants under one Group (same process name) to have\n"
            "a different Rich Presence chosen at random each time that process starts."
        )
        ttk.Label(self, text=hint, foreground="#888888", font=("Segoe UI", 8), justify="left").pack(
            anchor="w", padx=10, pady=(0, 4)
        )

        

    
    def _refresh_group_tree(self):
        open_groups = {
            iid for iid in self.tree.get_children("")
            if self.tree.item(iid, "open")
        } if self.tree.get_children("") else set()

        self.tree.delete(*self.tree.get_children())
        for gi, group in enumerate(self.config_data["groups"]):
            gid = f"g{gi}"
            variants = group.get("variants", [])
            mode = f"{len(variants)} variant{'s' if len(variants) != 1 else ''}"
            if len(variants) > 1:
                mode += " (random)"
            if group.get("cdp_watch"):
                mode += "  |  live data"
            self.tree.insert(
                "", "end", iid=gid, text=group.get("process_name", "(no process name)"),
                values=("Yes" if group.get("enabled") else "No", mode),
                open=(gid in open_groups) if open_groups else True,
            )
            for vi, variant in enumerate(variants):
                vid = f"g{gi}v{vi}"
                detail = variant.get("client_id") or "(no Client ID)"
                if len(variants) > 1:
                    detail += f"  |  weight {variant.get('weight', 1)}"
                if int(variant.get("party_max", 0) or 0) > 0:
                    detail += "  |  party"
                if variant.get("button1_label") or variant.get("button2_label"):
                    detail += "  |  buttons"
                self.tree.insert(
                    gid, "end", iid=vid, text="   " + variant.get("app_name", "Variant"),
                    values=("Yes" if variant.get("enabled", True) else "No", detail),
                )

    def _selected_ids(self):
        """Returns (group_index, variant_index_or_None) for the current
        selection, or (None, None) if nothing is selected."""
        sel = self.tree.selection()
        if not sel:
            return None, None
        iid = sel[0]
        if "v" in iid:
            g_part, v_part = iid[1:].split("v")
            return int(g_part), int(v_part)
        return int(iid[1:]), None

    def _copy_selected(self):
        gi, vi = self._selected_ids()
        if gi is None:
            return
        if vi is None:
            self._copy_group()
        else:
            self._copy_variant()

    def _edit_selected(self):
        gi, vi = self._selected_ids()
        if gi is None:
            return
        if vi is None:
            self._edit_group()
        else:
            self._edit_variant()

    
    def _add_group(self):
        dlg = GroupDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            new_group = _normalize_group(dlg.result)
            self.config_data["groups"].append(new_group)
            self._save_config()
            self._refresh_group_tree()

    def _copy_group(self):
        gi, _ = self._selected_ids()
        if gi is None:
            messagebox.showinfo(APP_TITLE, "Select a group first.")
            return

        source = self.config_data["groups"][gi]
        new_group = copy.deepcopy(source)

        
        
        new_group["enabled"] = False
        self.config_data["groups"].insert(gi + 1, new_group)
        new_index = gi + 1

        self._save_config()
        self._refresh_group_tree()
        gid = f"g{new_index}"
        if self.tree.exists(gid):
            self.tree.selection_set(gid)
            self.tree.focus(gid)
            self.tree.see(gid)

    def _edit_group(self):
        gi, _ = self._selected_ids()
        if gi is None:
            messagebox.showinfo(APP_TITLE, "Select a group first.")
            return
        group = self.config_data["groups"][gi]
        dlg = GroupDialog(self, group=group)
        self.wait_window(dlg)
        if dlg.result:
            group["process_name"] = dlg.result["process_name"]
            group["enabled"] = dlg.result["enabled"]
            group["cdp_watch"] = dlg.result["cdp_watch"]
            group["cdp_port"] = dlg.result["cdp_port"]
            group["widget_v2_enabled"] = dlg.result["widget_v2_enabled"]
            group["widget_v2_app_id"] = dlg.result["widget_v2_app_id"]
            group["widget_v2_user_id"] = dlg.result["widget_v2_user_id"]
            group["widget_v2_bot_token"] = dlg.result["widget_v2_bot_token"]
            group["widget_v2_field_name"] = dlg.result["widget_v2_field_name"]
            group["widget_v2_value_template"] = dlg.result["widget_v2_value_template"]
            self._save_config()
            self._refresh_group_tree()

    def _toggle_group_enabled(self):
        gi, _ = self._selected_ids()
        if gi is None:
            messagebox.showinfo(APP_TITLE, "Select a group first.")
            return
        group = self.config_data["groups"][gi]
        group["enabled"] = not group.get("enabled", True)
        self._save_config()
        self._refresh_group_tree()

    def _delete_group(self):
        gi, _ = self._selected_ids()
        if gi is None:
            messagebox.showinfo(APP_TITLE, "Select a group first.")
            return
        group = self.config_data["groups"][gi]
        if messagebox.askyesno(
            APP_TITLE, f"Delete group '{group.get('process_name')}' and all its variants?"
        ):
            del self.config_data["groups"][gi]
            self._save_config()
            self._refresh_group_tree()

    
    def _add_variant(self):
        gi, vi = self._selected_ids()
        if gi is None:
            messagebox.showinfo(APP_TITLE, "Select a group first (click on the process row).")
            return
        existing_ids = [
            v.get("client_id") for v in self.config_data["groups"][gi]["variants"] if v.get("client_id")
        ]
        dlg = VariantDialog(self, sibling_client_ids=existing_ids)
        self.wait_window(dlg)
        if dlg.result:
            self.config_data["groups"][gi]["variants"].append(_normalize_variant(dlg.result))
            self._save_config()
            self._refresh_group_tree()

    def _copy_variant(self):
        gi, vi = self._selected_ids()
        if gi is None or vi is None:
            messagebox.showinfo(APP_TITLE, "Select a variant first.")
            return

        group = self.config_data["groups"][gi]
        source = group["variants"][vi]
        new_variant = copy.deepcopy(source)

        
        
        base_name = new_variant.get("app_name") or "Variant"
        new_variant["app_name"] = f"{base_name} (Copy)"
        group["variants"].insert(vi + 1, new_variant)
        new_index = vi + 1

        self._save_config()
        self._refresh_group_tree()
        vid = f"g{gi}v{new_index}"
        if self.tree.exists(vid):
            self.tree.selection_set(vid)
            self.tree.focus(vid)
            self.tree.see(vid)

    def _edit_variant(self):
        gi, vi = self._selected_ids()
        if gi is None or vi is None:
            messagebox.showinfo(APP_TITLE, "Select a variant first.")
            return
        variant = self.config_data["groups"][gi]["variants"][vi]
        existing_ids = [
            v.get("client_id") for i, v in enumerate(self.config_data["groups"][gi]["variants"])
            if i != vi and v.get("client_id")
        ]
        dlg = VariantDialog(self, variant=variant, sibling_client_ids=existing_ids)
        self.wait_window(dlg)
        if dlg.result:
            self.config_data["groups"][gi]["variants"][vi] = _normalize_variant(dlg.result)
            self._save_config()
            self._refresh_group_tree()

    def _toggle_variant_enabled(self):
        gi, vi = self._selected_ids()
        if gi is None or vi is None:
            messagebox.showinfo(APP_TITLE, "Select a variant first.")
            return
        variant = self.config_data["groups"][gi]["variants"][vi]
        variant["enabled"] = not variant.get("enabled", True)
        self._save_config()
        self._refresh_group_tree()

    def _delete_variant(self):
        gi, vi = self._selected_ids()
        if gi is None or vi is None:
            messagebox.showinfo(APP_TITLE, "Select a variant first.")
            return
        group = self.config_data["groups"][gi]
        if len(group["variants"]) <= 1:
            messagebox.showwarning(
                APP_TITLE, "A group needs at least one variant. Delete the whole group instead."
            )
            return
        variant = group["variants"][vi]
        if messagebox.askyesno(APP_TITLE, f"Delete variant '{variant.get('app_name')}'?"):
            del group["variants"][vi]
            self._save_config()
            self._refresh_group_tree()

    def _open_custom_templates(self):
        templates = self.config_data.get("custom_templates", {})
        if not isinstance(templates, dict):
            templates = {}

        dlg = CustomTemplatesDialog(self, templates=templates)
        self.wait_window(dlg)
        if dlg.result is None:
            return

        self.config_data["custom_templates"] = dlg.result
        try:
            self._save_config()
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not save custom templates: {e}")
            return
        self._append_log("Saved custom templates.")


    def _open_config_folder(self):
        folder = get_data_dir()
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not open folder: {e}")

    def _open_log_window(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.deiconify()
            self.log_window.lift()
            self.log_window.focus_force()
            return

        self.log_window = tk.Toplevel(self)
        self.log_window.title("Activity Log")
        self.log_window.geometry("700x350")
        self.log_window.minsize(500, 200)

        self.log_text = tk.Text(
            self.log_window,
            state="disabled",
            wrap="word",
        )

        self.log_text.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=8,
        )

        self.log_window.protocol(
            "WM_DELETE_WINDOW",
            self._close_log_window,
        )


    def _close_log_window(self):
        if self.log_window is not None:
            self.log_window.destroy()

        self.log_window = None
        self.log_text = None
    

    def _save_interval(self):
        try:
            val = int(self.interval_var.get())
        except ValueError:
            val = DEFAULT_INTERVAL
        self.config_data["check_interval_seconds"] = val
        self._save_config()

    def _save_idle_stop(self):
        try:
            val = max(0, int(self.idle_stop_var.get()))
        except ValueError:
            val = 0
        self.idle_stop_var.set(str(val))
        self.config_data["idle_auto_stop_minutes"] = val
        self._save_config()

    def _get_idle_stop_minutes(self):
        try:
            return int(self.idle_stop_var.get())
        except ValueError:
            return 0

    def _save_auto_monitor(self):
        self.config_data["auto_start_monitoring"] = self.auto_monitor_var.get()
        self._save_config()

    def _save_minimize_on_launch(self):
        self.config_data["start_minimized_to_tray"] = self.minimize_launch_var.get()
        self._save_config()

    def _save_start_with_windows(self):
        enabled = self.start_with_windows_var.get()
        try:
            set_start_with_windows(enabled)
            self.config_data["start_with_windows"] = enabled
            self._save_config()
            if enabled:
                self._append_log("Registered to start automatically with Windows.")
            else:
                self._append_log("Removed from Windows startup.")
        except RuntimeError as e:
            
            self.start_with_windows_var.set(not enabled)
            messagebox.showerror(APP_TITLE, str(e))

    
    def _get_groups(self):
        return self.config_data["groups"]

    def _get_interval(self):
        try:
            return int(self.interval_var.get())
        except ValueError:
            return DEFAULT_INTERVAL

    def _get_custom_templates(self):
        templates = self.config_data.get("custom_templates", {})
        return templates if isinstance(templates, dict) else {}

    def _get_stage_template_defaults(self):
        templates = self.config_data.get("stage_template_defaults", {})
        return templates if isinstance(templates, dict) else {}

    def _toggle_monitor(self):
        if self.monitor and self.monitor.is_alive():
            self._append_log("Stopping monitor...")
            self.monitor.stop()
            self.monitor.join(timeout=2)
            self.monitor = None
            self.start_stop_btn.config(text="Start Monitoring")
            self.status_label.config(text="Status: Idle")
        else:
            if not any(g.get("enabled") for g in self.config_data["groups"]):
                messagebox.showwarning(
                    APP_TITLE, "Add and enable at least one group before starting."
                )
                return
            self.monitor = RPCMonitor(
                self._get_groups, self._get_interval, self.log_queue, self.status_queue,
                self._get_idle_stop_minutes, self._get_custom_templates,
                self._get_stage_template_defaults,
            )
            self.monitor.start()
            self.start_stop_btn.config(text="Stop Monitoring")

    def _apply_changes(self):
        try:
            self._save_config()
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not save config: {e}")
            return

        self._append_log(f"Saved to {self.active_config_path}")

        if not (self.monitor and self.monitor.is_alive()):
            self._append_log("Changes saved. Monitoring is not running, so no restart was needed.")
            return

        self._append_log("Applying changes: restarting monitor...")
        self.monitor.stop()
        self.monitor.join(timeout=2)

        if self.monitor.is_alive():
            self._append_log(
                "Could not stop the current monitor within 2 seconds. "
                "Changes were saved but were not applied yet."
            )
            return

        self.monitor = None
        self.start_stop_btn.config(text="Start Monitoring")
        self.status_label.config(text="Status: Idle")

        if not any(g.get("enabled") for g in self.config_data["groups"]):
            self._append_log(
                "Changes saved. No groups are enabled, so monitoring remains stopped."
            )
            return

        self.monitor = RPCMonitor(
            self._get_groups, self._get_interval, self.log_queue, self.status_queue,
            self._get_idle_stop_minutes, self._get_custom_templates,
            self._get_stage_template_defaults,
        )
        self.monitor.start()
        self.start_stop_btn.config(text="Stop Monitoring")
        self._append_log("Changes applied; monitor restarted with the new settings.")


    def _poll_queues(self):
        for _ in range(50):
            try:
                command, done, box = self.web_command_queue.get_nowait()
            except queue.Empty:
                break
            try:
                box["result"] = command()
            except Exception as e:
                box["error"] = e
            finally:
                done.set()

        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.web_log_buffer.append(msg)
                if len(self.web_log_buffer) > 500:
                    del self.web_log_buffer[:-500]
                self._append_log(msg)
        except queue.Empty:
            pass
        try:
            while True:
                status = self.status_queue.get_nowait()
                self._web_status_text = status
                self.status_label.config(text=f"Status: {status}")
        except queue.Empty:
            pass
        if self.monitor is not None and not self.monitor.is_alive():
            self.monitor = None
            self.start_stop_btn.config(text="Start Monitoring")
        self.after(300, self._poll_queues)

    def _append_log(self, msg):
        if not self.show_log_window.get():
            return

        if self.log_window is None or not self.log_window.winfo_exists():
            self._open_log_window()

        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    
    def _make_tray_image(self):
        img = Image.new("RGB", (64, 64), color="#5865F2")
        d = ImageDraw.Draw(img)
        d.ellipse((14, 14, 50, 50), fill="white")
        return img

    def _minimize_to_tray(self):
        if not TRAY_AVAILABLE:
            messagebox.showinfo(
                APP_TITLE,
                "System tray support requires the 'pystray' and 'pillow' packages.",
            )
            return
        self.withdraw()
        if self.tray_icon is None:
            menu = pystray.Menu(
                pystray.MenuItem("Show", self._restore_from_tray, default=True),
                pystray.MenuItem(
                    "Start/Stop Monitoring", lambda: self.after(0, self._toggle_monitor)
                ),
                pystray.MenuItem("Quit", lambda: self.after(0, self._quit_app)),
            )
            self.tray_icon = pystray.Icon(APP_TITLE, self._make_tray_image(), APP_TITLE, menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _restore_from_tray(self, icon=None, item=None):
        self.after(0, self.deiconify)

    def _on_close_button(self):
        if TRAY_AVAILABLE:
            if messagebox.askyesno(
                APP_TITLE, "Minimize to system tray instead of quitting?"
            ):
                self._minimize_to_tray()
                return
        self._quit_app()

    def _quit_app(self):
        if self.monitor and self.monitor.is_alive():
            self.monitor.stop()
            self.monitor.join(timeout=2)
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        close_event = getattr(self, "webview_close_event", None)
        if close_event is not None:
            close_event.set()
        self.destroy()
        sys.exit(0)

