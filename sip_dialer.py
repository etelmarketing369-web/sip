#!/usr/bin/env python3
"""
SIP Dialer GUI Application
Main GUI interface for the Windows Desktop SIP Dialer
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import queue
import time
from datetime import datetime
from typing import Dict, List, Optional
import sys
import os
import platform
import ctypes
import subprocess
import shutil
import re
import numpy as np
import sounddevice as sd
import json
from pathlib import Path

from config_manager import ConfigManager
from account_audio_manager import AccountAudioManager
from android_installer import AndroidInstaller, install_android_async

# Import speech recognition components
try:
    import vosk
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    print("Warning: Vosk not available. Speech recognition disabled.")

try:
    from enhanced_sip_manager import EnhancedSipManager as SipManager
    print("Using Enhanced SIP Manager with RTP media support")
except ImportError:
    try:
        from working_sip_manager import WorkingSipManager as SipManager
        print("Using Working SIP Manager")
    except ImportError:
        try:
            from sip_manager import SipManager
            print("Using PJSIP Manager") 
        except ImportError:
            print("PJSIP not available, using mock SIP manager for testing")
            from mock_sip_manager import MockSipManager as SipManager

class SipDialerApp:
    """Main SIP Dialer Application GUI"""
    
    def __init__(self, root):
        self.root = root
        self.config_manager = ConfigManager()
        self.sip_manager = SipManager()
        # Android installer for SDK and emulator setup
        self.android_installer = AndroidInstaller()
        # Thread-safe queue for UI updates coming from background threads
        self._ui_queue = queue.Queue()
        # Track emulator toggle buttons per account
        self._emu_buttons = {}
        # Track emulator status labels per account
        self._emu_status_labels = {}
        # WhatsApp state labels per account
        self._wa_status_labels = {}
        # Track call routing buttons per account (WhatsApp/Desktop)
        self._call_routing_buttons = {}
        # Track call routing state per account (True=WhatsApp, False=Desktop)
        self._call_routing_state = {}
        # Lightweight timer tick for periodic UI refreshes
        self._timer_tick = 0

        # Per-account audio worker manager (separate process per account)
        self.account_audio_manager = AccountAudioManager()
        print("Windows Volume Mixer integration initialized")

        # GUI state - simplified to only account status
        self.account_status_labels = {}
        self.account_status_frames = {}
        # Volume Mixer sessions are handled by per-account workers only (no in-process sessions)
        # Track call->account to manage worker lifecycle during calls
        self.account_status_frames = {}
        self._call_to_account = {}
        # Deferred incoming calls waiting for WhatsApp notification to answer
        self._deferred_calls = {}
        self._notification_thread = None
        self.sip_manager.on_incoming_call = self._on_incoming_call
        self.sip_manager.on_call_state_changed = self._on_call_state_changed

        # Speech recognition for auto-answer
        self._init_speech_recognition()
        self._speech_recognition_active = {}  # Track active recognition per call
        self._speech_audio_streams = {}  # Track audio streams per call

        # Initialize GUI
        self._setup_gui()
        self._initialize_sip()

        # Start status update timer
        self._start_status_timer()

        # Proactively start per-account audio workers so each account shows in Volume Mixer
        # even before SIP registration (user requested device entries per account always visible)
        try:
            self._start_all_audio_workers()
        except Exception as e:
            print(f"[WARN]  Failed to start all audio workers on startup: {e}")

        # Auto-register SIP accounts on startup (non-blocking)
        try:
            self._auto_register_accounts_on_startup()
        except Exception as e:
            print(f"[WARN]  Failed to start auto-registration: {e}")
        # Start notification watcher for deferred answering
        try:
            self._start_notification_watcher()
        except Exception as e:
            print(f"[WARN]  Failed to start notification watcher: {e}")
        # Start live registration status refresh (real-time)
        self._start_registration_live_update()
        
        # Auto-configure AVD if needed (for existing installations)
        try:
            self._auto_configure_avd_if_needed()
        except Exception as e:
            print(f"[WARN]  Failed to auto-configure AVD: {e}")

    def _start_all_audio_workers(self):
        """Start an audio worker process for each configured account (idempotent)."""
        started = 0
        # Get accounts from config instead of hardcoded range
        accounts = self.config_manager.config.get("accounts", {})
        account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])
        total_accounts = len(account_ids)
        
        for account_id in account_ids:
            try:
                cfg = self.config_manager.get_account_config(account_id) or {}
                username = cfg.get('username') or self._default_username(account_id)
                result = self.account_audio_manager.start_for_account(account_id, username)
                if result is not False:
                    started += 1
            except Exception as e:
                print(f"[WARN]  Could not start audio worker for account {account_id}: {e}")
        print(f"[MIXER]  Audio workers started: {started}/{total_accounts}")

    def _default_username(self, account_id: int) -> str:
        """Return the default username for a SIP account."""
        defaults = {
            1: "JEFF01",
            2: "JEFF0"
        }
        return defaults.get(account_id, f"Account{account_id}")
    
    def _setup_gui(self):
        """Setup the main GUI interface"""
        # Configure main window
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Create main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create only the account status tab - calls and settings removed per request
        self._create_status_tab()  # Only tab to show account status
        
        # Create Volume Mixer control tab
        self._create_volume_mixer_tab()
        
        # Create status bar
        self._create_status_bar()
    
    def _create_status_tab(self):
        """Create the SIP accounts status tab (read-only)"""
        status_frame = ttk.Frame(self.notebook)
        self.notebook.add(status_frame, text="Account Status")

        # Configure grid
        status_frame.grid_rowconfigure(1, weight=1)  # Changed from row=0 to row=1
        status_frame.grid_columnconfigure(0, weight=1)

        # Add Android SDK installation section at top
        self._create_android_install_section(status_frame)

        # Scrollable container for account cards
        scroll_host, scroll_inner = self._create_scrollable_area(status_frame)
        scroll_host.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)  # Changed from row=0 to row=1

        # Configure inner grid (2 columns)
        for i in range(2):
            scroll_inner.grid_columnconfigure(i, weight=1)

        # Create status frames (2 columns, dynamic rows based on config) inside scrollable area
        self.account_status_frames = {}
        # Get accounts from config instead of hardcoded range
        accounts = self.config_manager.config.get("accounts", {})
        account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])
        
        for i, account_id in enumerate(account_ids):
            row = i // 2
            col = i % 2
            frame = self._create_status_frame(scroll_inner, account_id)
            frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            self.account_status_frames[account_id] = frame

        # Add bottom padding filler to ensure last row fully scrolls into view
        filler = ttk.Frame(scroll_inner)
        filler.grid(row=10, column=0, columnspan=2, pady=(0, 5))
        
    def _create_volume_mixer_tab(self):
        """Create Volume Mixer control tab"""
        mixer_frame = ttk.Frame(self.notebook)
        self.notebook.add(mixer_frame, text="[MIXER] Volume Mixer")

        # Configure grid
        mixer_frame.grid_rowconfigure(2, weight=1)
        mixer_frame.grid_columnconfigure(0, weight=1)

        # Title
        title_frame = ttk.Frame(mixer_frame)
        title_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        title_label = tk.Label(title_frame, 
                              text="[MIXER] Windows Volume Mixer Integration",
                              font=("Arial", 14, "bold"))
        title_label.pack()
        
        # Instructions
        info_frame = ttk.LabelFrame(mixer_frame, text="What to Look For", padding=10)
        info_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        info_text = tk.Label(
            info_frame,
            text="Each SIP account appears in Windows Volume Mixer with these names:\n\n"
                 "* SIP Account 1 (JEFF01)\n"
                 "* SIP Account 2 (JEFF0)",
            font=("Arial", 10),
            justify="left"
        )
        info_text.pack()
        
        # Control buttons
        button_frame = ttk.Frame(mixer_frame)
        button_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        # Start all button
        start_btn = tk.Button(button_frame, 
                             text="[PLAY] Start All Audio Workers",
                             font=("Arial", 11, "bold"),
                             bg="#4CAF50",
                             fg="white",
                             command=self._start_all_audio_workers_manual)
        start_btn.pack(side="left", padx=(0, 10))
        
        # Stop all button  
        stop_btn = tk.Button(button_frame, 
                            text="[STOP] Stop All Audio Workers",
                            font=("Arial", 11),
                            bg="#f44336",
                            fg="white",
                            command=self._stop_all_audio_workers)
        stop_btn.pack(side="left", padx=(0, 10))
        
        # Check status button
        check_btn = tk.Button(button_frame, 
                             text="[CHECK] Check Volume Mixer",
                             font=("Arial", 11),
                             bg="#2196F3",
                             fg="white",
                             command=self._check_volume_mixer_status)
        check_btn.pack(side="left", padx=(0, 10))
        
        # Open Volume Mixer button
        open_mixer_btn = tk.Button(button_frame, 
                                  text="[AUDIO] Open Volume Mixer",
                                  font=("Arial", 11),
                                  bg="#FF9800",
                                  fg="white",
                                  command=self._open_volume_mixer)
        open_mixer_btn.pack(side="left")
        
        # Status display
        status_frame = ttk.LabelFrame(mixer_frame, text="Status", padding=10)
        status_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        self.mixer_status_text = tk.Text(status_frame, height=8, width=60)
        scrollbar = ttk.Scrollbar(status_frame, orient="vertical", command=self.mixer_status_text.yview)
        self.mixer_status_text.configure(yscrollcommand=scrollbar.set)
        
        self.mixer_status_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _create_scrollable_area(self, parent):
        """Create a vertically scrollable area using Canvas + Scrollbar.
        Returns (host_frame, inner_content_frame).
        """
        host = ttk.Frame(parent)
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)

        # Canvas for scrolling
        canvas = tk.Canvas(host, highlightthickness=0)
        vscroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")

        # Inner frame inside the canvas
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(event=None):
            # Update scroll region to match inner content
            canvas.configure(scrollregion=canvas.bbox("all"))
            # If inner is narrower than canvas, expand to fit width
            try:
                canvas_width = canvas.winfo_width()
                canvas.itemconfigure(inner_id, width=canvas_width)
            except Exception:
                pass

        def _on_canvas_configure(event=None):
            # Ensure inner frame width tracks canvas width
            try:
                canvas.itemconfigure(inner_id, width=event.width)
            except Exception:
                pass

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse wheel scrolling (Windows)
        def _on_mousewheel(event):
            try:
                # event.delta is positive/negative multiple of 120 on Windows
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
            return "break"

        # Bind wheel to canvas and inner content
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        return host, inner
    
    def _create_status_frame(self, parent, account_id):
        """Create a status frame for a single SIP account"""
        # Main frame with border
        main_frame = ttk.LabelFrame(parent, text=f"Account {account_id}")

        # Get account config
        account_config = self.config_manager.get_account_config(account_id) or {}

        # Username input field
        username_frame = ttk.Frame(main_frame)
        username_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        username_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(username_frame, text="Username:").grid(row=0, column=0, sticky="w", pady=2)
        username_var = tk.StringVar(value=account_config.get("username", f"1{account_id:03d}"))
        username_entry = ttk.Entry(username_frame, textvariable=username_var, width=15)
        username_entry.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=2)

        # Emulator mapping display
        emulator_port = self.config_manager.get_account_emulator_port(account_id)
        emulator_label = ttk.Label(main_frame, text=f"Emulator: {emulator_port}")
        emulator_label.grid(row=1, column=0, sticky="w", padx=5)

        # Emulator toggle + status
        emu_btns = ttk.Frame(main_frame)
        emu_btns.grid(row=2, column=0, pady=4)
        emu_toggle = ttk.Button(
            emu_btns,
            text="Open Emulator",
            width=18,
            command=lambda aid=account_id: self._toggle_emulator_for_account(aid),
        )
        emu_toggle.grid(row=0, column=0, padx=3)
        emu_status = ttk.Label(emu_btns, text="Stopped", foreground="red")
        emu_status.grid(row=0, column=1, padx=6)
        self._emu_buttons[account_id] = emu_toggle
        self._emu_status_labels[account_id] = emu_status

        # Control buttons
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=3, column=0, pady=5)

        # Start/Stop (registration toggle)
        register_btn = ttk.Button(
            buttons_frame,
            text="Start",
            width=12,
            command=lambda aid=account_id: self._toggle_account_registration(aid),
        )
        register_btn.grid(row=0, column=0, padx=2)

        # Call routing button (WhatsApp/Desktop toggle)
        call_routing_btn = ttk.Button(
            buttons_frame,
            text="Windows WhatsApp",
            width=14,
            command=lambda aid=account_id: self._toggle_call_routing(aid),
        )
        call_routing_btn.grid(row=0, column=1, padx=2)
        
        # Initialize call routing state (True=Emulator WhatsApp, False=Windows WhatsApp + Speech Recognition)
        self._call_routing_state[account_id] = False  # Default to Windows WhatsApp for speech recognition
        self._call_routing_buttons[account_id] = call_routing_btn

        # Status label
        status_label = ttk.Label(main_frame, text="Not Registered", foreground="red")
        status_label.grid(row=4, column=0, pady=2)
        self.account_status_labels[account_id] = status_label

        # WhatsApp call status (row 4.5 effectively)
        wa_status = ttk.Label(main_frame, text="WA: IDLE", foreground="#555555")
        wa_status.grid(row=4, column=1, padx=4, sticky="e")
        self._wa_status_labels[account_id] = wa_status

        # WhatsApp tap settings (Step 1 + Delay + optional Step 2 and Step 3)
        try:
            step1_x_default = int(account_config.get("whatsapp_step1_x", account_config.get("whatsapp_tap_x", 230)))
            step1_y_default = int(account_config.get("whatsapp_step1_y", account_config.get("whatsapp_tap_y", 130)))
        except Exception:
            step1_x_default, step1_y_default = 230, 130
        try:
            step_delay_default = int(account_config.get("whatsapp_step_delay_ms", 800))
        except Exception:
            step_delay_default = 800
        # Step 2/3 can be blank to skip
        step2_x_cfg = account_config.get("whatsapp_step2_x", "")
        step2_y_cfg = account_config.get("whatsapp_step2_y", "")
        step2_x_default = ("" if str(step2_x_cfg).strip() == "" else str(int(step2_x_cfg)))
        step2_y_default = ("" if str(step2_y_cfg).strip() == "" else str(int(step2_y_cfg)))
        step3_x_cfg = account_config.get("whatsapp_step3_x", "")
        step3_y_cfg = account_config.get("whatsapp_step3_y", "")
        step3_x_default = ("" if str(step3_x_cfg).strip() == "" else str(int(step3_x_cfg)))
        step3_y_default = ("" if str(step3_y_cfg).strip() == "" else str(int(step3_y_cfg)))
        # Optional Step 3 delay (falls back to Step 2 delay if blank)
        try:
            step3_delay_default = account_config.get("whatsapp_step3_delay_ms", "")
            if str(step3_delay_default).strip() != "":
                step3_delay_default = int(step3_delay_default)
            else:
                step3_delay_default = ""
        except Exception:
            step3_delay_default = ""

        # Chat page verification delay (new field)
        try:
            chat_verify_delay = int(account_config.get("whatsapp_chat_verify_delay_ms", 3000))
        except Exception:
            chat_verify_delay = 3000

        wa_frame = ttk.Frame(main_frame)
        wa_frame.grid(row=5, column=0, sticky="ew", padx=5, pady=(6, 2))
        wa_frame.grid_columnconfigure(10, weight=1)
        # Row 0: Step 1 + Delay + Step 2
        ttk.Label(wa_frame, text="Step 1:").grid(row=0, column=0, sticky="w")
        ttk.Label(wa_frame, text="X").grid(row=0, column=1)
        s1x_var = tk.StringVar(value=str(step1_x_default))
        ttk.Entry(wa_frame, textvariable=s1x_var, width=6).grid(row=0, column=2, padx=(2, 6))
        ttk.Label(wa_frame, text="Y").grid(row=0, column=3)
        s1y_var = tk.StringVar(value=str(step1_y_default))
        ttk.Entry(wa_frame, textvariable=s1y_var, width=6).grid(row=0, column=4, padx=(2, 8))
        ttk.Label(wa_frame, text="Delay(ms)").grid(row=0, column=5)
        sdelay_var = tk.StringVar(value=str(step_delay_default))
        ttk.Entry(wa_frame, textvariable=sdelay_var, width=7).grid(row=0, column=6, padx=(2, 8), sticky="w")
        ttk.Label(wa_frame, text="Step 2:").grid(row=0, column=7)
        ttk.Label(wa_frame, text="X").grid(row=0, column=8)
        s2x_var = tk.StringVar(value=step2_x_default)
        ttk.Entry(wa_frame, textvariable=s2x_var, width=6).grid(row=0, column=9, padx=(2, 6))
        ttk.Label(wa_frame, text="Y").grid(row=0, column=10)
        s2y_var = tk.StringVar(value=step2_y_default)
        ttk.Entry(wa_frame, textvariable=s2y_var, width=6).grid(row=0, column=11, padx=(2, 8))

        # Row 1: Step 3 + optional delay
        ttk.Label(wa_frame, text="Step 3:").grid(row=1, column=0, sticky="w")
        ttk.Label(wa_frame, text="X").grid(row=1, column=1)
        s3x_var = tk.StringVar(value=step3_x_default)
        ttk.Entry(wa_frame, textvariable=s3x_var, width=6).grid(row=1, column=2, padx=(2, 6))
        ttk.Label(wa_frame, text="Y").grid(row=1, column=3)
        s3y_var = tk.StringVar(value=step3_y_default)
        ttk.Entry(wa_frame, textvariable=s3y_var, width=6).grid(row=1, column=4, padx=(2, 8))
        ttk.Label(wa_frame, text="Delay(ms)").grid(row=1, column=5)
        s3delay_var = tk.StringVar(value=(str(step3_delay_default) if step3_delay_default != "" else ""))
        ttk.Entry(wa_frame, textvariable=s3delay_var, width=7).grid(row=1, column=6, padx=(2, 8), sticky="w")

        # Row 2: Delay Before Tapping (after chat opens, before tapping starts)
        try:
            tap_ready_delay = int(account_config.get("whatsapp_tap_ready_delay_ms", 2000))
        except Exception:
            tap_ready_delay = 2000
            
        ttk.Label(wa_frame, text="Delay Before Tapping:").grid(row=2, column=0, sticky="w", columnspan=3)
        ttk.Label(wa_frame, text="ms").grid(row=2, column=3)
        tap_ready_var = tk.StringVar(value=str(tap_ready_delay))
        ttk.Entry(wa_frame, textvariable=tap_ready_var, width=7).grid(row=2, column=4, padx=(2, 8), sticky="w")

        def on_save_wa():
            try:
                s1x = int(s1x_var.get())
                s1y = int(s1y_var.get())
                sdelay = int(sdelay_var.get())
                # Step 2 may be blank
                s2x_text = s2x_var.get().strip()
                s2y_text = s2y_var.get().strip()
                s2x = ("" if s2x_text == "" else int(s2x_text))
                s2y = ("" if s2y_text == "" else int(s2y_text))
                # Step 3 may be blank
                s3x_text = s3x_var.get().strip()
                s3y_text = s3y_var.get().strip()
                s3x = ("" if s3x_text == "" else int(s3x_text))
                s3y = ("" if s3y_text == "" else int(s3y_text))
                # Step 3 delay may be blank (fallback to Step 2 delay)
                s3delay_text = s3delay_var.get().strip()
                s3delay = ("" if s3delay_text == "" else int(s3delay_text))
                # Delay before tapping (after chat page opens)
                tap_ready = int(tap_ready_var.get())
                self._save_whatsapp_tap_config(account_id, step1=(s1x, s1y), step_delay=sdelay, step2=(s2x, s2y), step3=(s3x, s3y), step3_delay=s3delay, tap_ready_delay=tap_ready)
            except Exception:
                messagebox.showerror("Error", "Enter valid integers for Step 1 and Delay; Step 2/3 can be blank or integers")

        def on_test_step1():
            try:
                s1x = int(s1x_var.get())
                s1y = int(s1y_var.get())
                self._test_whatsapp_tap(account_id, s1x, s1y)
            except Exception:
                messagebox.showerror("Error", "Enter valid integers for Step 1 X and Y")

        def on_test_step2():
            try:
                s2x_text = s2x_var.get().strip()
                s2y_text = s2y_var.get().strip()
                if not s2x_text or not s2y_text:
                    messagebox.showwarning("Test Step 2", "Step 2 is empty; fill X and Y to test")
                    return
                s2x = int(s2x_text)
                s2y = int(s2y_text)
                self._test_whatsapp_tap(account_id, s2x, s2y)
            except Exception:
                messagebox.showerror("Error", "Enter valid integers for Step 2 X and Y")

        def on_test_step3():
            try:
                s3x_text = s3x_var.get().strip()
                s3y_text = s3y_var.get().strip()
                if not s3x_text or not s3y_text:
                    messagebox.showwarning("Test Step 3", "Step 3 is empty; fill X and Y to test")
                    return
                s3x = int(s3x_text)
                s3y = int(s3y_text)
                self._test_whatsapp_tap(account_id, s3x, s3y)
            except Exception:
                messagebox.showerror("Error", "Enter valid integers for Step 3 X and Y")

        ttk.Button(wa_frame, text="Save", width=8, command=on_save_wa).grid(row=3, column=0, padx=(0, 6), pady=(4, 0), sticky="w")
        ttk.Button(wa_frame, text="Test Step 1", width=12, command=on_test_step1).grid(row=3, column=1, padx=(0, 4), pady=(4, 0), sticky="w")
        ttk.Button(wa_frame, text="Test Step 2", width=12, command=on_test_step2).grid(row=3, column=2, padx=(0, 4), pady=(4, 0), sticky="w")
        ttk.Button(wa_frame, text="Test Step 3", width=12, command=on_test_step3).grid(row=3, column=3, padx=(0, 4), pady=(4, 0), sticky="w")

        # Store references
        main_frame.register_btn = register_btn
        main_frame.username_var = username_var

        return main_frame

    # ----- Emulator helpers -----
    def _find_emulator_exe(self) -> Optional[str]:
        # Prefer PATH
        for name in ("emulator.exe", "emulator"):
            p = shutil.which(name)
            if p:
                return p
        # Common SDK locations
        candidates = []
        for env in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            root = os.environ.get(env)
            if root:
                candidates.append(os.path.join(root, "emulator", "emulator.exe"))
        local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "emulator", "emulator.exe")
        candidates.append(local)
        for p in candidates:
            if p and os.path.isfile(p):
                return p
        return None

    def _find_adb_exe(self) -> Optional[str]:
        for name in ("adb.exe", "adb"):
            p = shutil.which(name)
            if p:
                return p
        candidates = []
        for env in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            root = os.environ.get(env)
            if root:
                candidates.append(os.path.join(root, "platform-tools", "adb.exe"))
        local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe")
        candidates.append(local)
        for p in candidates:
            if p and os.path.isfile(p):
                return p
        return None

    def _list_avds(self, emulator_exe: str) -> List[str]:
        try:
            res = subprocess.run([emulator_exe, "-list-avds"], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            pass
        return []

    def _is_emulator_running(self, port: int) -> bool:
        adb = self._find_adb_exe()
        if not adb:
            return False
        try:
            res = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                target = f"emulator-{port}"
                return any(target in line for line in res.stdout.splitlines())
        except Exception:
            pass
        return False

    def _open_emulator_for_account(self, account_id: int):
        def worker():
            port = self.config_manager.get_account_emulator_port(account_id)
            if self._is_emulator_running(port):
                self._update_status(f"Emulator {port} already running")
                return
            emulator_exe = self._find_emulator_exe()
            if not emulator_exe:
                self._update_status("Emulator not found (install Android SDK or add to PATH)")
                return
            # Get preferred AVD name from config if provided
            cfg = self.config_manager.get_account_config(account_id) or {}
            avd = cfg.get("emulator_avd")
            if not avd:
                avds = self._list_avds(emulator_exe)
                if avds:
                    avd = avds[0]
            if not avd:
                self._update_status("No AVD configured/found; set 'emulator_avd' in config.json")
                return
            args = [
                emulator_exe,
                "-avd", avd,
                "-port", str(port),
                "-no-metrics",        # Prevent metrics dialog blocking
                #"-read-only",         # Allow multiple instances  
                "-no-snapshot",
                "-netdelay", "none",
                "-netspeed", "full",
                "-no-boot-anim",
                "-gpu", "host",       # Use host GPU for better performance
                "-memory", "2048",    # Allocate more memory per emulator for simultaneous use
                "-cores", "2"         # Use 2 CPU cores per emulator
            ]
            try:
                # Set proper environment variables for emulator
                env = os.environ.copy()
                android_sdk_path = os.path.dirname(os.path.dirname(emulator_exe))  # Go up two levels from emulator/emulator.exe
                env['ANDROID_SDK_ROOT'] = android_sdk_path
                env['ANDROID_HOME'] = android_sdk_path
                
                creationflags = 0
                if os.name == 'nt':
                    creationflags = subprocess.CREATE_NO_WINDOW
                subprocess.Popen(args, creationflags=creationflags, env=env)
                self._update_status(f"Launching emulator {avd} on port {port}...")
            except Exception as e:
                self._update_status(f"Failed to launch emulator: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _save_whatsapp_tap_config(self, account_id: int, step1: tuple[int, int], step_delay: int, step2: tuple[int | str, int | str], step3: tuple[int | str, int | str] | None = None, step3_delay: int | str | None = None, tap_ready_delay: int | None = None, chat_verify_delay: int | None = None):
        """Persist two-step WhatsApp tap settings for an account and update status.
        step2 can contain empty strings to clear.
        """
        try:
            s1x, s1y = int(step1[0]), int(step1[1])
            sdelay = int(step_delay)
            s2x_raw, s2y_raw = step2
            s3x_raw = s3y_raw = None
            if step3 is not None:
                s3x_raw, s3y_raw = step3
            update: dict = {
                "whatsapp_step1_x": s1x,
                "whatsapp_step1_y": s1y,
                "whatsapp_step_delay_ms": sdelay,
            }
            # Preserve single-tap config for backward compatibility (use step1 + initial settle)
            update["whatsapp_tap_x"] = s1x
            update["whatsapp_tap_y"] = s1y
            # Step 2 optional
            if isinstance(s2x_raw, str) and s2x_raw.strip() == "":
                update["whatsapp_step2_x"] = ""
            else:
                update["whatsapp_step2_x"] = int(s2x_raw)
            if isinstance(s2y_raw, str) and s2y_raw.strip() == "":
                update["whatsapp_step2_y"] = ""
            else:
                update["whatsapp_step2_y"] = int(s2y_raw)

            # Step 3 optional
            if s3x_raw is not None:
                if isinstance(s3x_raw, str) and s3x_raw.strip() == "":
                    update["whatsapp_step3_x"] = ""
                else:
                    update["whatsapp_step3_x"] = int(s3x_raw)
            if s3y_raw is not None:
                if isinstance(s3y_raw, str) and s3y_raw.strip() == "":
                    update["whatsapp_step3_y"] = ""
                else:
                    update["whatsapp_step3_y"] = int(s3y_raw)

            # Optional Step 3 delay
            if step3_delay is not None:
                if isinstance(step3_delay, str) and step3_delay.strip() == "":
                    update["whatsapp_step3_delay_ms"] = ""
                else:
                    update["whatsapp_step3_delay_ms"] = int(step3_delay)

            # Delay before tapping (after chat page opens)
            if tap_ready_delay is not None:
                update["whatsapp_tap_ready_delay_ms"] = int(tap_ready_delay)

            # Chat verification delay
            if chat_verify_delay is not None:
                update["whatsapp_chat_verify_delay_ms"] = int(chat_verify_delay)

            if self.config_manager.set_account_config(account_id, update):
                self.config_manager.save_config()
                s2x_disp = update.get("whatsapp_step2_x", "") if update.get("whatsapp_step2_x", "") != "" else "-"
                s2y_disp = update.get("whatsapp_step2_y", "") if update.get("whatsapp_step2_y", "") != "" else "-"
                s3x_disp = update.get("whatsapp_step3_x", "") if update.get("whatsapp_step3_x", "") != "" else "-"
                s3y_disp = update.get("whatsapp_step3_y", "") if update.get("whatsapp_step3_y", "") != "" else "-"
                s3delay_disp = update.get("whatsapp_step3_delay_ms", "") if update.get("whatsapp_step3_delay_ms", "") != "" else "(=Delay)"
                self._update_status(
                    f"Saved WA taps A{account_id}: Step1 {s1x},{s1y} | Delay {sdelay}ms | Step2 {s2x_disp},{s2y_disp} | Step3 {s3x_disp},{s3y_disp} (Delay {s3delay_disp})"
                )
            else:
                self._update_status("Failed to save WhatsApp settings")
        except Exception as e:
            self._update_status(f"Save error: {e}")

    def _test_whatsapp_tap(self, account_id: int, x: int, y: int):
        """Issue an adb tap to the mapped emulator for quick coordinate testing."""
        def worker():
            port = self.config_manager.get_account_emulator_port(account_id)
            target = f"emulator-{port}"
            adb = self._find_adb_exe()
            if not adb:
                self._update_status("adb not found (install Android SDK or add to PATH)")
                return
            if not self._is_emulator_running(port):
                self._update_status(f"Emulator {port} not running; open it first")
                return
            try:
                res = subprocess.run([adb, "-s", target, "shell", "input", "tap", str(int(x)), str(int(y))], capture_output=True, text=True, timeout=6)
                if res.returncode == 0:
                    self._update_status(f"Test tap sent to {target} at {x},{y}")
                else:
                    msg = res.stderr.strip() or res.stdout.strip() or "unknown error"
                    self._update_status(f"Test tap failed: {msg}")
            except Exception as e:
                self._update_status(f"Test tap error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _close_emulator_for_account(self, account_id: int):
        def worker():
            port = self.config_manager.get_account_emulator_port(account_id)
            adb = self._find_adb_exe()
            if not adb:
                self._update_status("adb not found (install Android SDK or add to PATH)")
                return
            target = f"emulator-{port}"
            try:
                res = subprocess.run([adb, "-s", target, "emu", "kill"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    self._update_status(f"Closed emulator on port {port}")
                else:
                    # Fallback: try 'adb -s <target> kill-server' then retry
                    subprocess.run([adb, "kill-server"], capture_output=True, text=True, timeout=5)
                    time.sleep(0.5)
                    subprocess.run([adb, "start-server"], capture_output=True, text=True, timeout=5)
                    res2 = subprocess.run([adb, "-s", target, "emu", "kill"], capture_output=True, text=True, timeout=5)
                    if res2.returncode == 0:
                        self._update_status(f"Closed emulator on port {port}")
                    else:
                        self._update_status(f"Failed to close emulator on port {port}")
            except Exception as e:
                self._update_status(f"Error closing emulator: {e}")
        threading.Thread(target=worker, daemon=True).start()
    
    # ----- WhatsApp integration -----
    def _extract_phone_number(self, from_header: str | None) -> Optional[str]:
        """Extract E.164-ish phone number from a SIP From header or display value.
        Returns digits with optional leading '+', or None if not found."""
        try:
            if not from_header:
                return None
            # Common patterns: sip:+123456789@domain; or sip:123456789@...
            # Also display name might include number in quotes.
            # Strategy: find the longest +?digits sequence between 7 and 15 digits.
            m = re.findall(r"\+?\d{7,15}", from_header)
            if not m:
                return None
            # Prefer the first with '+'; otherwise first
            with_plus = [x for x in m if x.startswith('+')]
            return (with_plus[0] if with_plus else m[0])
        except Exception:
            return None

    def _initiate_windows_whatsapp_call(self, phone_number: str, account_id: int):
        """Initiate a voice call in Windows WhatsApp using the phone number"""
        try:
            self._update_status(f"🔄 Starting Windows WhatsApp call to {phone_number}")
            
            # Format phone number for WhatsApp URL (remove + if present)
            clean_number = phone_number.lstrip('+')
            
            # Method 1: Try direct WhatsApp chat URL first
            def initiate_call():
                import time
                import subprocess
                import pyautogui
                
                try:
                    # Step 1: Direct WhatsApp call using Windows start command
                    whatsapp_call_url = f"whatsapp://call?phone={clean_number}"
                    self._update_status(f"📞 Dialing WhatsApp call directly: {whatsapp_call_url}")
                    
                    # Use Windows start command to launch WhatsApp call
                    import subprocess
                    result = subprocess.run(["start", whatsapp_call_url], shell=True, capture_output=True, text=True, timeout=5)
                    
                    if result.returncode == 0:
                        self._update_status(f"✅ WhatsApp call initiated successfully")
                    else:
                        self._update_status(f"⚠ Start command result: {result.stderr or result.stdout or 'Unknown'}")
                        # Fallback to webbrowser
                        import webbrowser
                        webbrowser.open(whatsapp_call_url)
                        self._update_status(f"📱 Fallback: Used webbrowser for {whatsapp_call_url}")
                    
                    # Step 2: Wait briefly for WhatsApp to process the call
                    self._update_status(f"⏳ Waiting for WhatsApp call to start...")
                    time.sleep(2)
                    
                    # The whatsapp://call protocol should directly initiate the voice call
                    # No additional automation needed - WhatsApp should handle it automatically
                    self._update_status(f"📞 WhatsApp should now be calling {phone_number}")
                    self._update_status(f"ℹ️ If call doesn't start automatically, check WhatsApp permissions")
                    
                    return True
                    
                except Exception as e:
                    self._update_status(f"✗ Call initiation error: {e}")
                    return False
            
            # Run call initiation in a separate thread
            import threading
            threading.Thread(target=initiate_call, daemon=True).start()
                    
        except Exception as e:
            self._update_status(f"✗ Error initiating Windows WhatsApp call: {e}")

    def _open_whatsapp_chat_for_account(self, account_id: int, phone_number: str):
        """Open WhatsApp chat for phone_number on the emulator mapped to account_id.
        If emulator isn't running, attempt to start it and retry for a short period."""
        def worker():
            try:
                port = self.config_manager.get_account_emulator_port(account_id)
                target = f"emulator-{port}"
                adb = self._find_adb_exe()
                if not adb:
                    self._update_status("adb not found; cannot open WhatsApp chat")
                    return

                # Ensure emulator is running; try to launch if not
                if not self._is_emulator_running(port):
                    self._update_status(f"Starting emulator on port {port} for WhatsApp chat...")
                    # Attempt to open emulator quickly (non-blocking)
                    self._set_emulator_status_text(account_id, "Starting...", "orange")
                    self._open_emulator_for_account(account_id)

                # Wait briefly for device; poll for availability and boot completion
                start = time.time()
                device_ready = False
                while time.time() - start < 90:  # up to 90s
                    # Check presence in adb devices
                    try:
                        res = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
                        if res.returncode == 0 and any(target in line and 'device' in line for line in res.stdout.splitlines()):
                            # Optional: check boot completion
                            bc = subprocess.run([adb, "-s", target, "shell", "getprop", "sys.boot_completed"], capture_output=True, text=True, timeout=5)
                            if bc.returncode == 0 and bc.stdout.strip() == '1':
                                device_ready = True
                                break
                    except Exception:
                        pass
                    time.sleep(2)

                if not device_ready:
                    self._update_status(f"Emulator {port} not ready; skipping WhatsApp open")
                    return

                # Launch WhatsApp via universal link
                chat_url = f"https://wa.me/{phone_number.lstrip('+')}"
                cmd = [adb, "-s", target, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", chat_url]
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if res.returncode == 0:
                        self._update_status(f"Opened WhatsApp chat for {phone_number} on {target}")
                        self._set_emulator_status_text(account_id, "Running", "green")
                        
                        # Wait and verify chat page is loaded before tapping
                        if self._wait_for_whatsapp_chat_ready(adb, target, phone_number):
                            # Tapping sequence: initial settle -> Step 1 -> (Delay) -> optional Step 2
                            try:
                                # Reload config to pick up any recent manual edits before reading tap settings
                                try:
                                    self.config_manager.load_config()
                                except Exception:
                                    pass
                                cfg = self.config_manager.get_account_config(account_id) or {}
                                # Delay before tapping starts (after chat page opens)
                                tap_ready_delay_ms = int(cfg.get("whatsapp_tap_ready_delay_ms", 2000))
                                s1x = int(cfg.get("whatsapp_step1_x", cfg.get("whatsapp_tap_x", 230)))
                                s1y = int(cfg.get("whatsapp_step1_y", cfg.get("whatsapp_tap_y", 130)))
                                step_delay_ms = int(cfg.get("whatsapp_step_delay_ms", 800))
                                s2x_raw = cfg.get("whatsapp_step2_x", "")
                                s2y_raw = cfg.get("whatsapp_step2_y", "")
                                s3x_raw = cfg.get("whatsapp_step3_x", "")
                                s3y_raw = cfg.get("whatsapp_step3_y", "")
                                step3_delay_raw = cfg.get("whatsapp_step3_delay_ms", "")
                                has_step2 = False
                                has_step3 = False
                                s2x = s2y = None
                                s3x = s3y = None
                                if not (str(s2x_raw).strip() == "" or str(s2y_raw).strip() == ""):
                                    s2x, s2y = int(s2x_raw), int(s2y_raw)
                                    has_step2 = True
                                if not (str(s3x_raw).strip() == "" or str(s3y_raw).strip() == ""):
                                    s3x, s3y = int(s3x_raw), int(s3y_raw)
                                    has_step3 = True
                                # Step 3 delay (optional, fallback to step_delay_ms)
                                step3_delay_ms = None
                                if str(step3_delay_raw).strip() != "":
                                    try:
                                        step3_delay_ms = int(step3_delay_raw)
                                    except Exception:
                                        step3_delay_ms = None
                                # Brief debug status to confirm resolved tap sequence (helps diagnose Step 3 issues)
                                try:
                                    s2_disp = (f"{s2x},{s2y}" if has_step2 else "-")
                                    s3_disp = (f"{s3x},{s3y}" if has_step3 else "-")
                                    s3d_disp = ("(=Delay)" if step3_delay_ms is None else f"{step3_delay_ms}ms")
                                    self._update_status(
                                        f"WA taps A{account_id}: S1 {s1x},{s1y} | Delay {step_delay_ms}ms | S2 {s2_disp} | S3 {s3_disp} {s3d_disp}"
                                    )
                                except Exception:
                                    pass
                            except Exception:
                                tap_ready_delay_ms, s1x, s1y, step_delay_ms, has_step2, has_step3, step3_delay_ms = 2000, 230, 130, 800, False, False, None

                            # Delay before starting tapping steps (chat page is already open)
                            if tap_ready_delay_ms > 0:
                                self._update_status(f"Waiting {tap_ready_delay_ms}ms before starting tapping...")
                                time.sleep(tap_ready_delay_ms / 1000.0)
                            # Step 1
                            try:
                                tap_cmd1 = [adb, "-s", target, "shell", "input", "tap", str(s1x), str(s1y)]
                                tap_res1 = subprocess.run(tap_cmd1, capture_output=True, text=True, timeout=5)
                                if tap_res1.returncode == 0:
                                    self._update_status(f"Tapped Step 1 at {s1x},{s1y} on {target}")
                                else:
                                    self._update_status(f"Step 1 tap failed: {tap_res1.stderr.strip() or tap_res1.stdout.strip()}")
                            except Exception as te1:
                                self._update_status(f"Step 1 tap error: {te1}")

                            # Step 2 (optional)
                            if has_step2:
                                if step_delay_ms > 0:
                                    time.sleep(step_delay_ms / 1000.0)
                                try:
                                    tap_cmd2 = [adb, "-s", target, "shell", "input", "tap", str(s2x), str(s2y)]
                                    tap_res2 = subprocess.run(tap_cmd2, capture_output=True, text=True, timeout=5)
                                    if tap_res2.returncode == 0:
                                        self._update_status(f"Tapped Step 2 at {s2x},{s2y} on {target}")
                                    else:
                                        self._update_status(f"Step 2 tap failed: {tap_res2.stderr.strip() or tap_res2.stdout.strip()}")
                                except Exception as te2:
                                    self._update_status(f"Step 2 tap error: {te2}")
                            # Step 3 (optional)
                            if has_step3:
                                delay_ms = step3_delay_ms if (step3_delay_ms is not None) else step_delay_ms
                                if delay_ms > 0:
                                    time.sleep(delay_ms / 1000.0)
                                try:
                                    tap_cmd3 = [adb, "-s", target, "shell", "input", "tap", str(s3x), str(s3y)]
                                    tap_res3 = subprocess.run(tap_cmd3, capture_output=True, text=True, timeout=5)
                                    if tap_res3.returncode == 0:
                                        self._update_status(f"Tapped Step 3 at {s3x},{s3y} on {target}")
                                    else:
                                        self._update_status(f"Step 3 tap failed: {tap_res3.stderr.strip() or tap_res3.stdout.strip()}")
                                except Exception as te3:
                                    self._update_status(f"Step 3 tap error: {te3}")
                        else:
                            self._update_status(f"⚠️ WhatsApp chat verification failed - skipping taps")
                    else:
                        self._update_status(f"Failed to open WhatsApp chat: {res.stderr.strip() or res.stdout.strip()}")
                except Exception as e:
                    self._update_status(f"WhatsApp open error: {e}")
            finally:
                # Refresh button label for this account
                try:
                    self._refresh_one_emulator_button_async(account_id)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()
        
    def _wait_for_whatsapp_chat_ready(self, adb: str, target: str, phone_number: str, max_wait_seconds: int = 15) -> bool:
        """Wait for WhatsApp chat page to be ready before tapping."""
        self._update_status(f"Verifying WhatsApp chat page is ready...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            try:
                # Check if WhatsApp is running and responding
                activity_cmd = [adb, "-s", target, "shell", "dumpsys", "activity", "activities", "|", "grep", "whatsapp"]
                result = subprocess.run(activity_cmd, capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0 and "whatsapp" in result.stdout.lower():
                    # Additional check: see if we can detect UI elements (simple verification)
                    ui_cmd = [adb, "-s", target, "shell", "dumpsys", "activity", "top", "|", "head", "-20"]
                    ui_result = subprocess.run(ui_cmd, capture_output=True, text=True, timeout=5)
                    
                    if ui_result.returncode == 0:
                        self._update_status(f"✓ WhatsApp chat page verified ready for {phone_number}")
                        return True
                        
            except Exception as e:
                self._update_status(f"Chat verification check error: {e}")
                
            time.sleep(1)
            
        self._update_status(f"⚠️ WhatsApp chat verification timed out after {max_wait_seconds}s - proceeding anyway")
        return True  # Proceed with tapping even if verification times out
        
    def _get_account_name(self, account_id: int) -> str:
        """Get account name/username for the given account ID"""
        try:
            accounts = self.config_manager.config.get('accounts', {})

            if str(account_id) in accounts:
                username = accounts[str(account_id)].get('username')
                if username:
                    return username

            frame = self.account_status_frames.get(account_id)
            if frame and hasattr(frame, 'username_var'):
                username = frame.username_var.get().strip()
                if username:
                    return username

            return self._default_username(account_id)
            
        except Exception as e:
            print(f"Error getting account name for {account_id}: {e}")
            return self._default_username(account_id)
    
    def _create_status_bar(self):
        """Create status bar at bottom of window"""
        self.status_bar = ttk.Frame(self.root)
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=5)
        self.status_bar.grid_columnconfigure(0, weight=1)
        
        self.status_label = ttk.Label(self.status_bar, text="Ready")
        self.status_label.grid(row=0, column=0, sticky="w")
        
        self.time_label = ttk.Label(self.status_bar, text="")
        self.time_label.grid(row=0, column=1, sticky="e")
        
    def _create_android_install_section(self, parent):
        """Create Android SDK installation section at top of GUI"""
        # Prevent duplicate creation
        if hasattr(self, '_android_install_created') and self._android_install_created:
            return
            
        # Create a prominent frame for Android installation
        install_frame = ttk.LabelFrame(parent, text="[ANDROID] Android SDK & Emulator System Status", padding=10)
        install_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 10))
        install_frame.grid_columnconfigure(1, weight=1)
        
        # Check installation status
        status = self.android_installer.get_installation_status()
        
        # Main status display
        all_ready = all([
            status["sdk_installed"],
            status["emulator_installed"], 
            status["android_14_installed"],
            len(status["avd_list"]) > 0
        ])
        
        status_text = "[OK] System Ready" if all_ready else "[WARN] Setup Required"
        status_label = ttk.Label(install_frame, text=f"Status: {status_text}", font=("TkDefaultFont", 10, "bold"))
        status_label.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        # Detailed system availability status
        system_frame = ttk.Frame(install_frame)
        system_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        system_frame.grid_columnconfigure(2, weight=1)
        
        # Android 14 Status
        a14_icon = "[OK]" if status["android_14_installed"] else "[X]"
        a14_status = "Available" if status["android_14_installed"] else "Not Found"
        ttk.Label(system_frame, text=f"{a14_icon} Android 14 (API 34):", font=("TkDefaultFont", 9, "bold")).grid(row=2, column=0, sticky="w", padx=(0, 5))
        ttk.Label(system_frame, text=a14_status).grid(row=2, column=1, sticky="w", padx=(0, 10))
        
        # AVDs Status
        avd_count = len(status["avd_list"])
        avd_icon = "[OK]" if avd_count > 0 else "[X]"
        avd_status = f"{avd_count} Available" if avd_count > 0 else "None Found"
        ttk.Label(system_frame, text=f"{avd_icon} Virtual Devices (AVDs):", font=("TkDefaultFont", 9, "bold")).grid(row=2, column=2, sticky="w", padx=(10, 5))
        ttk.Label(system_frame, text=avd_status).grid(row=2, column=3, sticky="w")
        
        # System paths info
        paths_frame = ttk.Frame(install_frame)
        paths_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        paths_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(paths_frame, text="[FOLDER] Android Home:", font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 5))
        android_home_path = status["android_home"] if status["android_home"] else "Not Set"
        path_label = ttk.Label(paths_frame, text=android_home_path, font=("TkDefaultFont", 8))
        path_label.grid(row=0, column=1, sticky="w", padx=(0, 10))
        
        # AVD List - Hidden to reduce clutter
        # Individual AVDs are configured per account and don't need to be displayed here
        
        # Separator
        separator = ttk.Separator(install_frame, orient="horizontal")
        separator.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(5, 10))
        
        # Installation button
        self.install_button = ttk.Button(
            install_frame,
            text="[DEVICE] Install Android 14 SDK & Emulator",
            command=self._start_android_installation
        )
        self.install_button.grid(row=4, column=0, sticky="w", padx=(0, 10))
        
        # Refresh status button
        refresh_button = ttk.Button(
            install_frame,
            text="[REFRESH] Refresh Status",
            command=self._refresh_android_install_status
        )
        refresh_button.grid(row=4, column=1, sticky="w", padx=(10, 0))
        
        # Progress bar (hidden initially)
        self.install_progress = ttk.Progressbar(
            install_frame, 
            mode='determinate',
            length=300
        )
        # Don't grid it initially - will be shown during installation
        
        # Progress label (hidden initially)
        self.install_progress_label = ttk.Label(install_frame, text="")
        # Don't grid it initially
        
        # Store references for updates
        self.install_status_label = status_label
        
        # Mark as created to prevent duplicates
        self._android_install_created = True
        
    def _delete_avd(self, avd_name: str):
        """Delete an Android Virtual Device"""
        try:
            # Confirm deletion
            result = messagebox.askyesno(
                "Delete AVD",
                f"Are you sure you want to delete the AVD:\n\n'{avd_name}'?\n\n"
                f"This action cannot be undone.",
                icon="warning"
            )
            
            if not result:
                return
            
            # Find avdmanager executable
            avdmanager_exe = self._find_avdmanager_exe()
            if not avdmanager_exe:
                messagebox.showerror("Error", "AVD Manager not found. Please install Android SDK first.")
                return
            
            # Delete the AVD
            self._update_status("Deleting AVD...")
            
            cmd = [avdmanager_exe, "delete", "avd", "-n", avd_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                messagebox.showinfo("Success", f"AVD '{avd_name}' deleted successfully!")
                self._update_status(f"AVD '{avd_name}' deleted")
                # Refresh the Android status display
                self._refresh_android_status()
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                messagebox.showerror("Delete Failed", f"Failed to delete AVD '{avd_name}':\n{error_msg}")
                self._update_status("AVD deletion failed")
                
        except subprocess.TimeoutExpired:
            messagebox.showerror("Error", f"Delete operation timed out for AVD '{avd_name}'")
            self._update_status("AVD deletion timed out")
        except Exception as e:
            messagebox.showerror("Error", f"Error deleting AVD '{avd_name}':\n{str(e)}")
            self._update_status("AVD deletion error")
    
    def _find_avdmanager_exe(self) -> Optional[str]:
        """Find avdmanager executable"""
        # Check common Android SDK locations
        candidates = []
        
        # Environment variables
        for env_var in ["ANDROID_SDK_ROOT", "ANDROID_HOME"]:
            if env_var in os.environ:
                candidates.append(os.path.join(os.environ[env_var], "cmdline-tools", "latest", "bin", "avdmanager.bat"))
                candidates.append(os.path.join(os.environ[env_var], "tools", "bin", "avdmanager.bat"))
        
        # Local AppData
        local_sdk = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
        candidates.append(os.path.join(local_sdk, "cmdline-tools", "latest", "bin", "avdmanager.bat"))
        candidates.append(os.path.join(local_sdk, "tools", "bin", "avdmanager.bat"))
        
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return None
    
    def _refresh_android_status(self):
        """Refresh the Android status section"""
        # This will trigger a refresh of the android install section
        # by recreating it - we'll need to clear and rebuild
        if hasattr(self, '_android_install_created'):
            # Find the status frame and refresh it
            for child in self.root.winfo_children():
                if isinstance(child, ttk.Frame):
                    # Look for the status frame
                    for subchild in child.winfo_children():
                        if isinstance(subchild, ttk.LabelFrame) and "Android SDK" in subchild.cget('text'):
                            # Clear and recreate the android section
                            subchild.destroy()
                            self._android_install_created = False
                            self._create_android_install_section(child)
                            break

    def _start_android_installation(self):
        """Start Android SDK and emulator installation process"""
        try:
            # Confirm installation
            result = messagebox.askyesno(
                "Install Android SDK & Emulator",
                "This will download and install:\n\n"
                "* Android SDK Command Line Tools\n"
                "* Android Platform Tools (ADB)\n"
                "* Android Emulator\n"
                "* Android 14 (API 34) System Image\n"
                "* Create Android 14 Virtual Device\n\n"
                "Installation size: ~2-3 GB\n"
                "Continue?",
                icon="question"
            )
            
            if not result:
                return
                
            # Disable install button and show progress
            self.install_button.config(state="disabled", text="Installing...")
            self.install_progress.grid(row=2, column=1, sticky="ew", padx=(10, 0))
            self.install_progress_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(5, 0))
            
            # Set up callbacks for installation progress
            def progress_callback(message: str, percentage: int):
                def update_ui():
                    self.install_progress['value'] = percentage
                    self.install_progress_label.config(text=f"{message} ({percentage}%)")
                    self.root.update_idletasks()
                self.root.after(0, update_ui)
                
            def completion_callback(success: bool, message: str):
                def update_ui():
                    if success:
                        messagebox.showinfo("Installation Complete", 
                                          "[OK] Android SDK and Android 14 emulator installed successfully!\n\n"
                                          "You can now use the 'Open Emulator' buttons for each account.")
                        self.install_button.config(text="[OK] Installation Complete", state="disabled")
                        self.install_status_label.config(text="Status: [OK] Ready")
                        # Refresh the installation status display
                        self._refresh_android_install_status()
                    else:
                        messagebox.showerror("Installation Failed", f"[X] Installation failed:\n\n{message}")
                        self.install_button.config(text="[DEVICE] Install Android 14 SDK & Emulator", state="normal")
                        
                    # Hide progress elements
                    self.install_progress.grid_remove()
                    self.install_progress_label.grid_remove()
                    self.install_progress['value'] = 0
                    
                self.root.after(0, update_ui)
            
            # Set callbacks and start installation
            self.android_installer.set_progress_callback(progress_callback)
            install_android_async(self.android_installer, self.config_manager, completion_callback)
            
        except Exception as e:
            messagebox.showerror("Installation Error", f"Failed to start installation: {e}")
            self.install_button.config(text="[DEVICE] Install Android 14 SDK & Emulator", state="normal")
            
    def _refresh_android_install_status(self):
        """Refresh the Android installation status display"""
        try:
            # Find the existing Android install frame in the status tab
            install_frame = None
            
            # Look in the status tab specifically
            for tab_id in self.notebook.tabs():
                tab_widget = self.notebook.nametowidget(tab_id)
                if self.notebook.tab(tab_id, "text") == "Account Status":
                    # Found the Account Status tab, look for the Android install frame
                    for child in tab_widget.winfo_children():
                        if isinstance(child, ttk.LabelFrame) and "Android SDK" in child.cget("text"):
                            install_frame = child
                            break
                    break
            
            if not install_frame:
                # Frame doesn't exist, skip refresh (it should have been created during init)
                return
            
            # Get updated status
            status = self.android_installer.get_installation_status()
            
            # Update the main status label if it exists
            if hasattr(self, 'install_status_label') and self.install_status_label.winfo_exists():
                all_ready = all([
                    status["sdk_installed"],
                    status["emulator_installed"], 
                    status["android_14_installed"],
                    len(status["avd_list"]) > 0
                ])
                status_text = "[OK] System Ready" if all_ready else "[WARN] Setup Required"
                self.install_status_label.config(text=f"Status: {status_text}")
            
        except Exception as e:
            self._update_status(f"Error refreshing Android install status: {e}")
            
    def _auto_configure_avd_if_needed(self):
        """Auto-configure AVD for accounts if Android SDK is installed but AVDs not configured"""
        try:
            # Check if SDK is installed but accounts don't have AVD configured
            status = self.android_installer.get_installation_status()
            if status["sdk_installed"] and status["emulator_installed"] and len(status["avd_list"]) > 0:
                # Check if any account needs AVD configuration
                needs_config = False
                # Get accounts from config instead of hardcoded range
                accounts = self.config_manager.config.get("accounts", {})
                account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])
                
                for account_id in account_ids:
                    cfg = self.config_manager.get_account_config(account_id) or {}
                    if not cfg.get("emulator_avd"):
                        needs_config = True
                        break
                if needs_config:
                    configured_count = 0
                    for account_id in account_ids:
                        avd_name = f"SipDialer_Account_{account_id}"
                        if avd_name in status["avd_list"]:
                            cfg = self.config_manager.get_account_config(account_id) or {}
                            cfg["emulator_avd"] = avd_name
                            if self.config_manager.set_account_config(account_id, cfg):
                                configured_count += 1
                    if configured_count > 0:
                        self.config_manager.save_config()
                        self._update_status(f"[OK] {configured_count} accounts configured with individual AVDs")
                    else:
                        self._update_status("No individual AVDs found for accounts")
      
        except Exception as e:
            print(f"Error in auto-configure AVD: {e}")
    
    
    
    
    def _initialize_sip(self):
        """Initialize SIP manager in background thread"""
        def init_worker():
            try:
                ok = False
                if hasattr(self.sip_manager, 'initialize'):
                    ok = bool(self.sip_manager.initialize())
                if ok:
                    self._ui_queue.put(('status', 'SIP initialized'))
                else:
                    self._ui_queue.put(('status', 'SIP init failed'))
            except Exception as e:
                self._ui_queue.put(('status', f'SIP init error: {e}'))
        threading.Thread(target=init_worker, daemon=True).start()

    def _start_status_timer(self):
        """Start periodic UI update timer and process UI queue on main thread."""
        def update_timer():
            # Process queued UI updates
            try:
                while True:
                    msg_type, payload = self._ui_queue.get_nowait()
                    if msg_type == 'status':
                        self.status_label.config(text=str(payload))
                    elif msg_type == 'account_status':
                        aid, registered, code = payload
                        self._apply_account_status_update(aid, registered, code)
                    elif msg_type == 'reg_btn':
                        aid, text = payload
                        frame = self.account_status_frames.get(aid)
                        if frame and hasattr(frame, 'register_btn'):
                            frame.register_btn.config(text=text)
                    elif msg_type == 'emu_btn_text':
                        aid, text, enabled = payload
                        btn = self._emu_buttons.get(aid)
                        if btn:
                            btn.config(text=text)
                            if enabled:
                                btn.state(['!disabled'])
                            else:
                                btn.state(['disabled'])
                    elif msg_type == 'emu_status_text':
                        aid, text, color = payload
                        lbl = self._emu_status_labels.get(aid)
                        if lbl:
                            kwargs = {'text': text}
                            if color:
                                kwargs['foreground'] = color
                            lbl.config(**kwargs)
                    elif msg_type == 'emu_button':
                        status_map: Dict[int, bool] = payload
                        for aid, running in status_map.items():
                            btn = self._emu_buttons.get(aid)
                            if btn:
                                btn.config(text=("Close Emulator" if running else "Open Emulator"))
                                btn.state(['!disabled'])
                            lbl = self._emu_status_labels.get(aid)
                            if lbl:
                                if running:
                                    lbl.config(text="Running", foreground="green")
                                else:
                                    lbl.config(text="Stopped", foreground="red")
                    elif msg_type == 'wa_status':
                        aid, text, state = payload
                        lbl = self._wa_status_labels.get(aid)
                        if lbl:
                            color = {'IDLE': '#555555', 'RINGING': '#cc8800', 'CONNECTED': 'green', 'ONGOING': 'green', 'UNKNOWN': '#888888'}.get(state, '#555555')
                            lbl.config(text=text, foreground=color)
            except queue.Empty:
                pass

            # Update clock
            try:
                current_time = datetime.now().strftime("%H:%M:%S")
                self.time_label.config(text=current_time)
            except Exception:
                pass

            # Periodically refresh emulator state (every ~2.5s)
            self._timer_tick = (self._timer_tick + 1) % 10
            if self._timer_tick == 0:
                self._refresh_emulator_buttons_async()

            # Live update WhatsApp CONNECTED durations (tick every 250ms)
            try:
                if hasattr(self, '_wa_call_start'):
                    for aid, start_ts in list(getattr(self, '_wa_call_start', {}).items()):
                        lbl = self._wa_status_labels.get(aid)
                        if not lbl:
                            continue
                        # Only update if current label contains 'WA: CONNECTED'
                        current = lbl.cget('text')
                        if 'WA: CONNECTED' in current:
                            elapsed = int(time.time() - start_ts)
                            mm = elapsed // 60
                            ss = elapsed % 60
                            # Preserve any number after CONNECTED (e.g., phone number)
                            # Pattern: WA: CONNECTED [number] 00:05
                            import re
                            m = re.match(r'(WA: CONNECTED(?: [^ ]+)?) \d{2}:\d{2}$', current)
                            if m:
                                base = m.group(1)
                            else:
                                # fallback remove trailing time if present
                                parts = current.split()
                                if len(parts) >= 2:
                                    base = ' '.join(parts[:-1]) if re.match(r'\d{2}:\d{2}$', parts[-1]) else current
                                else:
                                    base = current
                            new_text = f"{base} {mm:02d}:{ss:02d}"
                            if new_text != current:
                                lbl.config(text=new_text)
            except Exception:
                pass

            # Schedule next tick
            self.root.after(250, update_timer)

        update_timer()

    # -------- Live Registration Status --------
    def _start_registration_live_update(self):
        """Start a repeating Tk callback to refresh registration status & button text in near real-time."""
        def refresh():
            try:
                sip = getattr(self, 'sip_manager', None)
                if sip:
                    acct_map = getattr(sip, 'accounts', {}) or {}
                    registered = getattr(sip, 'registered_accounts', set()) or set()
                    now = time.time()
                    # Get accounts from config instead of hardcoded range
                    accounts = self.config_manager.config.get("accounts", {})
                    account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])
                    
                    for aid in account_ids:
                        label = self.account_status_labels.get(aid)
                        frame = self.account_status_frames.get(aid)
                        if not label or not frame:
                            continue
                        if aid in acct_map:
                            acct = acct_map.get(aid, {})
                            expires = acct.get('registration_expires', 0)
                            if aid in registered:
                                remaining = max(0, int(expires - now)) if expires else 0
                                if remaining:
                                    mm = remaining // 60
                                    ss = remaining % 60
                                    label.config(text=f"Registered ({mm:02d}:{ss:02d})", foreground="green")
                                else:
                                    label.config(text="Registered", foreground="green")
                                # Button should show Stop
                                if hasattr(frame, 'register_btn') and frame.register_btn.cget('text') != 'Stop':
                                    frame.register_btn.config(text='Stop')
                            else:
                                # Account added but not registered yet (in-progress or idle)
                                label.config(text="Registering...", foreground="orange")
                                if hasattr(frame, 'register_btn') and frame.register_btn.cget('text') != 'Stop':
                                    frame.register_btn.config(text='Stop')
                        else:
                            # Not added
                            label.config(text="Not Registered", foreground="red")
                            if hasattr(frame, 'register_btn') and frame.register_btn.cget('text') != 'Start':
                                frame.register_btn.config(text='Start')
            except Exception:
                pass
            # schedule next
            try:
                self.root.after(1000, refresh)
            except Exception:
                pass
        # Kick off first run on main thread
        self.root.after(1000, refresh)
    
    def _update_status(self, message):
        """Update status bar message; thread-safe via UI queue"""
        if threading.current_thread() == threading.main_thread():
            self.status_label.config(text=message)
        else:
            # Defer to main thread via queue to avoid Tkinter thread errors
            self._ui_queue.put(('status', message))

    def _set_emulator_button_text(self, account_id: int, text: str, enabled: bool = True):
        # Thread-safe update via queue
        self._ui_queue.put(('emu_btn_text', (account_id, text, enabled)))

    def _set_emulator_status_text(self, account_id: int, text: str, color: str = None):
        self._ui_queue.put(('emu_status_text', (account_id, text, color)))

    def _refresh_emulator_buttons_async(self):
        def worker():
            status_map: Dict[int, bool] = {}
            try:
                for aid in list(self.account_status_frames.keys()):
                    port = self.config_manager.get_account_emulator_port(aid)
                    status_map[aid] = self._is_emulator_running(port)
            finally:
                self._ui_queue.put(('emu_button', status_map))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_one_emulator_button_async(self, account_id: int):
        def worker():
            port = self.config_manager.get_account_emulator_port(account_id)
            running = self._is_emulator_running(port)
            self._set_emulator_button_text(account_id, "Close Emulator" if running else "Open Emulator", True)
        threading.Thread(target=worker, daemon=True).start()

    def _toggle_emulator_for_account(self, account_id: int):
        def worker():
            port = self.config_manager.get_account_emulator_port(account_id)
            running = self._is_emulator_running(port)
            if running:
                self._set_emulator_button_text(account_id, "Closing...", False)
                self._set_emulator_status_text(account_id, "Stopping...", "orange")
                adb = self._find_adb_exe()
                if not adb:
                    self._update_status("adb not found (install Android SDK or add to PATH)")
                else:
                    target = f"emulator-{port}"
                    try:
                        subprocess.run([adb, "-s", target, "emu", "kill"], capture_output=True, text=True, timeout=8)
                    except Exception as e:
                        self._update_status(f"Error closing emulator: {e}")
                time.sleep(0.5)
                self._refresh_one_emulator_button_async(account_id)
            else:
                self._set_emulator_button_text(account_id, "Opening...", False)
                self._set_emulator_status_text(account_id, "Starting...", "orange")
                emulator_exe = self._find_emulator_exe()
                if not emulator_exe:
                    self._update_status("Emulator not found (install Android SDK or add to PATH)")
                else:
                    cfg = self.config_manager.get_account_config(account_id) or {}
                    avd = cfg.get("emulator_avd")
                    if not avd:
                        avds = self._list_avds(emulator_exe)
                        if avds:
                            avd = avds[0]
                    if not avd:
                        self._update_status("No AVD configured/found; set 'emulator_avd' in config.json")
                        self._set_emulator_status_text(account_id, "No AVD", "red")
                    else:
                        args = [
                            emulator_exe, 
                            "-avd", avd, 
                            "-port", str(port), 
                            "-no-metrics",
                            "-netdelay", "none", 
                            "-netspeed", "full", 
                            "-no-boot-anim",
                            "-gpu", "host",  # Use host GPU for better performance
                            "-memory", "2048",  # Allocate more memory per emulator for simultaneous use
                            "-cores", "2"  # Use 2 CPU cores per emulator
                        ]
                        try:
                            # Set creation flags to hide console window completely
                            creationflags = 0
                            if os.name == 'nt':
                                # Use CREATE_NO_WINDOW to completely hide console
                                # The emulator GUI will still show as it's a separate window
                                creationflags = subprocess.CREATE_NO_WINDOW
                            
                            # Set proper environment variables for emulator
                            env = os.environ.copy()
                            android_sdk_path = os.path.dirname(os.path.dirname(emulator_exe))  # Go up two levels from emulator/emulator.exe
                            env['ANDROID_SDK_ROOT'] = android_sdk_path
                            env['ANDROID_HOME'] = android_sdk_path
                            env['ANDROID_AVD_HOME'] = os.path.join(os.path.expanduser("~"), ".android", "avd")
                            
                            self._update_status(f"Environment: ANDROID_SDK_ROOT={android_sdk_path}")
                            
                            process = subprocess.Popen(args, creationflags=creationflags, env=env)
                            self._update_status(f"🚀 Launching emulator {avd} on port {port} with enhanced settings for simultaneous operation (PID: {process.pid})")
                            self._set_emulator_status_text(account_id, "Starting...", "orange")
                        except Exception as e:
                            self._update_status(f"Failed to launch emulator: {e}")
                            self._set_emulator_status_text(account_id, "Failed", "red")
                time.sleep(1.0)
                self._refresh_one_emulator_button_async(account_id)
        threading.Thread(target=worker, daemon=True).start()
    
    def _toggle_account_registration(self, account_id):
        """Toggle account registration with automatic username save"""
        try:
            if account_id in self.sip_manager.accounts:
                # Unregister from server and remove account
                self.sip_manager.remove_account(account_id)
                self._update_account_status(account_id, False, 0)
                # Stop associated audio worker as part of Stop
                try:
                    self.account_audio_manager.stop_for_account(account_id)
                except Exception:
                    pass
                self.account_status_frames[account_id].register_btn.config(text="Start")
                self._update_status(f"Account {account_id} unregistered")
            else:
                # Get current username from input field
                frame = self.account_status_frames[account_id]
                username = frame.username_var.get().strip()
                
                if not username:
                    messagebox.showwarning("Warning", "Please enter a username first")
                    return
                
                # Auto-save username when registering
                self.config_manager.set_account_config(account_id, {"username": username})
                self.config_manager.save_config()
                
                # Register with current username and fixed configuration
                account_config = self.config_manager.get_account_config(account_id)
                account_config["username"] = username  # Use current input
                
                if self.sip_manager.add_account(account_id, account_config):
                    # Actually register the account with the server
                    if self.sip_manager.register_account(account_id):
                        self.account_status_frames[account_id].register_btn.config(text="Stop")
                        self._update_status(f"Registering Account {account_id} with username: {username}")
                    else:
                        messagebox.showerror("Error", f"Failed to register Account {account_id} with server")
                else:
                    messagebox.showerror("Error", f"Failed to add Account {account_id}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Registration error: {e}")
    
    def _toggle_call_routing(self, account_id):
        """Toggle call routing between WhatsApp and Desktop for an account"""
        try:
            # Toggle the routing state
            current_state = self._call_routing_state.get(account_id, False)
            new_state = not current_state
            self._call_routing_state[account_id] = new_state
            
            # Update button text
            if new_state:
                button_text = "Emulator WhatsApp"
                route_text = "Emulator WhatsApp"
            else:
                button_text = "Windows WhatsApp"
                route_text = "Windows WhatsApp"
            
            self._call_routing_buttons[account_id].config(text=button_text)
            self._update_status(f"Account {account_id} calls will route to {route_text}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Call routing toggle error: {e}")
    
    def _on_registration_changed(self, account_id, registered, status_code):
        """Handle registration state change"""
        self._update_account_status(account_id, registered, status_code)
        
        if registered:
            self._update_status(f"Account {account_id} registered successfully")
            # Start per-account audio worker (separate Volume Mixer app per account)
            try:
                cfg = self.config_manager.get_account_config(account_id) or {}
                username = cfg.get('username') or self._default_username(account_id)
                self.account_audio_manager.start_for_account(account_id, username)
            except Exception as e:
                print(f"[WARN]  Could not start audio worker for account {account_id}: {e}")
            # Update register button to Stop
            self._ui_queue.put(('reg_btn', (account_id, 'Stop')))
        else:
            self._update_status(f"Account {account_id} registration failed")
            # Stop worker if running
            self.account_audio_manager.stop_for_account(account_id)
            # Update register button to Start
            self._ui_queue.put(('reg_btn', (account_id, 'Start')))
    
    def _apply_account_status_update(self, account_id, registered, status_code):
        """Apply account status update on the main thread only."""
        if account_id in self.account_status_labels:
            label = self.account_status_labels[account_id]
            if registered:
                label.config(text="Registered", foreground="green")
            else:
                label.config(text=f"Not Registered ({status_code})", foreground="red")

    def _update_account_status(self, account_id, registered, status_code):
        """Queue-safe update for account status display"""
        if threading.current_thread() == threading.main_thread():
            self._apply_account_status_update(account_id, registered, status_code)
        else:
            self._ui_queue.put(('account_status', (account_id, registered, status_code)))
    
    def _on_incoming_call(self, account_id, call_id, call_info):
        """Handle incoming call - route to WhatsApp or Desktop based on account setting"""
        # Extract caller number from active_calls if available
        caller_display = "Unknown"
        try:
            call_obj = getattr(self.sip_manager, 'active_calls', {}).get(call_id)
            if call_obj and call_obj.get('caller_number'):
                caller_display = call_obj.get('caller_number')
            elif isinstance(call_info, str):
                extracted = self._extract_phone_number(call_info)
                caller_display = extracted or call_info[:30]
        except Exception:
            caller_display = str(call_info)[:30] if call_info else "Unknown"
        
        # Check routing preference for this account
        route_to_whatsapp = self._call_routing_state.get(account_id, False)
        
        if route_to_whatsapp:
            # Route to WhatsApp (existing deferred behavior)
            self._update_status(f"📞 Incoming call (WhatsApp route) A{account_id} from {caller_display}")
            # Save deferred call details
            self._deferred_calls[call_id] = {
                'account_id': account_id,
                'received_ts': time.time(),
                'call_info': call_info,
                'caller_display': caller_display,
                'answered': False,
            }
            # Extract possible phone number and open WA chat early
            try:
                number = self._extract_phone_number(call_info if isinstance(call_info, str) else None)
                if number:
                    self._update_status(f"Opening WA for deferred {number} (A{account_id})")
                    self._open_whatsapp_chat_for_account(account_id, number)
            except Exception:
                pass
        else:
            # Route to Windows WhatsApp with speech recognition (dial WhatsApp FIRST, then wait for voice)
            self._update_status(f"📞 Incoming call (WhatsApp First + Speech Recognition) A{account_id} from {caller_display}")
            
            # Store call for speech recognition processing
            self._deferred_calls[call_id] = {
                'account_id': account_id,
                'received_ts': time.time(),
                'call_info': call_info,
                'caller_display': caller_display,
                'answered': False,
                'speech_detection_mode': True,  # Flag for speech recognition
            }
            
            # FIRST: Dial WhatsApp call immediately
            phone_number = self._extract_phone_number(call_info if isinstance(call_info, str) else caller_display)
            if phone_number:
                self._update_status(f"🔄 Dialing WhatsApp call FIRST to {phone_number}")
                self._initiate_windows_whatsapp_call(phone_number, account_id)
                
                # Give WhatsApp time to start calling, then start speech recognition
                def delayed_speech_recognition():
                    import time
                    time.sleep(3)  # Wait for WhatsApp call to start
                    if call_id in self._deferred_calls:  # Check call still exists
                        self._start_speech_recognition_for_call(call_id, account_id, caller_display)
                
                import threading
                threading.Thread(target=delayed_speech_recognition, daemon=True).start()
            else:
                self._update_status(f"⚠ Could not extract phone number - starting speech recognition anyway")
                self._start_speech_recognition_for_call(call_id, account_id, caller_display)
        
        # Stop worker preemptively (avoid duplicate sessions once answered later)
        try:
            self._call_to_account[call_id] = account_id
            #self.account_audio_manager.stop_for_account(account_id)
        except Exception:
            pass
    
    def _on_call_state_changed(self, call_id, state, state_text):
        """Handle call state change"""
        self._update_status(f"Call {call_id}: {state_text}")
        # Mark answered latency when established
        if state == 'ESTABLISHED' and call_id in self._deferred_calls:
            info = self._deferred_calls.get(call_id, {})
            if info and not info.get('answered_latency_logged'):
                recv_ts = info.get('received_ts')
                try:
                    call_obj = getattr(self.sip_manager, 'active_calls', {}).get(call_id, {})
                    ans_ts = call_obj.get('answered_ts') or time.time()
                    latency = ans_ts - recv_ts if recv_ts else 0.0
                    self._update_status(f"Deferred call {call_id} latency {latency:.3f}s")
                    info['answered_latency_logged'] = True
                except Exception:
                    pass
        # Call controls removed from UI; no per-call button state updates
        # When a call becomes established, stop the worker for that account to avoid duplicate Mixer entries
        if state == 'ESTABLISHED':
            # Ensure we know the account for this call
            account_id = self._call_to_account.get(call_id)
            if account_id is None:
                try:
                    # Try to infer from the SIP manager's active_calls mapping (EnhancedSipManager)
                    if hasattr(self.sip_manager, 'active_calls'):
                        call_info = self.sip_manager.active_calls.get(call_id)
                        if call_info and 'account_id' in call_info:
                            account_id = call_info['account_id']
                            self._call_to_account[call_id] = account_id
                except Exception:
                    account_id = None
            if account_id is not None:
                try:
                    self.account_audio_manager.stop_for_account(account_id)
                except Exception:
                    pass

        # Also preemptively stop worker during call setup for outgoing calls
        if state in ('TRYING', 'RINGING'):
            account_id = self._call_to_account.get(call_id)
            if account_id is None:
                try:
                    if hasattr(self.sip_manager, 'active_calls'):
                        call_info = self.sip_manager.active_calls.get(call_id)
                        if call_info and 'account_id' in call_info:
                            account_id = call_info['account_id']
                            self._call_to_account[call_id] = account_id
                except Exception:
                    account_id = None
            if account_id is not None:
                try:
                    self.account_audio_manager.stop_for_account(account_id)
                except Exception:
                    pass

        # When a call ends, restart the worker for that account so the Mixer entry returns
        if state in ('TERMINATED', 'FAILED', 'BUSY', 'TIMEOUT', 'ERROR'):
            account_id = self._call_to_account.pop(call_id, None)
            if account_id is not None:
                try:
                    cfg = self.config_manager.get_account_config(account_id) or {}
                    username = cfg.get('username') or self._default_username(account_id)
                    self.account_audio_manager.start_for_account(account_id, username)
                except Exception:
                    pass
    
    # Call-related UI and actions removed per request
    
    # In-process Volume Mixer session management removed; handled by workers only
    
    # Volume Mixer control methods
    def _start_all_audio_workers_manual(self):
        """Manually start all audio workers (button click)"""
        try:
            # Get accounts from config instead of hardcoded range
            accounts = self.config_manager.config.get("accounts", {})
            account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])
            total_accounts = len(account_ids)
            
            self.mixer_status_text.delete("1.0", "end")
            self.mixer_status_text.insert("end", f"[MIXER] Starting {len(account_ids)} SIP account audio workers...\n")
            self.mixer_status_text.insert("end", "=" * 50 + "\n")
            
            started_count = 0
            for account_id in account_ids:
                account_name = self._default_username(account_id)
                self.mixer_status_text.insert("end", f"[PLAY]  Starting Account {account_id} ({account_name})...\n")
                self.mixer_status_text.update()
                
                try:
                    result = self.account_audio_manager.start_for_account(account_id, account_name)
                    if result:
                        started_count += 1
                        self.mixer_status_text.insert("end", f"   [OK] Account {account_id} started successfully\n")
                    else:
                        self.mixer_status_text.insert("end", f"   [X] Account {account_id} failed to start\n")
                except Exception as e:
                    self.mixer_status_text.insert("end", f"   [X] Account {account_id} error: {e}\n")
                
                self.mixer_status_text.see("end")
                self.mixer_status_text.update()
            
            self.mixer_status_text.insert("end", "=" * 50 + "\n")
            self.mixer_status_text.insert("end", f"? Audio workers started: {started_count}/{total_accounts}\n")
            
            if started_count > 0:
                self.mixer_status_text.insert("end", "\n? Waiting 3 seconds for workers to initialize...\n")
                self.mixer_status_text.update()
                self.root.after(3000, lambda: self._finalize_audio_worker_startup())
            else:
                self.mixer_status_text.insert("end", "\n[X] No workers started. Check audio device configuration.\n")
            
            self.mixer_status_text.see("end")
            
        except Exception as e:
            self.mixer_status_text.insert("end", f"\n[X] Error starting workers: {e}\n")
    
    def _finalize_audio_worker_startup(self):
        """Called after delay to complete audio worker startup"""
        self.mixer_status_text.insert("end", "\n[OK] Workers should now be visible in Volume Mixer!\n")
        self.mixer_status_text.insert("end", "   Look for: 'SIP Account 1 (JEFF01)' and 'SIP Account 2 (JEFF0)'\n")
        self.mixer_status_text.see("end")
    
    def _stop_all_audio_workers(self):
        """Stop all audio workers"""
        try:
            self.mixer_status_text.delete("1.0", "end")
            self.mixer_status_text.insert("end", "? Stopping all audio workers...\n")
            self.account_audio_manager.stop_all()
            self.mixer_status_text.insert("end", "[OK] All audio workers stopped\n")
            self.mixer_status_text.insert("end", "   SIP accounts no longer visible in Volume Mixer\n")
            self.mixer_status_text.see("end")
        except Exception as e:
            self.mixer_status_text.insert("end", f"[X] Error stopping workers: {e}\n")
    
    def _check_volume_mixer_status(self):
        """Check current Volume Mixer entries"""
        def check_worker():
            try:
                self.root.after(0, lambda: self.mixer_status_text.delete("1.0", "end"))
                self.root.after(0, lambda: self.mixer_status_text.insert("end", "[CHECK] Checking Windows Volume Mixer entries...\n"))
                self.root.after(0, lambda: self.mixer_status_text.insert("end", "=" * 50 + "\n"))
                
                try:
                    from pycaw.pycaw import AudioUtilities
                    sessions = AudioUtilities.GetAllSessions()
                    sip_sessions = []
                    all_sessions = []
                    
                    for session in sessions:
                        try:
                            if session.Process:
                                name = session.Process.name() if hasattr(session.Process, 'name') else 'Unknown'
                                pid = session.Process.pid
                                
                                # Get display name
                                display_name = ""
                                try:
                                    if hasattr(session, '_ctl') and session._ctl:
                                        display_name = session._ctl.GetDisplayName() or ""
                                except:
                                    pass
                                
                                session_info = f"{name} (PID:{pid})"
                                if display_name:
                                    session_info += f" - '{display_name}'"
                                
                                all_sessions.append(session_info)
                                
                                # Check for SIP sessions
                                if 'SIP Account' in display_name:
                                    sip_sessions.append(display_name)
                                    
                        except Exception:
                            pass
                    
                    # Show SIP sessions
                    if sip_sessions:
                        self.root.after(0, lambda: self.mixer_status_text.insert("end", f"[OK] Found {len(sip_sessions)} SIP Account sessions in Volume Mixer:\n"))
                        for sip_session in sip_sessions:
                            self.root.after(0, lambda s=sip_session: self.mixer_status_text.insert("end", f"   [MIXER] {s}\n"))
                    else:
                        self.root.after(0, lambda: self.mixer_status_text.insert("end", "[X] No SIP Account sessions found in Volume Mixer\n"))
                        self.root.after(0, lambda: self.mixer_status_text.insert("end", "   ? Click 'Start All Audio Workers' to make them appear\n"))
                    
                    # Show other sessions for reference
                    self.root.after(0, lambda: self.mixer_status_text.insert("end", f"\n? All audio sessions ({len(all_sessions)} total):\n"))
                    for session in all_sessions[:6]:  # Show first 6
                        self.root.after(0, lambda s=session: self.mixer_status_text.insert("end", f"   * {s}\n"))
                    if len(all_sessions) > 6:
                        remaining = len(all_sessions) - 6
                        self.root.after(0, lambda r=remaining: self.mixer_status_text.insert("end", f"   ... and {r} more\n"))
                        
                except ImportError:
                    self.root.after(0, lambda: self.mixer_status_text.insert("end", "[X] pycaw not available - install with: pip install pycaw\n"))
                except Exception as e:
                    self.root.after(0, lambda: self.mixer_status_text.insert("end", f"[X] Error checking Volume Mixer: {e}\n"))
                
                self.root.after(0, lambda: self.mixer_status_text.see("end"))
                    
            except Exception as e:
                self.root.after(0, lambda: self.mixer_status_text.insert("end", f"[X] Error in mixer check: {e}\n"))
        
        # Run in separate thread to avoid blocking GUI
        import threading
        threading.Thread(target=check_worker, daemon=True).start()
    
    def _open_volume_mixer(self):
        """Open Windows Volume Mixer"""
        try:
            import subprocess
            subprocess.Popen(["sndvol.exe"], creationflags=subprocess.CREATE_NO_WINDOW)
            self.mixer_status_text.delete("1.0", "end")
            self.mixer_status_text.insert("end", "[AUDIO] Opening Windows Volume Mixer...\n")
            self.mixer_status_text.insert("end", "[OK] Volume Mixer should now be open\n")
            self.mixer_status_text.see("end")
        except Exception as e:
            self.mixer_status_text.insert("end", f"[X] Error opening Volume Mixer: {e}\n")
    
    def __del__(self):
        """Cleanup when application is destroyed"""
        try:
            if hasattr(self, 'sip_manager'):
                self.sip_manager.shutdown()
            if hasattr(self, 'account_audio_manager'):
                self.account_audio_manager.stop_all()
        except:
            pass

    # ----- Auto registration on startup -----
    def _auto_register_accounts_on_startup(self):
        """Automatically add and register accounts marked auto_register in config on app start."""
        def worker():
            try:
                # Wait briefly until SIP manager is running
                for _ in range(20):  # up to ~4s
                    if getattr(self.sip_manager, 'running', False):
                        break
                    time.sleep(0.2)
                # Iterate through configured accounts
                # Get accounts from config instead of hardcoded range
                accounts = self.config_manager.config.get("accounts", {})
                account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])
                
                for account_id in account_ids:
                    try:
                        cfg = self.config_manager.get_account_config(account_id) or {}
                        if not cfg.get('enabled', True):
                            continue
                        if not cfg.get('auto_register', True):
                            continue
                        # Ensure username exists
                        username = cfg.get('username', f'1{account_id:03d}')
                        # Add account if not already present
                        if account_id not in getattr(self.sip_manager, 'accounts', {}):
                            added = self.sip_manager.add_account(account_id, cfg)
                            if not added:
                                continue
                        # Register if not already registered
                        if account_id not in getattr(self.sip_manager, 'registered_accounts', set()):
                            self._update_status(f"Auto registering Account {account_id} ({username})...")
                            self.sip_manager.register_account(account_id)
                            # Optimistically set button to Stop; callback will confirm
                            self._ui_queue.put(('reg_btn', (account_id, 'Stop')))
                    except Exception as e_acc:
                        print(f"Auto-register error for account {account_id}: {e_acc}")
                        continue
            except Exception as e:
                print(f"Auto-register worker error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    # -------- Notification watcher for deferred answer --------
    def _start_notification_watcher(self):
        if self._notification_thread and self._notification_thread.is_alive():
            return
        self._notification_thread = threading.Thread(target=self._notification_loop, daemon=True)
        self._notification_thread.start()

    def _notification_loop(self):
        # New implementation: use WhatsAppCallMonitor for each emulator referenced by deferred calls.
        try:
            from whatsapp_monitor import WhatsAppCallMonitor
        except ImportError:
            print("Notification watcher: whatsapp_monitor not available")
            return

        monitor = WhatsAppCallMonitor(poll_interval=1.2)

        def _attempt_sip_answer(call_id: int) -> bool:
            """Try available SIP manager answer methods, preferring deferred flow."""
            ok = False
            sip_manager = getattr(self, 'sip_manager', None)
            if not sip_manager:
                return False

            if hasattr(sip_manager, 'answer_deferred_call'):
                try:
                    ok = sip_manager.answer_deferred_call(call_id)
                except Exception as exc:
                    print(f"[WA->SIP] answer_deferred_call error for {call_id}: {exc}")

            if not ok and hasattr(sip_manager, 'answer_incoming_call'):
                try:
                    ok = sip_manager.answer_incoming_call(call_id)
                except Exception as exc:
                    print(f"[WA->SIP] answer_incoming_call error for {call_id}: {exc}")

            return ok

        def on_state(account_id: int, state: str, number: str | None):
            # Initialize storage for WA start times
            if not hasattr(self, '_wa_call_start'):
                self._wa_call_start = {}
            try:
                print(f"[WA CALLBACK] A{account_id}: {state} (number: {number})")
                if state == 'CONNECTED':
                    # set start if not already
                    self._wa_call_start.setdefault(account_id, time.time())
                elif state in ('IDLE', 'UNKNOWN'):
                    # clear
                    self._wa_call_start.pop(account_id, None)
                # Build label text with optional duration
                duration_part = ''
                if state == 'CONNECTED' and account_id in self._wa_call_start:
                    elapsed = int(time.time() - self._wa_call_start[account_id])
                    mm = elapsed // 60
                    ss = elapsed % 60
                    duration_part = f" {mm:02d}:{ss:02d}"
                # Append emulator port for clarity
                port = None
                try:
                    cfgp = self.config_manager.get_account_config(account_id) or {}
                    port = cfgp.get('emulator_port')
                except Exception:
                    port = None
                port_part = f" (emu-{port})" if port else ''
                label_text = f"WA: {state}{(' '+number) if number else ''}{duration_part}{port_part}"
                print(f"[WA UI] A{account_id} label: {label_text}")
                self._ui_queue.put(('wa_status', (account_id, label_text, state)))
            except Exception as e:
                print(f"[WA CALLBACK] Error in on_state: {e}")
                pass
            # For matching logic adjust state name back to ONGOING semantic
            normalized_state = 'ONGOING' if state == 'CONNECTED' else state
            if normalized_state == 'ONGOING':
                print(f"[WA->SIP] WhatsApp CONNECTED detected for A{account_id}, checking deferred SIP calls...")
                pending_calls = [cid for cid, info in self._deferred_calls.items() 
                               if info.get('account_id') == account_id and not info.get('answered')]
                print(f"[WA->SIP] Found {len(pending_calls)} pending calls for A{account_id}: {pending_calls}")
                
                # Try number-based matching first
                matched_any = False
                for cid, info in list(self._deferred_calls.items()):
                    if info.get('account_id') != account_id or info.get('answered'):
                        continue
                    # Obtain SIP caller number from active_calls
                    sip_number = None
                    try:
                        call_obj = getattr(self.sip_manager, 'active_calls', {}).get(cid)
                        if call_obj:
                            sip_number = call_obj.get('caller_number')
                    except Exception:
                        sip_number = None
                    
                    print(f"[WA->SIP] Call {cid}: WA number={number}, SIP number={sip_number}")
                    
                    number_match = False
                    if number and sip_number:
                        # Normalize by stripping leading + and zeros
                        def norm(n):
                            return n.lstrip('+').lstrip('0')
                        if norm(number) == norm(sip_number):
                            number_match = True
                            print(f"[WA->SIP] Number match found for call {cid}")
                    
                    # Decide whether to answer: match if number matches OR no number available at all
                    if number and sip_number and not number_match:
                        print(f"[WA->SIP] Skipping call {cid} - number mismatch")
                        continue  # wait for correct number
                    
                    print(f"[WA->SIP] Attempting to answer deferred SIP call {cid}...")
                    try:
                        ok = _attempt_sip_answer(cid)
                        if ok:
                            info['answered'] = True
                            matched_any = True
                            detail = f"number {number}" if number else "no number match"
                            self._update_status(f"✅ Deferred call {cid} answered (Acct {account_id}) via WA CONNECTED ({detail})")
                            print(f"[WA->SIP] Successfully answered call {cid}")
                        else:
                            print(f"[WA->SIP] Failed to answer call {cid} - method returned False")
                    except Exception as e:
                        print(f"[WA->SIP] Deferred answer error {cid}: {e}")
                
                # Fallback: if nothing answered and we had a number, maybe SIP number extraction failed -> answer first pending
                if not matched_any and pending_calls:
                    print(f"[WA->SIP] No number matches, trying fallback for first pending call...")
                    for cid, info in list(self._deferred_calls.items()):
                        if info.get('account_id') == account_id and not info.get('answered'):
                            print(f"[WA->SIP] Fallback: attempting to answer call {cid}")
                            try:
                                ok = _attempt_sip_answer(cid)
                                if ok:
                                    info['answered'] = True
                                    self._update_status(f"✅ Deferred call {cid} answered fallback (Acct {account_id})")
                                    print(f"[WA->SIP] Fallback successful for call {cid}")
                                    break
                                else:
                                    print(f"[WA->SIP] Fallback failed for call {cid} - method returned False")
                            except Exception as e:
                                print(f"[WA->SIP] Deferred fallback error {cid}: {e}")
                
                if not pending_calls:
                    print(f"[WA->SIP] No pending SIP calls found for A{account_id}")

        monitor.set_callback(on_state)

        # Map account -> emulator_port from config (start after callback is in place)
        accounts = self.config_manager.config.get("accounts", {})
        account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])

        for aid in account_ids:
            try:
                cfg = self.config_manager.get_account_config(aid) or {}
                port = cfg.get('emulator_port')
                if port:
                    monitor.start_monitoring(aid, port)
            except Exception:
                pass

        # Idle loop just maintains linkage and cleans answered calls
        while True:
            try:
                # Cleanup answered entries occasionally
                for cid, info in list(self._deferred_calls.items()):
                    if info.get('answered'):
                        # Remove after short grace period
                        if time.time() - info.get('ts', time.time()) > 70:
                            self._deferred_calls.pop(cid, None)
                time.sleep(2.0)
            except Exception as e:
                print(f"Notification loop error: {e}")
                time.sleep(3)

    def _init_speech_recognition(self):
        """Initialize Vosk speech recognition system"""
        if not VOSK_AVAILABLE:
            print("[SPEECH] Vosk not available - speech recognition disabled")
            self.vosk_model = None
            self.speech_device_id = None
            return
        
        try:
            # Set up Vosk model
            model_path = Path("vosk-model-en-us-0.22-lgraph")
            if not model_path.exists():
                print("[SPEECH] Vosk model not found - speech recognition disabled")
                self.vosk_model = None
                return
            
            self.vosk_model = vosk.Model(str(model_path))
            print("[SPEECH] Vosk model loaded successfully")
            
            # Find VoiceMeeter Out B2 device
            devices = sd.query_devices()
            self.speech_device_id = None
            
            for i, device in enumerate(devices):
                if "Voicemeeter Out B2 in device['name'] and device['max_input_channels'] > 0:
                    self.speech_device_id = i
                    print(f"[SPEECH] Found VoiceMeeter Out B2: Device {i} - {device['name']}")
                    break
            
            if self.speech_device_id is None:
                print("[SPEECH] VoiceMeeter Out B2 not found - speech recognition disabled")
                
            # Speech recognition parameters
            self.speech_sample_rate = 16000
            self.speech_block_size = 1024
            
            # Trigger phrases for auto-answer
            self.trigger_phrases = [
                "hello", "hi", "hey", "yes", "ello", "llo", "ooo", "ok", "oo", "o", "ha", "hal",
                "speaking", "here", "okey", "listening", "go ahead"
            ]

        except Exception as e:
            print(f"[SPEECH] Error initializing speech recognition: {e}")
            self.vosk_model = None
            self.speech_device_id = None
    
    def _start_speech_recognition_for_call(self, call_id, account_id, caller_display):
        """Start speech recognition for an incoming call"""
        if not self.vosk_model or self.speech_device_id is None:
            # Fallback: answer immediately if speech recognition not available
            self._update_status(f"⚠ Speech recognition not available - answering immediately")
            self._answer_call_with_speech_trigger(call_id, account_id, "fallback")
            return
        
        try:
            self._update_status(f"🎤 Starting speech detection for call from {caller_display}")
            
            # Create recognizer for this call
            recognizer = vosk.KaldiRecognizer(self.vosk_model, self.speech_sample_rate)
            
            # Start audio stream
            def audio_callback(indata, frames, time, status):
                if status:
                    print(f"[SPEECH] Audio callback status: {status}")
                
                # Check if recognition is still active for this call
                if call_id not in self._speech_recognition_active:
                    return
                
                try:
                    # Convert audio data for Vosk
                    audio_data = indata[:, 0] if indata.shape[1] > 0 else indata.flatten()
                    audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
                    
                    # Process with Vosk
                    if recognizer.AcceptWaveform(audio_bytes):
                        result = recognizer.Result()
                        result_dict = json.loads(result)
                        text = result_dict.get('text', '').lower().strip()
                        
                        if text:
                            self._update_status(f"🎤 Recognized: '{text}'")
                            
                            # Check for trigger phrases
                            for phrase in self.trigger_phrases:
                                if phrase in text:
                                    self._update_status(f"✓ Trigger detected: '{phrase}' - answering call")
                                    self._answer_call_with_speech_trigger(call_id, account_id, phrase)
                                    return
                    
                except Exception as e:
                    print(f"[SPEECH] Audio processing error: {e}")
            
            # Start audio stream
            stream = sd.InputStream(
                device=self.speech_device_id,
                channels=1,
                samplerate=self.speech_sample_rate,
                blocksize=self.speech_block_size,
                callback=audio_callback,
                dtype=np.float32
            )
            
            stream.start()
            self._speech_recognition_active[call_id] = True
            self._speech_audio_streams[call_id] = stream
            
            # Set timeout for speech recognition (45 seconds - longer since WhatsApp is already ringing)
            def speech_timeout():
                time.sleep(45)
                if call_id in self._speech_recognition_active:
                    self._update_status(f"⏰ Speech detection timeout - SIP call not answered")
                    self._update_status(f"💡 WhatsApp call may still be ringing - you can answer manually")
                    self._stop_speech_recognition_for_call(call_id)
            
            threading.Thread(target=speech_timeout, daemon=True).start()
            
        except Exception as e:
            print(f"[SPEECH] Error starting speech recognition: {e}")
            self._update_status(f"✗ Speech recognition error - answering immediately")
            self._answer_call_with_speech_trigger(call_id, account_id, "error_fallback")
    
    def _answer_call_with_speech_trigger(self, call_id, account_id, trigger_phrase):
        """Answer the SIP call after speech trigger detection (WhatsApp already dialed)"""
        try:
            # Stop speech recognition for this call
            self._stop_speech_recognition_for_call(call_id)
            
            # Answer the SIP call (WhatsApp call should already be ringing)
            if hasattr(self.sip_manager, 'answer_incoming_call'):
                success = self.sip_manager.answer_incoming_call(call_id)
                if success:
                    self._update_status(f"✅ SIP call answered for A{account_id} (trigger: '{trigger_phrase}')")
                    self._update_status(f"🔗 Audio connected! WhatsApp call should already be active.")
                    
                    # Mark as answered
                    if call_id in self._deferred_calls:
                        self._deferred_calls[call_id]['answered'] = True
                        
                else:
                    self._update_status(f"✗ Failed to answer SIP call for A{account_id}")
            else:
                self._update_status(f"⚠ SIP call answer not supported")
                
        except Exception as e:
            self._update_status(f"✗ Error answering call: {e}")
        finally:
            # Clean up deferred call
            if call_id in self._deferred_calls:
                del self._deferred_calls[call_id]
    
    def _stop_speech_recognition_for_call(self, call_id):
        """Stop speech recognition for a specific call"""
        try:
            if call_id in self._speech_recognition_active:
                del self._speech_recognition_active[call_id]
            
            if call_id in self._speech_audio_streams:
                stream = self._speech_audio_streams[call_id]
                stream.stop()
                stream.close()
                del self._speech_audio_streams[call_id]
                
        except Exception as e:
            print(f"[SPEECH] Error stopping speech recognition: {e}")

if __name__ == "__main__":
    # Optionally hide the console window on Windows to avoid extra terminal showing with the GUI
    try:
        if platform.system() == 'Windows':
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass

    # Create main window
    root = tk.Tk()
    root.title("Windows Desktop SIP Dialer - Auto Volume Mixer Integration")
    root.geometry("1000x600")
    root.minsize(800, 400)
    
    # Create application
    app = SipDialerApp(root)
    
    # Setup close event
    def on_closing():
        try:
            # Stop all speech recognition
            if hasattr(app, '_speech_audio_streams'):
                for call_id in list(app._speech_audio_streams.keys()):
                    app._stop_speech_recognition_for_call(call_id)
                print("? Stopped speech recognition")

            # Shutdown SIP manager
            if hasattr(app, 'sip_manager'):
                app.sip_manager.shutdown()
                print("? SIP Manager shutdown")

            # Stop per-account audio workers
            if hasattr(app, 'account_audio_manager'):
                app.account_audio_manager.stop_all()
                print("? Stopped account audio workers")
                
        except Exception as e:
            print(f"Cleanup error: {e}")
        finally:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Start GUI
    root.mainloop()
