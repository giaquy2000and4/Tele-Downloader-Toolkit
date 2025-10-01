# !/usr/bin/env python3
"""
Telegram Media Downloader - CustomTkinter GUI
Theme: Black-Cyan Dark Mode
Tích hợp hoàn toàn với downloader.py gốc
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any # Thêm 'Any' vào đây
import threading
import sys
import os

# Import từ file downloader.py gốc
from downloader import (
    TelegramDownloader,
    StateManager,
    load_env,
    save_env,
    ensure_env_exists,
    get_current_account_index,
    get_account_config,
    set_current_account_index,
    pick_account_index,
    purge_session_files_for,
    ENV_TEMPLATE
)

# Thêm các lỗi Telethon cần thiết
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
    FloodWaitError,
)


class TelegramDownloaderGUI:
    def __init__(self):
        # Cấu hình theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Main window
        self.root = ctk.CTk()
        self.root.title("Telegram Media Downloader")
        self.root.geometry("950x750")
        self.root.minsize(850, 650)

        # Custom colors (Black-Cyan theme)
        self.colors = {
            'bg': '#0a0e14',
            'card': '#151b24',
            'accent': '#00d9ff',
            'accent_hover': '#00b8d4',
            'text': '#ffffff',
            'text_dim': '#7a8896',
            'success': '#00ff9f',
            'warning': '#ffa500',
            'error': '#ff4757',
        }

        # Đường dẫn .env
        self.env_path = Path(".env")
        ensure_env_exists(self.env_path)

        # Variables
        self.current_screen = "login"
        self.envd = load_env(self.env_path)
        self.current_account_idx = get_current_account_index(self.envd)
        self.downloader: Optional[TelegramDownloader] = None
        self.download_thread = None
        self.is_downloading = False
        self.stop_flag = False
        self.active_loop: Optional[asyncio.AbstractEventLoop] = None  # Lưu event loop đang hoạt động

        # Stats tracking
        self.stats = {
            'total_found': 0,
            'images_found': 0,
            'videos_found': 0,
            'downloaded': 0,
            'skipped': 0,
            'errors': 0,
            'total_size': 0,
        }

        # Media list và source info
        self.media_list = []
        self.current_source_type = None
        self.current_filter = "3"  # 1=photos, 2=videos, 3=both
        self.selected_dialogs = []
        self.all_dialogs_info: List[Dict[str, Any]] = [] # To store all fetched dialogs for search/filter

        # Configure root
        self.root.configure(fg_color=self.colors['bg'])

        # Main container
        self.main_container = ctk.CTkFrame(self.root, fg_color=self.colors['bg'])
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Show initial screen
        self.show_login_screen()

        # Protocol cho đóng cửa sổ
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def clear_screen(self):
        """Xóa tất cả widgets trong main container"""
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def load_accounts_from_env(self) -> List[Dict]:
        """Load danh sách tài khoản từ .env"""
        accounts = []
        idxs = sorted({
            int(k.split("_")[1])
            for k in self.envd.keys()
            if k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()
        })

        for idx in idxs:
            phone = self.envd.get(f"ACCOUNT_{idx}_PHONE", "")
            if phone:
                accounts.append({
                    'id': idx,
                    'phone': phone,
                    'status': 'active' if idx == self.current_account_idx else 'inactive'
                })
        return accounts

    # ==================== LOGIN SCREEN ====================
    def show_login_screen(self):
        self.clear_screen()
        self.current_screen = "login"

        # Reload env
        self.envd = load_env(self.env_path)
        self.current_account_idx = get_current_account_index(self.envd)

        # Header
        header = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        header.pack(fill="x", pady=(0, 20))

        title = ctk.CTkLabel(
            header,
            text="TELEGRAM MEDIA DOWNLOADER",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self.colors['accent']
        )
        title.pack(pady=10)

        subtitle = ctk.CTkLabel(
            header,
            text="Multi-account • Auto-resume • Fast Download",
            font=ctk.CTkFont(size=12),
            text_color=self.colors['text_dim']
        )
        subtitle.pack()

        # Scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(
            self.main_container,
            fg_color=self.colors['bg']
        )
        scroll_frame.pack(fill="both", expand=True)

        # Existing accounts
        accounts = self.load_accounts_from_env()
        if accounts:
            accounts_card = self._create_card(scroll_frame, "Existing Accounts")

            for acc in accounts:
                acc_frame = ctk.CTkFrame(accounts_card, fg_color=self.colors['card'])
                acc_frame.pack(fill="x", pady=5, padx=15)

                info_frame = ctk.CTkFrame(acc_frame, fg_color="transparent")
                info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

                ctk.CTkLabel(
                    info_frame,
                    text=f"Account #{acc['id']}",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=self.colors['text']
                ).pack(anchor="w")

                # Mask số điện thoại
                masked = acc['phone'][:3] + "****" + acc['phone'][-4:] if len(acc['phone']) > 7 else acc['phone']
                ctk.CTkLabel(
                    info_frame,
                    text=masked,
                    font=ctk.CTkFont(size=11),
                    text_color=self.colors['text_dim']
                ).pack(anchor="w")

                # Status indicator
                status_color = self.colors['success'] if acc['status'] == 'active' else self.colors['text_dim']
                ctk.CTkLabel(
                    info_frame,
                    text=f"● {acc['status']}",
                    font=ctk.CTkFont(size=10),
                    text_color=status_color
                ).pack(anchor="w")

                ctk.CTkButton(
                    acc_frame,
                    text="Select",
                    width=100,
                    fg_color=self.colors['accent'],
                    hover_color=self.colors['accent_hover'],
                    command=lambda idx=acc['id']: self.select_account(idx)
                ).pack(side="right", padx=10, pady=10)

        # Add new account
        add_card = self._create_card(scroll_frame, "Add New Account")

        form_frame = ctk.CTkFrame(add_card, fg_color="transparent")
        form_frame.pack(fill="both", padx=15, pady=(0, 15))

        # Phone
        ctk.CTkLabel(form_frame, text="Phone Number:", text_color=self.colors['text']).pack(anchor="w", pady=(5, 0))
        self.phone_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="+84123456789",
            fg_color=self.colors['card'],
            border_color=self.colors['accent']
        )
        self.phone_entry.pack(fill="x", pady=(0, 10))

        # API ID
        ctk.CTkLabel(form_frame, text="API ID:", text_color=self.colors['text']).pack(anchor="w", pady=(5, 0))
        self.api_id_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Get from https://my.telegram.org",
            fg_color=self.colors['card'],
            border_color=self.colors['accent']
        )
        self.api_id_entry.pack(fill="x", pady=(0, 10))

        # API Hash
        ctk.CTkLabel(form_frame, text="API Hash:", text_color=self.colors['text']).pack(anchor="w", pady=(5, 0))
        self.api_hash_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Get from https://my.telegram.org",
            fg_color=self.colors['card'],
            border_color=self.colors['accent']
        )
        self.api_hash_entry.pack(fill="x", pady=(0, 10))

        # Download Directory
        dir_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        dir_frame.pack(fill="x", pady=(5, 10))

        ctk.CTkLabel(dir_frame, text="Download Directory:", text_color=self.colors['text']).pack(anchor="w")

        dir_input_frame = ctk.CTkFrame(dir_frame, fg_color="transparent")
        dir_input_frame.pack(fill="x", pady=(5, 0))

        self.download_dir_entry = ctk.CTkEntry(
            dir_input_frame,
            placeholder_text="downloads",
            fg_color=self.colors['card'],
            border_color=self.colors['accent']
        )
        self.download_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            dir_input_frame,
            text="Browse",
            width=80,
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            command=self.browse_directory
        ).pack(side="right")

        # Login button
        ctk.CTkButton(
            form_frame,
            text="Login & Continue",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=self.handle_login
        ).pack(fill="x", pady=(10, 0))

        # Bottom buttons (kept for now, could be moved to a "settings" screen in a larger refactor)
        btn_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        btn_frame.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(
            btn_frame,
            text="Logout Current",
            fg_color=self.colors['warning'],
            hover_color="#e69500",
            command=self.handle_logout_current
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="Reset Config",
            fg_color=self.colors['error'],
            hover_color="#cc3a47",
            command=self.handle_reset
        ).pack(side="left", padx=5)

    # ==================== SOURCE SELECTION SCREEN ====================
    def show_source_screen(self):
        self.clear_screen()
        self.current_screen = "source"

        # Header
        header_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        header_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            header_frame,
            text="Select Download Source",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['text']
        ).pack(side="left")

        ctk.CTkButton(
            header_frame,
            text="Logout",
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            command=self.handle_logout_and_return
        ).pack(side="right")

        # Source options grid
        options_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        options_frame.pack(fill="both", expand=True)

        options_frame.grid_columnconfigure(0, weight=1)
        options_frame.grid_columnconfigure(1, weight=1)
        options_frame.grid_rowconfigure(0, weight=1)
        options_frame.grid_rowconfigure(1, weight=1)

        # Saved Messages
        self._create_source_card(
            options_frame, 0, 0,
            "Saved Messages",
            "Download from your saved messages",
            self.colors['accent'],
            lambda: self.select_source("saved")
        )

        # Select Dialogs
        self._create_source_card(
            options_frame, 0, 1,
            "Select Dialogs",
            "Choose specific chats/channels",
            "#9b59b6", # Purple-ish
            lambda: self.select_source("dialogs")
        )

        # All Dialogs
        self._create_source_card(
            options_frame, 1, 0,
            "All Dialogs",
            "Scan all available sources",
            "#2ecc71", # Green-ish
            lambda: self.select_source("all")
        )

        # Continue Last
        self._create_source_card(
            options_frame, 1, 1,
            "Continue Last",
            "Resume previous session",
            "#e67e22", # Orange-ish
            lambda: self.select_source("continue")
        )

    # ==================== DIALOGS SELECTION SCREEN ====================
    def show_dialogs_screen(self):
        self.clear_screen()
        self.current_screen = "dialogs"

        # Header
        header_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        header_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            header_frame,
            text="Select Dialogs",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['text']
        ).pack(side="left")

        ctk.CTkButton(
            header_frame,
            text="Back",
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            command=self.show_source_screen
        ).pack(side="right")

        # Loading message
        loading = ctk.CTkLabel(
            self.main_container,
            text="Loading dialogs...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim']
        )
        loading.pack(pady=50)

        # Fetch dialogs trong thread
        threading.Thread(target=self._fetch_dialogs_thread, daemon=True).start()

    def _fetch_dialogs_thread(self):
        """Fetch dialogs trong background thread"""
        try:
            # Sử dụng lại event loop đã lưu
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for fetching dialogs.")

            asyncio.set_event_loop(loop)  # Gán lại event loop hiện tại
            dialogs = loop.run_until_complete(self._fetch_dialogs_async())
            self.all_dialogs_info = dialogs # Store all dialogs

            # Update UI trong main thread
            self.root.after(0, lambda d=dialogs: self._display_dialogs(d))
        except Exception as e:
            error_msg = f"Failed to fetch dialogs: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))

    async def _fetch_dialogs_async(self):
        """Fetch dialogs qua Telethon"""
        # Đảm bảo đã connect
        if not self.downloader or not self.downloader.client.is_connected():
            # This should ideally not happen if flow is correct, but as a safeguard
            self.root.after(0, lambda: messagebox.showerror("Error", "Telethon client not connected!"))
            return []

        dialogs = []
        idx = 0
        async for d in self.downloader.client.iter_dialogs():
            entity = d.entity
            etype = entity.__class__.__name__
            title = (getattr(d, "name", None) or getattr(entity, "title", None)
                     or getattr(entity, "first_name", None) or "Unknown").strip()
            idx += 1
            dialogs.append({
                "index": idx,
                "dialog": d,
                "entity": entity,
                "title": title,
                "type": etype,
            })

        return dialogs

    def _display_dialogs(self, dialogs):
        """Hiển thị danh sách dialogs"""
        self.clear_screen()

        # Header
        header_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        header_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            header_frame,
            text=f"Select Dialogs ({len(dialogs)} found)",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['text']
        ).pack(side="left")

        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        ctk.CTkButton(
            btn_frame,
            text="Continue",
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=lambda: self._continue_with_selected_dialogs(dialogs)
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="Back",
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            command=self.show_source_screen
        ).pack(side="left")

        # Search and Select All/Deselect All
        search_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 10))

        self.dialog_search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Search dialogs...",
            fg_color=self.colors['card'],
            border_color=self.colors['accent']
        )
        self.dialog_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.dialog_search_entry.bind("<KeyRelease>", self._on_dialog_search_key_release)

        self.select_all_btn = ctk.CTkButton(
            search_frame,
            text="Select All",
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            command=self._select_all_dialogs
        )
        self.select_all_btn.pack(side="left", padx=5)

        self.deselect_all_btn = ctk.CTkButton(
            search_frame,
            text="Deselect All",
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            command=self._deselect_all_dialogs
        )
        self.deselect_all_btn.pack(side="left", padx=5)

        # Scrollable list
        self.dialog_scroll_frame = ctk.CTkScrollableFrame(
            self.main_container,
            fg_color=self.colors['bg']
        )
        self.dialog_scroll_frame.pack(fill="both", expand=True)

        self._render_dialog_list(dialogs)

    def _render_dialog_list(self, dialogs_to_display: List[Dict[str, Any]]):
        """Renders the dialog list within the scrollable frame."""
        # Clear existing checkboxes
        for widget in self.dialog_scroll_frame.winfo_children():
            widget.destroy()

        self.dialog_checkboxes = [] # Reset for new render
        for dialog in dialogs_to_display:
            dialog_frame = ctk.CTkFrame(self.dialog_scroll_frame, fg_color=self.colors['card'])
            dialog_frame.pack(fill="x", pady=3, padx=5)

            var = ctk.IntVar()
            checkbox = ctk.CTkCheckBox(
                dialog_frame,
                text="",
                variable=var,
                checkbox_width=20,
                checkbox_height=20,
                fg_color=self.colors['accent'],
                hover_color=self.colors['accent_hover']
            )
            checkbox.pack(side="left", padx=10, pady=10)

            info_frame = ctk.CTkFrame(dialog_frame, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True)

            ctk.CTkLabel(
                info_frame,
                text=dialog['title'],
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=self.colors['text'],
                anchor="w"
            ).pack(fill="x")

            ctk.CTkLabel(
                info_frame,
                text=f"Type: {dialog['type']}",
                font=ctk.CTkFont(size=10),
                text_color=self.colors['text_dim'],
                anchor="w"
            ).pack(fill="x")

            self.dialog_checkboxes.append((var, dialog))

    def _on_dialog_search_key_release(self, event=None):
        """Filters the dialog list based on search entry content."""
        search_term = self.dialog_search_entry.get().strip().lower()
        if search_term:
            filtered_dialogs = [
                d for d in self.all_dialogs_info
                if search_term in d['title'].lower() or search_term in d['type'].lower()
            ]
        else:
            filtered_dialogs = self.all_dialogs_info
        self._render_dialog_list(filtered_dialogs)

    def _select_all_dialogs(self):
        """Selects all currently displayed dialogs."""
        for var, _ in self.dialog_checkboxes:
            var.set(1)

    def _deselect_all_dialogs(self):
        """Deselects all currently displayed dialogs."""
        for var, _ in self.dialog_checkboxes:
            var.set(0)

    def _continue_with_selected_dialogs(self, dialogs):
        """Tiếp tục với dialogs đã chọn"""
        selected = [d for var, d in self.dialog_checkboxes if var.get() == 1]

        if not selected:
            messagebox.showwarning("No Selection", "Please select at least one dialog!")
            return

        self.selected_dialogs = [d['entity'] for d in selected]
        self.scan_and_show_filter()

    # ==================== FILTER SCREEN ====================
    def show_filter_screen(self):
        self.clear_screen()
        self.current_screen = "filter"

        # Header
        header_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        header_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            header_frame,
            text="Select Media Type",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['text']
        ).pack(side="left")

        ctk.CTkButton(
            header_frame,
            text="Back",
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            command=self.show_source_screen
        ).pack(side="right")

        # Stats card
        stats_card = self._create_card(self.main_container, "Current Statistics")
        stats_grid = ctk.CTkFrame(stats_card, fg_color="transparent")
        stats_grid.pack(fill="x", pady=10, padx=15)

        for i in range(4):
            stats_grid.grid_columnconfigure(i, weight=1)

        self._create_stat_box(stats_grid, 0, str(self.stats['images_found']), "Photos", self.colors['accent'])
        self._create_stat_box(stats_grid, 1, str(self.stats['videos_found']), "Videos", "#9b59b6")
        self._create_stat_box(stats_grid, 2, str(self.stats['total_found']), "Total", "#2ecc71")

        # Size calculation
        size_str = self._format_size(self.stats['total_size'])
        self._create_stat_box(stats_grid, 3, size_str, "Size", "#e67e22")

        # Spacer
        ctk.CTkLabel(self.main_container, text="", fg_color=self.colors['bg']).pack(pady=10)

        # Filter options
        options_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        options_frame.pack(fill="both", expand=True)

        for i in range(3):
            options_frame.grid_columnconfigure(i, weight=1)
        options_frame.grid_rowconfigure(0, weight=1)

        self._create_source_card(
            options_frame, 0, 0,
            "Photos Only",
            f"Download {self.stats['images_found']} photos",
            self.colors['accent'],
            lambda: self.start_download("1")
        )

        self._create_source_card(
            options_frame, 0, 1,
            "Videos Only",
            f"Download {self.stats['videos_found']} videos",
            "#9b59b6",
            lambda: self.start_download("2")
        )

        self._create_source_card(
            options_frame, 0, 2,
            "Both",
            f"Download all {self.stats['total_found']} files",
            "#2ecc71",
            lambda: self.start_download("3")
        )

    # ==================== DOWNLOAD SCREEN ====================
    def show_download_screen(self):
        self.clear_screen()
        self.current_screen = "download"

        # Header
        header_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['bg'])
        header_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            header_frame,
            text="Downloading Media",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['text']
        ).pack(side="left")

        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        self.pause_btn = ctk.CTkButton(
            btn_frame,
            text="Pause",
            fg_color=self.colors['warning'],
            hover_color="#e69500",
            command=self.toggle_download
        )
        self.pause_btn.pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="Stop",
            fg_color=self.colors['error'],
            hover_color="#cc3a47",
            command=self.stop_download
        ).pack(side="left")

        # Progress card
        progress_card = ctk.CTkFrame(self.main_container, fg_color=self.colors['card'], corner_radius=10)
        progress_card.pack(fill="both", expand=True)

        content_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Progress bar
        progress_header = ctk.CTkFrame(content_frame, fg_color="transparent")
        progress_header.pack(fill="x")

        ctk.CTkLabel(
            progress_header,
            text="Progress",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors['text']
        ).pack(side="left")

        self.progress_label = ctk.CTkLabel(
            progress_header,
            text="0/0",
            font=ctk.CTkFont(size=12),
            text_color=self.colors['text_dim']
        )
        self.progress_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            content_frame,
            height=20,
            progress_color=self.colors['accent']
        )
        self.progress_bar.pack(fill="x", pady=(5, 20))
        self.progress_bar.set(0)

        # Stats grid
        stats_grid = ctk.CTkFrame(content_frame, fg_color="transparent")
        stats_grid.pack(fill="x", pady=10)

        for i in range(4):
            stats_grid.grid_columnconfigure(i, weight=1)

        self.stat_boxes = {}
        self._create_download_stat_box(stats_grid, 0, "0", "Downloaded", self.colors['success'], 'downloaded')
        self._create_download_stat_box(stats_grid, 1, "0", "Skipped", self.colors['warning'], 'skipped')
        self._create_download_stat_box(stats_grid, 2, "0", "Errors", self.colors['error'], 'errors')
        self._create_download_stat_box(stats_grid, 3, "0 B", "Size", self.colors['accent'], 'size')

        # Status info
        status_frame = ctk.CTkFrame(content_frame, fg_color=self.colors['bg'], corner_radius=8)
        status_frame.pack(fill="x", pady=(20, 0))

        ctk.CTkLabel(
            status_frame,
            text="Current Status",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors['text']
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=self.colors['text_dim'],
            justify="left",
            anchor="w"
        )
        self.status_label.pack(anchor="w", fill="x", padx=30, pady=(0, 15))

        # Download Log
        log_frame = ctk.CTkFrame(content_frame, fg_color=self.colors['bg'], corner_radius=8)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))

        ctk.CTkLabel(
            log_frame,
            text="Download Log",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors['text']
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.log_textbox = ctk.CTkTextbox(
            log_frame,
            fg_color=self.colors['card'],
            text_color=self.colors['text_dim'],
            wrap="word",
            height=150
        )
        self.log_textbox.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.log_textbox.configure(state="disabled") # Make it read-only

    def _create_download_stat_box(self, parent, col, value, label, color, key):
        """Tạo stat box cho download screen"""
        box = ctk.CTkFrame(parent, fg_color=self.colors['bg'], corner_radius=8)
        box.grid(row=0, column=col, padx=5, sticky="ew")

        value_label = ctk.CTkLabel(
            box,
            text=value,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=color
        )
        value_label.pack(pady=(15, 0))

        ctk.CTkLabel(
            box,
            text=label,
            font=ctk.CTkFont(size=11),
            text_color=self.colors['text_dim']
        ).pack(pady=(0, 15))

        self.stat_boxes[key] = value_label

    # ==================== HELPER METHODS ====================
    def _create_card(self, parent, title):
        """Tạo card container"""
        card = ctk.CTkFrame(parent, fg_color=self.colors['card'], corner_radius=10)
        card.pack(fill="x", pady=10)

        if title:
            title_label = ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.colors['text']
            )
            title_label.pack(anchor="w", padx=15, pady=(15, 10))

        return card

    def _create_source_card(self, parent, row, col, title, subtitle, color, command):
        """Tạo card cho source selection"""
        card = ctk.CTkFrame(
            parent,
            fg_color=color,
            corner_radius=10,
            cursor="hand2"
        )
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        card.bind("<Button-1>", lambda e: command())

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(expand=True)

        title_label = ctk.CTkLabel(
            content,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="white"
        )
        title_label.pack(pady=(20, 5))
        title_label.bind("<Button-1>", lambda e: command())

        subtitle_label = ctk.CTkLabel(
            content,
            text=subtitle,
            font=ctk.CTkFont(size=11),
            text_color="#e0e0e0"
        )
        subtitle_label.pack(pady=(0, 20))
        subtitle_label.bind("<Button-1>", lambda e: command())

    def _create_stat_box(self, parent, col, value, label, color):
        """Tạo stat box"""
        box = ctk.CTkFrame(parent, fg_color=self.colors['bg'], corner_radius=8)
        box.grid(row=0, column=col, padx=5, sticky="ew")

        ctk.CTkLabel(
            box,
            text=value,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=color
        ).pack(pady=(15, 0))

        ctk.CTkLabel(
            box,
            text=label,
            font=ctk.CTkFont(size=11),
            text_color=self.colors['text_dim']
        ).pack(pady=(0, 15))

    def _format_size(self, size_bytes):
        """Format bytes thành human readable"""
        if size_bytes == 0:
            return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        size = float(size_bytes)
        while size >= 1024 and i < len(units) - 1:
            size /= 1024
            i += 1
        return f"{size:.1f} {units[i]}"

    def _show_error(self, message):
        """Hiển thị error message"""
        messagebox.showerror("Error", message)
        self.show_login_screen()  # Fallback to login screen on error

    def _append_log(self, message: str, color: Optional[str] = None):
        """Appends a message to the download log textbox."""
        if self.current_screen == "download" and hasattr(self, 'log_textbox'):
            self.log_textbox.configure(state="normal")
            if color:
                self.log_textbox.insert("end", f"{message}\n", color)
            else:
                self.log_textbox.insert("end", f"{message}\n")
            self.log_textbox.see("end") # Scroll to bottom
            self.log_textbox.configure(state="disabled")

    # ==================== EVENT HANDLERS ====================
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.download_dir_entry.delete(0, "end")
            self.download_dir_entry.insert(0, directory)

    def handle_login(self):
        """Xử lý login và lưu account mới"""
        phone = self.phone_entry.get().strip()
        api_id = self.api_id_entry.get().strip()
        api_hash = self.api_hash_entry.get().strip()
        download_dir = self.download_dir_entry.get().strip() or "downloads"

        if not all([phone, api_id, api_hash]):
            messagebox.showwarning("Missing Info", "Please fill Phone, API ID, and API Hash!")
            return

        try:
            api_id_int = int(api_id)
        except ValueError:
            messagebox.showerror("Invalid API ID", "API ID must be a number!")
            return

        # Tìm index mới
        existing_idxs = [int(k.split("_")[1]) for k in self.envd.keys()
                         if k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()]
        new_idx = 1 if not existing_idxs else max(existing_idxs) + 1

        # Lưu vào envd
        self.envd[f"ACCOUNT_{new_idx}_PHONE"] = phone
        self.envd[f"ACCOUNT_{new_idx}_API_ID"] = str(api_id_int)
        self.envd[f"ACCOUNT_{new_idx}_API_HASH"] = api_hash
        self.envd[f"ACCOUNT_{new_idx}_DOWNLOAD_DIR"] = download_dir
        self.envd = set_current_account_index(self.envd, new_idx)

        # Save to file
        save_env(self.env_path, self.envd)

        self.current_account_idx = new_idx

        # Tạo downloader và connect trong thread
        self._init_downloader_and_connect()

    def _init_downloader_and_connect(self):
        """Initialize downloader và connect trong background"""
        cfg = get_account_config(self.envd, self.current_account_idx)

        # Ensure a fresh event loop for the downloader operations
        if self.active_loop and not self.active_loop.is_closed():
            self.active_loop.stop()
            self.active_loop.close()
        self.active_loop = asyncio.new_event_loop()

        # Show loading
        self.clear_screen()
        loading = ctk.CTkLabel(
            self.main_container,
            text="Connecting to Telegram...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim']
        )
        loading.pack(pady=50)

        # Connect trong thread
        threading.Thread(
            target=self._connect_thread,
            args=(cfg, self.active_loop),  # Pass the loop to the thread
            daemon=True
        ).start()

    def _connect_thread(self, cfg: Dict[str, str], loop_to_use: asyncio.AbstractEventLoop):
        """Connect to Telegram trong background thread"""
        try:
            # Set the event loop for this thread
            asyncio.set_event_loop(loop_to_use)

            # Instantiate the TelegramDownloader, it will create its client internally
            self.downloader = TelegramDownloader(
                api_id=int(cfg["API_ID"]),
                api_hash=cfg["API_HASH"],
                phone=cfg["PHONE"],
                download_dir=cfg["DOWNLOAD_DIR"],
                account_index=self.current_account_idx
            )

            # Connect the client using the provided event loop
            is_connected, status_code = loop_to_use.run_until_complete(self._connect_client_with_status())

            if is_connected:
                if status_code == "success":
                    self.root.after(0, self.show_source_screen)
                elif status_code == "need_code":
                    self.root.after(0, self._show_otp_dialog)
            # If not connected, error message would have been shown by _connect_client_with_status
            else:
                self.root.after(0, self.show_login_screen)  # Return to login if connection fails

        except Exception as e:
            error_msg = f"Connection error: {str(e)}\n\nMake sure your API credentials are correct or check your network."
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))

    async def _connect_client_with_status(self) -> Tuple[bool, str]:
        """Async function to connect client and return status"""
        if not self.downloader:
            self.root.after(0, lambda: messagebox.showerror("Error", "Downloader not initialized."))
            return False, "error"
        try:
            await self.downloader.client.connect()
            if not await self.downloader.client.is_user_authorized():
                try:
                    await self.downloader.client.send_code_request(self.downloader.phone)
                    return True, "need_code"
                except FloodWaitError as e:
                    self.root.after(0, lambda: messagebox.showerror("Connection Error",
                                                                    f"Too many attempts. Please wait {e.seconds} seconds before trying again."))
                    await self.downloader.client.disconnect()  # Disconnect on flood wait
                    return False, "flood_wait"
            else:
                return True, "success"
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Connection Error",
                                                            f"Failed to connect: {e}\nPlease check your network or API credentials."))
            try:
                if self.downloader.client.is_connected():
                    await self.downloader.client.disconnect()
            except Exception:
                pass  # Ignore errors during disconnect attempt
            return False, f"error: {str(e)}"

    def _show_otp_dialog(self):
        """Hiển thị dialog nhập OTP"""
        self.clear_screen()

        # Header
        ctk.CTkLabel(
            self.main_container,
            text="Verification Required",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['accent']
        ).pack(pady=(50, 20))

        ctk.CTkLabel(
            self.main_container,
            text="Enter the code sent to your Telegram app",
            font=ctk.CTkFont(size=12),
            text_color=self.colors['text_dim']
        ).pack(pady=10)

        # OTP Entry
        otp_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['card'])
        otp_frame.pack(pady=20, padx=100, fill="x")

        self.otp_entry = ctk.CTkEntry(
            otp_frame,
            placeholder_text="12345",
            font=ctk.CTkFont(size=16),
            justify="center",
            fg_color=self.colors['bg'],
            border_color=self.colors['accent']
        )
        self.otp_entry.pack(pady=20, padx=20, fill="x")

        # Submit button
        ctk.CTkButton(
            otp_frame,
            text="Verify",
            height=40,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=self._submit_otp
        ).pack(pady=(0, 20), padx=20, fill="x")

        # 2FA info
        ctk.CTkLabel(
            self.main_container,
            text="If you have 2FA enabled, you'll be asked for password next",
            font=ctk.CTkFont(size=10),
            text_color=self.colors['text_dim']
        ).pack(pady=10)

    def _submit_otp(self):
        """Submit OTP code"""
        code = self.otp_entry.get().strip()
        if not code:
            messagebox.showwarning("Missing Code", "Please enter the verification code")
            return

        # Show loading
        self.clear_screen()
        ctk.CTkLabel(
            self.main_container,
            text="Verifying...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim']
        ).pack(pady=50)

        # Verify trong thread
        threading.Thread(
            target=self._verify_otp_thread,
            args=(code,),
            daemon=True
        ).start()

    def _verify_otp_thread(self, code):
        """Verify OTP trong background"""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for OTP verification.")
            asyncio.set_event_loop(loop)

            async def sign_in():
                try:
                    cfg = get_account_config(self.envd, self.current_account_idx)
                    await self.downloader.client.sign_in(cfg["PHONE"], code)
                    return "success"
                except SessionPasswordNeededError:
                    return "need_password"
                except PhoneCodeInvalidError:
                    return "invalid_code"
                except PhoneCodeExpiredError:  # Handle expired code
                    return "expired_code"
                except Exception as e:
                    raise e

            result = loop.run_until_complete(sign_in())

            if result == "need_password":
                self.root.after(0, self._show_2fa_dialog)
            elif result == "success":
                self.root.after(0, self.show_source_screen)
            elif result == "invalid_code":
                error_msg = "Invalid verification code. Please try again."
                self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
                self.root.after(100, self._show_otp_dialog)
            elif result == "expired_code":  # Handle expired code in UI
                error_msg = "Verification code has expired. Please request a new one."
                self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
                self.root.after(100, self.show_login_screen)  # Go back to login to re-send code

        except Exception as e:
            error_msg = f"Verification failed: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))

    def _show_2fa_dialog(self):
        """Hiển thị dialog nhập 2FA password"""
        self.clear_screen()

        ctk.CTkLabel(
            self.main_container,
            text="Two-Factor Authentication",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['accent']
        ).pack(pady=(50, 20))

        ctk.CTkLabel(
            self.main_container,
            text="Enter your 2FA password",
            font=ctk.CTkFont(size=12),
            text_color=self.colors['text_dim']
        ).pack(pady=10)

        # Password Entry
        pw_frame = ctk.CTkFrame(self.main_container, fg_color=self.colors['card'])
        pw_frame.pack(pady=20, padx=100, fill="x")

        self.password_entry = ctk.CTkEntry(
            pw_frame,
            placeholder_text="Password",
            show="*",
            font=ctk.CTkFont(size=16),
            fg_color=self.colors['bg'],
            border_color=self.colors['accent']
        )
        self.password_entry.pack(pady=20, padx=20, fill="x")

        ctk.CTkButton(
            pw_frame,
            text="Submit",
            height=40,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=self._submit_2fa
        ).pack(pady=(0, 20), padx=20, fill="x")

    def _submit_2fa(self):
        """Submit 2FA password"""
        password = self.password_entry.get().strip()
        if not password:
            messagebox.showwarning("Missing Password", "Please enter your 2FA password")
            return

        self.clear_screen()
        ctk.CTkLabel(
            self.main_container,
            text="Verifying...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim']
        ).pack(pady=50)

        threading.Thread(
            target=self._verify_2fa_thread,
            args=(password,),
            daemon=True
        ).start()

    def _verify_2fa_thread(self, password):
        """Verify 2FA trong background"""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for 2FA verification.")
            asyncio.set_event_loop(loop)

            async def sign_in_2fa():
                try:
                    await self.downloader.client.sign_in(password=password)
                    return "success"
                except PasswordHashInvalidError:
                    return "invalid_password"
                except Exception as e:
                    raise e

            result = loop.run_until_complete(sign_in_2fa())

            if result == "success":
                self.root.after(0, self.show_source_screen)
            elif result == "invalid_password":
                error_msg = "Invalid 2FA password. Please try again."
                self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
                self.root.after(100, self._show_2fa_dialog)

        except Exception as e:
            error_msg = f"2FA verification failed: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))

    def select_account(self, idx):
        """Chọn account có sẵn"""
        self.current_account_idx = idx
        self.envd = set_current_account_index(self.envd, idx)
        save_env(self.env_path, self.envd)

        self._init_downloader_and_connect()

    def handle_logout_current(self):
        """Logout account hiện tại"""
        if self.current_account_idx == 0 or not self.downloader:
            messagebox.showinfo("No Account", "No account is currently logged in.")
            return

        if messagebox.askyesno("Confirm Logout", f"Logout account #{self.current_account_idx}?"):
            purge_session_files_for(self.current_account_idx)
            self.current_account_idx = 0  # Reset current account
            self.envd = set_current_account_index(self.envd, 0)
            save_env(self.env_path, self.envd)
            messagebox.showinfo("Logged Out", "Session files deleted. You can login again.")
            self._disconnect_and_close_loop()  # Ensure resources are cleaned up
            self.show_login_screen()

    def handle_logout_and_return(self):
        """Logout và quay về login screen"""
        if messagebox.askyesno("Confirm", "Logout and return to login screen?"):
            self._disconnect_and_close_loop()
            self.show_login_screen()

    def handle_reset(self):
        """Reset .env file"""
        if messagebox.askyesno("Confirm Reset",
                               "Reset all config? This will delete all account info and saved sessions!"):
            self.envd = {"CURRENT_ACCOUNT": "0"}
            save_env(self.env_path, self.envd)
            # Purge all session files
            try:
                session_dir = Path("sessions")
                if session_dir.exists():
                    for f in session_dir.iterdir():
                        if f.is_file() and f.name.startswith("session_"):
                            f.unlink()
            except Exception as e:
                print(f"Error purging session files: {e}")

            messagebox.showinfo("Reset", "Config and all session files have been reset!")
            self._disconnect_and_close_loop()  # Ensure resources are cleaned up
            self.show_login_screen()

    def select_source(self, source_type):
        """Xử lý lựa chọn source"""
        if not self.downloader or not self.downloader.client.is_connected():
            messagebox.showerror("Not Connected", "Please login first.")
            self.show_login_screen()
            return

        self.current_source_type = source_type

        if source_type == "saved":
            self.selected_dialogs = ['me']
            self.scan_and_show_filter()
        elif source_type == "dialogs":
            self.show_dialogs_screen()
        elif source_type == "all":
            # Show loading and fetch all dialogs
            self.clear_screen()
            loading = ctk.CTkLabel(
                self.main_container,
                text="Loading all dialogs...",
                font=ctk.CTkFont(size=14),
                text_color=self.colors['text_dim']
            )
            loading.pack(pady=50)
            threading.Thread(target=self._fetch_all_dialogs_and_scan, daemon=True).start()
        elif source_type == "continue":
            self.continue_last_session()

    def _fetch_all_dialogs_and_scan(self):
        """Fetch tất cả dialogs và scan"""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for fetching all dialogs.")
            asyncio.set_event_loop(loop)

            dialogs = loop.run_until_complete(self._fetch_dialogs_async())
            # Don't close loop here, it's the active_loop for the client

            self.selected_dialogs = [d['entity'] for d in dialogs]
            self.root.after(0, self.scan_and_show_filter)
        except Exception as e:
            error_msg = f"Failed to fetch all dialogs: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))

    def scan_and_show_filter(self):
        """Scan media và hiển thị filter screen"""
        # Show loading
        self.clear_screen()
        loading = ctk.CTkLabel(
            self.main_container,
            text=f"Scanning media from {len(self.selected_dialogs)} source(s)...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim']
        )
        loading.pack(pady=50)

        # Scan trong thread
        threading.Thread(target=self._scan_media_thread, daemon=True).start()

    def _scan_media_thread(self):
        """Scan media trong background"""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for scanning media.")
            asyncio.set_event_loop(loop)

            if self.selected_dialogs == ['me']:
                media_list = loop.run_until_complete(self.downloader.scan_saved_messages())
            else:
                media_list = loop.run_until_complete(
                    self.downloader.scan_media_in_dialogs(self.selected_dialogs)
                )

            # Don't close loop here, it's the active_loop for the client

            self.media_list = media_list
            self.stats = self.downloader.stats.copy()

            self.root.after(0, self.show_filter_screen)
        except Exception as e:
            error_msg = f"Scan error: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))

    def continue_last_session(self):
        """Tiếp tục session trước"""
        if not self.downloader:
            messagebox.showerror("Error", "Downloader not initialized.")
            return

        state = self.downloader.state
        prev = state.get_source()

        if not prev or not prev.get("type"):
            messagebox.showinfo("No Session", "No previous session found to continue.")
            self.show_source_screen()
            return

        typ = prev.get("type")
        dialog_ids_from_state = prev.get("dialog_ids", [])

        # Reconstruct selected_dialogs based on state
        if typ == "saved":
            self.selected_dialogs = ['me']
        else:  # "dialogs" or "all"
            want_ids = [int(x) for x in dialog_ids_from_state if str(x).isdigit() and int(x) != 0]
            if not want_ids:
                messagebox.showinfo("No Session", "Could not restore dialogs from previous session.")
                self.show_source_screen()
                return

            def _restore_dialogs_thread():
                try:
                    loop = self.active_loop
                    if loop is None or loop.is_closed():
                        raise RuntimeError("Active event loop is not available for restoring dialogs.")
                    asyncio.set_event_loop(loop)

                    all_dialogs_info = loop.run_until_complete(self._fetch_dialogs_async())
                    restored_entities = []
                    for d_info in all_dialogs_info:
                        if int(getattr(d_info["entity"], "id", 0)) in want_ids:
                            restored_entities.append(d_info["entity"])

                    if not restored_entities:
                        self.root.after(0, lambda: messagebox.showinfo("No Session",
                                                                       "Could not restore dialogs from previous session."))
                        self.root.after(0, self.show_source_screen)
                        return

                    self.selected_dialogs = restored_entities
                    self.current_source_type = typ  # Restore source type
                    self.root.after(0, self.scan_and_show_filter)

                except Exception as e:
                    self.root.after(0,
                                    lambda msg=f"Error restoring previous session: {e}": messagebox.showerror("Error",
                                                                                                              msg))
                    self.root.after(0, self.show_source_screen)

            threading.Thread(target=_restore_dialogs_thread, daemon=True).start()
            return  # Exit early, thread will continue flow

        self.current_source_type = typ  # Restore source type
        self.scan_and_show_filter()

    def start_download(self, filter_choice):
        """Bắt đầu download với filter đã chọn"""
        if not self.downloader:
            messagebox.showerror("Error", "Downloader not initialized.")
            return

        self.current_filter = filter_choice

        # Filter media list
        if filter_choice == "1":
            filtered = [m for m in self.media_list if m['type'] == 'photo']
        elif filter_choice == "2":
            filtered = [m for m in self.media_list if m['type'] == 'video']
        else:
            filtered = self.media_list

        if not filtered:
            messagebox.showinfo("No Media", "No media files match the selected filter.")
            return

        self.filtered_media_list = filtered
        self.is_downloading = True
        self.stop_flag = False

        # Show download screen
        self.show_download_screen()

        # Update status
        source_label = "Saved Messages" if self.selected_dialogs == ['me'] else f"{len(self.selected_dialogs)} dialogs"
        filter_label = {"1": "Photos only", "2": "Videos only", "3": "Both"}[filter_choice]

        status_text = f"• Source: {source_label}\n"
        status_text += f"• Directory: {self.downloader.download_dir}\n"
        status_text += f"• Filter: {filter_label}\n"
        status_text += f"• Status: Starting..."

        self.status_label.configure(text=status_text)
        self._append_log(f"Download started for {len(self.filtered_media_list)} files.")
        self._append_log(f"Source: {source_label}, Filter: {filter_label}")
        self._append_log(f"Download directory: {self.downloader.download_dir}")


        # Start download thread
        self.download_thread = threading.Thread(target=self._download_thread, daemon=True)
        self.download_thread.start()

    def _download_thread(self):
        """Download thread"""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for downloading.")
            asyncio.set_event_loop(loop)

            total = len(self.filtered_media_list)

            for idx, item in enumerate(self.filtered_media_list):
                if self.stop_flag:
                    self._append_log("Download stopped by user.", "red")
                    break

                # Pause handling
                while not self.is_downloading and not self.stop_flag:
                    self.root.after(0, lambda: self._append_log("Download paused...", "yellow"))
                    import time
                    time.sleep(0.5)
                    self.root.after(0, lambda: self._append_log("Resuming...", "yellow"))


                if self.stop_flag:
                    self._append_log("Download stopped by user.", "red")
                    break

                msg = item["message"]
                target_path = self.downloader._target_path_for(item)

                # Check if already exists
                if target_path.exists() and os.path.getsize(target_path) > 0:
                    self.downloader.stats['skipped'] += 1
                    self.downloader.state.mark_completed(int(msg.id))
                    self.root.after(0, lambda path=target_path.name: self._append_log(f"Skipped: {path} (already exists)"))
                else:
                    try:
                        self.root.after(0, lambda path=target_path.name: self._append_log(f"Downloading: {path}"))
                        path = loop.run_until_complete(
                            self.downloader.client.download_media(msg, file=str(target_path))
                        )
                        if path and os.path.exists(path):
                            size = os.path.getsize(path)
                            self.downloader.stats['downloaded'] += 1
                            self.downloader.stats['total_size'] += size
                            self.downloader.state.mark_completed(int(msg.id))
                            self.root.after(0, lambda path=target_path.name: self._append_log(f"Downloaded: {path}", "green"))
                        else:
                            self.downloader.stats['errors'] += 1
                            self.root.after(0, lambda path=target_path.name: self._append_log(f"Error downloading: {path}", "red"))
                    except Exception as e:
                        self.downloader.stats['errors'] += 1
                        self.root.after(0, lambda path=target_path.name, err=e: self._append_log(f"Error downloading {path}: {err}", "red"))
                        print(f"Download error (msg {msg.id}): {e}")  # Log error to console

                # Update UI
                progress = (idx + 1) / total
                curr = idx + 1
                self.root.after(0, lambda p=progress, i=curr, t=total: self._update_download_progress(p, i, t))

            # Don't close loop here, it's the active_loop for the client

            # Hoàn thành
            self.root.after(0, self._download_complete)

        except Exception as e:
            error_msg = f"Download thread error: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))

    def _update_download_progress(self, progress, current, total):
        """Update download progress trong UI"""
        if self.current_screen != "download":
            return

        self.progress_bar.set(progress)
        self.progress_label.configure(text=f"{current}/{total}")

        # Update stats
        if 'downloaded' in self.stat_boxes:
            self.stat_boxes['downloaded'].configure(text=str(self.downloader.stats['downloaded']))
        if 'skipped' in self.stat_boxes:
            self.stat_boxes['skipped'].configure(text=str(self.downloader.stats['skipped']))
        if 'errors' in self.stat_boxes:
            self.stat_boxes['errors'].configure(text=str(self.downloader.stats['errors']))
        if 'size' in self.stat_boxes:
            self.stat_boxes['size'].configure(text=self._format_size(self.downloader.stats['total_size']))

        # Update status
        source_label = "Saved Messages" if self.selected_dialogs == ['me'] else f"{len(self.selected_dialogs)} dialogs"
        filter_label = {"1": "Photos only", "2": "Videos only", "3": "Both"}[self.current_filter]

        status_text = f"• Source: {source_label}\n"
        status_text += f"• Directory: {self.downloader.download_dir}\n"
        status_text += f"• Filter: {filter_label}\n"
        status_text += f"• Status: {'Downloading...' if self.is_downloading else 'Paused'}"

        self.status_label.configure(text=status_text)

    def _download_complete(self):
        """Download hoàn thành"""
        self._append_log("Download session complete.", "blue")
        messagebox.showinfo(
            "Download Complete",
            f"Downloaded: {self.downloader.stats['downloaded']}\n"
            f"Skipped: {self.downloader.stats['skipped']}\n"
            f"Errors: {self.downloader.stats['errors']}\n"
            f"Total size: {self._format_size(self.downloader.stats['total_size'])}"
        )
        self.is_downloading = False
        self.stop_flag = False
        self.show_source_screen()

    def toggle_download(self):
        """Pause/Resume download"""
        self.is_downloading = not self.is_downloading
        if self.is_downloading:
            self.pause_btn.configure(text="Pause", fg_color=self.colors['warning'], hover_color="#e69500")
            self._append_log("Download resumed.")
        else:
            self.pause_btn.configure(text="Resume", fg_color=self.colors['accent'], hover_color=self.colors['accent_hover'])
            self._append_log("Download paused.")
        # Ensure status label reflects the new state immediately
        self._update_download_progress(self.progress_bar.get(), int(self.progress_label.cget("text").split('/')[0]),
                                       int(self.progress_label.cget("text").split('/')[1]))

    def stop_download(self):
        """Stop download"""
        if messagebox.askyesno("Confirm", "Stop download and return?"):
            self.stop_flag = True
            self.is_downloading = False
            self.pause_btn.configure(text="Pause", fg_color=self.colors['warning'], hover_color="#e69500") # Reset button state
            self._append_log("Stopping download...", "red")


            # Chờ thread kết thúc
            if self.download_thread and self.download_thread.is_alive():
                self.download_thread.join(timeout=2)

            self.root.after(0, self.show_source_screen)

    def on_closing(self):
        """Xử lý khi đóng cửa sổ"""
        if self.is_downloading:
            if messagebox.askyesno("Confirm Exit", "Download in progress. Exit anyway?"):
                self.stop_flag = True
                # Give a moment for the thread to recognize stop_flag
                if self.download_thread and self.download_thread.is_alive():
                    self.download_thread.join(timeout=1)
                self._disconnect_and_close_loop()
                self.root.destroy()
        else:
            self._disconnect_and_close_loop()
            self.root.destroy()

    def _disconnect_and_close_loop(self):
        """Disconnect Telegram client and close the active event loop."""
        if self.downloader and self.downloader.client and self.downloader.client.is_connected():
            try:
                # To disconnect safely, we need to run it within the active event loop.
                # Since the loop might not be continuously running, we execute this in a temporary context.
                if self.active_loop and not self.active_loop.is_closed():
                    # Attempt to run disconnect within the active loop if it's not already closed.
                    # We might need to briefly set the loop for the current thread.
                    current_thread_loop = None
                    try:
                        current_thread_loop = asyncio.get_event_loop()
                    except RuntimeError:  # No current event loop in this thread
                        pass

                    if current_thread_loop is not self.active_loop:
                        asyncio.set_event_loop(self.active_loop)

                    try:
                        self.active_loop.run_until_complete(self.downloader.client.disconnect())
                    except Exception as e:
                        print(f"Error during Telethon client disconnect: {e}")
                    finally:
                        if current_thread_loop:  # Restore original loop if it existed
                            asyncio.set_event_loop(current_thread_loop)
                else:
                    print("Active loop not available or closed for graceful disconnect. Client might remain connected.")
            except Exception as e:
                print(f"Error attempting client disconnect: {e}")

        if self.active_loop and not self.active_loop.is_closed():
            self.active_loop.stop()
            self.active_loop.close()
        self.active_loop = None  # Reset the loop
        self.downloader = None  # Reset downloader instance

    def run(self):
        """Chạy GUI"""
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = TelegramDownloaderGUI()
        app.run()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

