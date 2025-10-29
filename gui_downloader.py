# !/usr/bin/env python3

import customtkinter as ctk
from tkinter import filedialog, messagebox
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Callable, Union
import threading
import sys
import os
import humanize


from downloader import (
    TelegramDownloader,
    StateManager,
    load_env,
    save_env,
    ensure_env_exists,
    get_current_account_index,
    get_account_config,
    set_current_account_index,
    do_login_flow,
    do_reset_flow,
    do_logout_flow,
    find_next_account_index,  # New import for account management
    
)

from telethon.tl.types import User, Chat, Channel  # Import for type hints
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
        self.root.title("Telegram Media Tool")  # Updated title
        self.root.geometry("950x750")
        self.root.minsize(850, 650)

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
            'upload_color': '#3498db',  # New color for upload
            'upload_hover': '#2980b9',
        }

        self.env_path = Path(".env")
        ensure_env_exists(self.env_path)

        # Variables
        self.current_screen = "login"
        self.envd = load_env(self.env_path)
        self.current_account_idx = get_current_account_index(self.envd)
        self.downloader: Optional[TelegramDownloader] = None
        self.download_thread = None
        self.upload_thread = None
        self.is_downloading = False
        self.is_uploading = False
        self.stop_flag = False
        self.active_loop: Optional[asyncio.AbstractEventLoop] = None

        self._gui_event = threading.Event()
        self._gui_input_result: Any = None

        # Stats tracking (for download)
        self.stats = {
            'total_found': 0,
            'images_found': 0,
            'videos_found': 0,
            'downloaded': 0,
            'skipped': 0,
            'errors': 0,
            'total_size': 0,
        }

        self.media_list = []
        self.filtered_media_list = []
        self.current_source_type = None
        self.current_filter = "3"
        self.selected_dialogs = []  # For download targets
        self.all_dialogs_info: List[Dict[str, Any]] = []

        # Upload specific variables
        self.upload_source_path: Optional[Path] = None  # Stores path to file or folder
        self.upload_is_folder_mode: bool = False
        self.upload_destination_entity: Optional[Union[User, Chat, Channel, int, str]] = None
        self.selected_upload_dialog_title: str = "Select a destination"

        self.continue_selected_btn: Optional[ctk.CTkButton] = None
        self.start_download_btn: Optional[ctk.CTkButton] = None
        self.upload_start_btn: Optional[ctk.CTkButton] = None  # Ref for upload button

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
        # Reset references when screen is cleared
        self.continue_selected_btn = None
        self.start_download_btn = None
        self.upload_start_btn = None
        if hasattr(self, 'upload_progress_bar'): del self.upload_progress_bar
        if hasattr(self, 'upload_progress_label'): del self.upload_progress_label
        if hasattr(self, 'upload_file_entry'): del self.upload_file_entry
        if hasattr(self, 'upload_destination_display_label'): del self.upload_destination_display_label

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

    # ==================== GUI-SPECIFIC I/O FUNCTIONS ====================
    def gui_log_output(self, message: str, color_tag: Optional[str] = None):
        """Custom log function to append messages to the GUI's log textbox."""
        self.root.after(0, lambda: self._append_log(message, color_tag))

    def gui_get_input(self, prompt: str, default: Optional[str] = None, hide_input: bool = False) -> str:
        """Custom input function to get user input via a CTkToplevel dialog."""
        self._gui_input_result = None
        self._gui_event.clear()

        def show_input_dialog():
            dialog = ctk.CTkToplevel(self.root)
            dialog.title("Input Required")
            dialog.geometry("400x200")
            dialog.transient(self.root)
            dialog.grab_set()

            ctk.CTkLabel(dialog, text=prompt, text_color=self.colors['text']).pack(pady=(10, 5))

            entry = ctk.CTkEntry(dialog, placeholder_text=default or "", fg_color=self.colors['card'],
                                 border_color=self.colors['accent'])
            if hide_input:
                entry.configure(show="*")
            entry.pack(pady=5, padx=20, fill="x")
            if default:
                entry.insert(0, default)

            def submit():
                self._gui_input_result = entry.get() or default or ""
                dialog.destroy()
                self._gui_event.set()

            def cancel():
                self._gui_input_result = ""
                dialog.destroy()
                self._gui_event.set()

            ctk.CTkButton(dialog, text="Submit", command=submit, fg_color=self.colors['accent'],
                          hover_color=self.colors['accent_hover']).pack(pady=(10, 5), padx=20, fill="x")
            ctk.CTkButton(dialog, text="Cancel", command=cancel, fg_color="gray", hover_color="darkgray").pack(
                pady=(5, 10), padx=20, fill="x")

            dialog.protocol("WM_DELETE_WINDOW", cancel)

        self.root.after(0, show_input_dialog)
        self._gui_event.wait()

        return self._gui_input_result

    # ==================== LOGIN SCREEN ====================
    def show_login_screen(self):
        self.clear_screen()
        self.current_screen = "login"

        # Reload env
        self.envd = load_env(self.env_path)
        self.current_account_idx = get_current_account_index(self.envd)

        # Header
        header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))

        title = ctk.CTkLabel(
            header,
            text="TELEGRAM MEDIA TOOL",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self.colors['accent']
        )
        title.pack(pady=10)

        subtitle = ctk.CTkLabel(
            header,
            text="Multi-account • Download • Upload • Auto-resume • Fast",
            font=ctk.CTkFont(size=12),
            text_color=self.colors['text_dim']
        )
        subtitle.pack()

        # New content frame for the two-column layout
        content_grid_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        content_grid_frame.pack(fill="both", expand=True, padx=0, pady=0)

        content_grid_frame.grid_columnconfigure(0, weight=1)
        content_grid_frame.grid_columnconfigure(1, weight=1)
        content_grid_frame.grid_rowconfigure(0, weight=1)

        # --- Left Column: Existing Accounts (with scroll) ---
        accounts_scroll_frame = ctk.CTkScrollableFrame(
            content_grid_frame,
            fg_color="transparent"
        )
        accounts_scroll_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)

        accounts_card = self._create_card(accounts_scroll_frame, "Existing Accounts")
        accounts_card.pack(fill="x", pady=10, padx=0)

        accounts = self.load_accounts_from_env()
        if accounts:
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

                masked = acc['phone'][:3] + "****" + acc['phone'][-4:] if len(acc['phone']) > 7 else acc['phone']
                ctk.CTkLabel(
                    info_frame,
                    text=masked,
                    font=ctk.CTkFont(size=11),
                    text_color=self.colors['text_dim']
                ).pack(anchor="w")

                status_color = self.colors['success'] if acc['status'] == 'active' else self.colors['text_dim']
                ctk.CTkLabel(
                    info_frame,
                    text=f"● {acc['status']}",
                    font=ctk.CTkFont(size=10),
                    text_color=status_color
                ).pack(anchor="w")

                ctk.CTkButton(
                    acc_frame,
                    text="Login",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    width=100,
                    fg_color=self.colors['card'],
                    border_width=1,
                    border_color=self.colors['accent'],
                    hover_color=self.colors['accent_hover'],
                    command=lambda idx=acc['id']: self.select_account(idx)
                ).pack(side="right", padx=10, pady=10)
        else:
            ctk.CTkLabel(accounts_card, text="No existing accounts.", text_color=self.colors['text_dim']).pack(pady=20)

        # --- Right Column: Add New Account ---
        add_card = self._create_card(content_grid_frame, "Add New Account")
        add_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)

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
            border_width=1,
            border_color=self.colors['accent'],
            fg_color=self.colors['card'],
            hover_color=self.colors['accent_hover'],
            command=self.handle_login
        ).pack(fill="x", pady=(10, 0))

        # Bottom buttons (kept at the bottom of main_container)
        btn_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(
            btn_frame,
            text="Logout Current",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=self.colors['warning'],
            hover_color="#e69500",
            command=self.handle_logout_current
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="Reset Config",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=self.colors['error'],
            hover_color="#cc3a47",
            command=self.handle_reset
        ).pack(side="left", padx=5)

    # ==================== SOURCE SELECTION SCREEN ====================
    def show_source_screen(self):
        self.clear_screen()
        self.current_screen = "source"

        # Reset upload specific state
        self.upload_source_path = None
        self.upload_is_folder_mode = False
        self.upload_destination_entity = None
        self.selected_upload_dialog_title = "Select a destination"

        # Header
        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            header_frame,
            text="Select Operation / Source",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['text']
        ).pack(side="left")

        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        self.continue_selected_btn = ctk.CTkButton(
            btn_frame,
            text="Continue with Selected",
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=self._execute_continue_selected_from_header
        )
        self.continue_selected_btn.pack(side="right", padx=(0, 10))
        self.continue_selected_btn.pack_forget()

        ctk.CTkButton(
            btn_frame,
            text="Logout",
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            command=self.handle_logout_and_return
        ).pack(side="right", padx=(5, 0))

        # Main content frame for two panels
        content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=3)
        content_frame.grid_rowconfigure(0, weight=1)

        # Left Panel - Source Selection Buttons
        self.left_panel = ctk.CTkFrame(content_frame, fg_color=self.colors['card'], corner_radius=10)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        self.left_panel.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(self.left_panel, text="OPERATIONS", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(15, 10))

        # Buttons for source selection (these will trigger right panel updates)
        self.source_buttons = {}
        button_defs = [
            ("Upload Media", "upload", self.colors['upload_color']),
            ("Saved Messages", "saved", self.colors['accent']),
            ("Select Dialogs", "dialogs", "#9b59b6"),
            ("All Dialogs", "all", "#2ecc71"),
            ("Continue Last", "continue", "#e67e22")
        ]
        for text, src_type, color in button_defs:
            btn = ctk.CTkButton(
                self.left_panel,
                text=text,
                fg_color="transparent",
                hover_color=color,
                border_width=2,
                border_color=color,
                command=lambda s=src_type: self._select_source_in_panel(s)
            )
            btn.pack(fill="x", padx=15, pady=5)
            self.source_buttons[src_type] = btn

        # Right Panel - Dynamic Content
        self.right_panel = ctk.CTkScrollableFrame(content_frame, fg_color=self.colors['card'], corner_radius=10)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        self.right_panel.grid_columnconfigure(0, weight=1)

        self._show_default_right_panel()

    def _clear_right_panel(self):
        """Xóa tất cả widget khỏi bảng điều khiển bên phải."""
        for widget in self.right_panel.winfo_children():
            widget.destroy()
        if hasattr(self, '_scan_progress_label'):
            del self._scan_progress_label
        if hasattr(self, 'upload_progress_bar'): del self.upload_progress_bar
        if hasattr(self, 'upload_progress_label'): del self.upload_progress_label
        if hasattr(self, 'upload_file_entry'): del self.upload_file_entry
        if hasattr(self, 'upload_destination_display_label'): del self.upload_destination_display_label

    def _show_default_right_panel(self):
        """Hiển thị thông báo mặc định trong bảng điều khiển bên phải."""
        self._clear_right_panel()
        ctk.CTkLabel(
            self.right_panel,
            text="Select an operation or source from the left panel.",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim'],
            wraplength=500
        ).pack(expand=True, padx=20, pady=50)

    def _select_source_in_panel(self, source_type: str):
        """Xử lý việc chọn loại nguồn từ bảng điều khiển bên trái, cập nhật bảng điều khiển bên phải."""
        self.current_source_type = source_type
        self._clear_right_panel()

        if self.continue_selected_btn:
            self.continue_selected_btn.pack_forget()
            self.continue_selected_btn.configure(state="disabled")
        if self.upload_start_btn:
            self.upload_start_btn.pack_forget()
            self.upload_start_btn.configure(state="disabled")

        for btn_type, btn_widget in self.source_buttons.items():
            if btn_type == source_type:
                btn_widget.configure(fg_color=btn_widget.cget("border_color"), text_color=self.colors['bg'])
            else:
                btn_widget.configure(fg_color="transparent", text_color=btn_widget.cget("border_color"))

        if source_type == "saved":
            self._display_saved_messages_options_panel()
        elif source_type == "dialogs":
            self._display_select_dialogs_options_panel()
        elif source_type == "all":
            self._display_all_dialogs_options_panel()
        elif source_type == "continue":
            self._display_continue_last_options_panel()
        elif source_type == "upload":
            self._display_upload_options_panel()

    def _display_saved_messages_options_panel(self):
        ctk.CTkLabel(self.right_panel, text="Saved Messages", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(20, 10))
        ctk.CTkLabel(self.right_panel, text="Download media from your personal 'Saved Messages' chat.",
                     text_color=self.colors['text_dim'], wraplength=400).pack(pady=(0, 20))
        ctk.CTkButton(
            self.right_panel,
            text="Scan Saved Messages & Continue",
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=lambda: self._initiate_scan("saved")
        ).pack(pady=10)

    def _display_all_dialogs_options_panel(self):
        ctk.CTkLabel(self.right_panel, text="All Dialogs", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(20, 10))
        ctk.CTkLabel(self.right_panel, text="Scan and download media from ALL chats and channels you are part of.",
                     text_color=self.colors['text_dim'], wraplength=400).pack(pady=(0, 20))
        ctk.CTkButton(
            self.right_panel,
            text="Scan All Dialogs & Continue",
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=lambda: self._initiate_scan("all")
        ).pack(pady=10)

    def _display_continue_last_options_panel(self):
        ctk.CTkLabel(self.right_panel, text="Continue Last Session", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(20, 10))
        if not self.downloader:
            messagebox.showerror("Error", "Downloader not initialized.")
            return

        state_data = self.downloader.state.state
        if not state_data or not state_data.get("source", {}).get("type"):
            ctk.CTkLabel(self.right_panel, text="No previous session found.", text_color=self.colors['error']).pack(
                pady=10)
            return

        info_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent", corner_radius=8)
        info_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(info_frame, text="Last Session Details:", font=ctk.CTkFont(weight="bold"),
                     text_color=self.colors['text']).pack(anchor="w", padx=10, pady=(10, 5))
        for line_text in self.downloader.state.get_status_lines(self.downloader.download_dir):
            ctk.CTkLabel(info_frame, text=line_text, text_color=self.colors['text_dim']).pack(anchor="w", padx=20)

        ctk.CTkButton(
            self.right_panel,
            text="Continue This Session",
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=lambda: self._initiate_continue_session()
        ).pack(pady=20)

    def _display_select_dialogs_options_panel(self):
        ctk.CTkLabel(self.right_panel, text="Select Dialogs", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(20, 10))
        ctk.CTkLabel(self.right_panel, text="Choose specific chats or channels to download media from.",
                     text_color=self.colors['text_dim'], wraplength=400).pack(pady=(0, 20))
        ctk.CTkButton(
            self.right_panel,
            text="Fetch Dialogs",
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=self._initiate_dialog_fetch
        ).pack(pady=10)

    # ==================== UPLOAD OPTIONS PANEL ====================
    def _display_upload_options_panel(self):
        self._clear_right_panel()
        ctk.CTkLabel(self.right_panel, text="Upload Media", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(20, 10))
        ctk.CTkLabel(self.right_panel, text="Select files/folder and a destination chat/channel to upload.",
                     text_color=self.colors['text_dim'], wraplength=400).pack(pady=(0, 20))

        # File/Folder selection
        file_selection_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        file_selection_frame.pack(fill="x", padx=20, pady=(10, 5))
        ctk.CTkLabel(file_selection_frame, text="Source File(s) / Folder:", text_color=self.colors['text']).pack(
            anchor="w")

        file_input_frame = ctk.CTkFrame(file_selection_frame, fg_color="transparent")
        file_input_frame.pack(fill="x", pady=(5, 0))

        self.upload_file_entry = ctk.CTkEntry(file_input_frame, placeholder_text="No file/folder selected",
                                              fg_color=self.colors['card'], border_color=self.colors['upload_color'])
        self.upload_file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        if self.upload_source_path:
            self.upload_file_entry.delete(0, "end")
            self.upload_file_entry.insert(0, str(self.upload_source_path))

        browse_buttons_frame = ctk.CTkFrame(file_input_frame, fg_color="transparent")
        browse_buttons_frame.pack(side="right")

        ctk.CTkButton(browse_buttons_frame, text="File", command=self._browse_upload_file,
                      fg_color=self.colors['card'], border_width=1, border_color=self.colors['upload_color']).pack(
            side="left", padx=(0, 5))
        ctk.CTkButton(browse_buttons_frame, text="Folder", command=self._browse_upload_folder,
                      fg_color=self.colors['card'], border_width=1, border_color=self.colors['upload_color']).pack(
            side="left")

        # Destination Dialog selection
        dest_selection_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        dest_selection_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(dest_selection_frame, text="Destination Chat/Channel:", text_color=self.colors['text']).pack(
            anchor="w")

        dest_input_frame = ctk.CTkFrame(dest_selection_frame, fg_color="transparent")
        dest_input_frame.pack(fill="x", pady=(5, 0))

        self.upload_destination_display_label = ctk.CTkLabel(dest_input_frame, text=self.selected_upload_dialog_title,
                                                             fg_color=self.colors['card'], corner_radius=5,
                                                             height=30, anchor="w", padx=10,
                                                             text_color=self.colors['text_dim'],
                                                             wraplength=300)
        self.upload_destination_display_label.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(dest_input_frame, text="Select Dialog", command=self._open_upload_destination_dialog_selector,
                      fg_color=self.colors['upload_color'], hover_color=self.colors['upload_hover']).pack(side="right")

        # Caption
        caption_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        caption_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(caption_frame, text="Caption (Optional):", text_color=self.colors['text']).pack(anchor="w")
        self.upload_caption_entry = ctk.CTkEntry(caption_frame, fg_color=self.colors['card'],
                                                 border_color=self.colors['upload_color'])
        self.upload_caption_entry.pack(fill="x")

        # Upload Button
        self.upload_start_btn = ctk.CTkButton(  # Store reference to enable/disable
            self.right_panel,
            text="Start Upload",
            fg_color=self.colors['upload_color'],
            hover_color=self.colors['upload_hover'],
            command=self._handle_start_upload,
            state="disabled"  # Initially disabled
        )
        self.upload_start_btn.pack(pady=20)

        # Progress bar and label
        self.upload_progress_bar = ctk.CTkProgressBar(self.right_panel, height=20,
                                                      progress_color=self.colors['upload_color'])
        self.upload_progress_bar.pack(fill="x", padx=20, pady=(10, 5))
        self.upload_progress_bar.set(0)

        self.upload_progress_label = ctk.CTkLabel(self.right_panel, text="Ready to upload.",
                                                  text_color=self.colors['text_dim'])
        self.upload_progress_label.pack(pady=(0, 10))

        self._update_upload_start_button_state()  # Update button state initially

    def _update_upload_start_button_state(self):
        """Enables/disables the Start Upload button based on selections."""
        if self.upload_start_btn:
            if self.upload_source_path and self.upload_destination_entity:
                self.upload_start_btn.configure(state="normal")
            else:
                self.upload_start_btn.configure(state="disabled")

    def _browse_upload_file(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.upload_source_path = Path(file_path)
            self.upload_is_folder_mode = False
            self.upload_file_entry.delete(0, "end")
            self.upload_file_entry.insert(0, str(self.upload_source_path))
            self._update_upload_start_button_state()

    def _browse_upload_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.upload_source_path = Path(folder_path)
            self.upload_is_folder_mode = True
            self.upload_file_entry.delete(0, "end")
            self.upload_file_entry.insert(0, str(self.upload_source_path))
            self._update_upload_start_button_state()

    def _open_upload_destination_dialog_selector(self):
        """Opens a Toplevel window to select an upload destination dialog."""
        if not self.downloader or not self.downloader.client.is_connected():
            messagebox.showerror("Not Connected", "Please login first.")
            self.show_login_screen()
            return

        dialog_selector_window = ctk.CTkToplevel(self.root)
        dialog_selector_window.title("Select Upload Destination")
        dialog_selector_window.geometry("500x600")
        dialog_selector_window.transient(self.root)
        dialog_selector_window.grab_set()  # Make it modal

        # Fetch dialogs in a separate thread if not already fetched
        if not self.all_dialogs_info:
            ctk.CTkLabel(dialog_selector_window, text="Fetching dialogs...", text_color=self.colors['text_dim']).pack(
                pady=20)

            def fetch_dialogs_for_selector():
                try:
                    loop = self.active_loop
                    if loop is None or loop.is_closed():
                        raise RuntimeError("Active event loop is not available.")
                    asyncio.set_event_loop(loop)
                    dialogs = loop.run_until_complete(
                        self.downloader.list_dialogs(print_to_cli=False))  # Pass print_to_cli=False
                    self.root.after(0, lambda: self._populate_dialog_selector(dialog_selector_window, dialogs))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to fetch dialogs: {e}"))
                    self.root.after(0, dialog_selector_window.destroy)

            threading.Thread(target=fetch_dialogs_for_selector, daemon=True).start()
        else:
            self.root.after(0, lambda: self._populate_dialog_selector(dialog_selector_window, self.all_dialogs_info))

    def _populate_dialog_selector(self, parent_window: ctk.CTkToplevel, dialogs: List[Dict[str, Any]]):
        """Populates the dialog selector window with scrollable list of dialogs."""
        for widget in parent_window.winfo_children():  # Clear loading label
            widget.destroy()

        ctk.CTkLabel(parent_window, text="Choose a chat/channel:", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(10, 5))

        search_frame = ctk.CTkFrame(parent_window, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 10), padx=5)

        search_entry = ctk.CTkEntry(search_frame, placeholder_text="Search dialogs...", fg_color=self.colors['bg'])
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        scrollable_dialog_frame = ctk.CTkScrollableFrame(parent_window, fg_color=self.colors['card'])
        scrollable_dialog_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Store dialogs and reference to the frame for filtering
        parent_window.dialog_data = dialogs
        parent_window.scrollable_dialog_frame = scrollable_dialog_frame

        def filter_dialogs(event=None):
            search_term = search_entry.get().strip().lower()
            for widget in scrollable_dialog_frame.winfo_children():
                widget.destroy()  # Clear existing

            filtered = [d for d in dialogs if
                        search_term in d['title'].lower() or search_term in d['etype'].lower() or (
                                    d['username'] and search_term in d['username'].lower())]
            for dialog_info in filtered:
                display_text = f"{dialog_info['title']} ({dialog_info['etype']})"
                if dialog_info['username']:
                    display_text += f" {dialog_info['username']}"

                btn = ctk.CTkButton(scrollable_dialog_frame, text=display_text,
                                    command=lambda d=dialog_info: self._select_upload_destination_dialog(d,
                                                                                                         parent_window),
                                    fg_color=self.colors['bg'], hover_color=self.colors['accent_hover'],
                                    anchor="w")
                btn.pack(fill="x", pady=2, padx=5)

        search_entry.bind("<KeyRelease>", filter_dialogs)
        filter_dialogs()  # Initial render

    def _select_upload_destination_dialog(self, dialog_info: Dict[str, Any], parent_window: ctk.CTkToplevel):
        """Sets the selected dialog as the upload destination and closes the selector."""
        self.upload_destination_entity = dialog_info['entity']
        self.selected_upload_dialog_title = dialog_info['title']

        # Safely get ID from entity object
        entity_id = getattr(dialog_info['entity'], 'id', None)

        if dialog_info['username']:
            self.selected_upload_dialog_title += f" ({dialog_info['username']})"
        elif entity_id is not None:  # Use entity_id if available and no username
            self.selected_upload_dialog_title += f" (ID: {entity_id})"

        self.upload_destination_display_label.configure(text=self.selected_upload_dialog_title,
                                                        text_color=self.colors['text'])
        self._update_upload_start_button_state()
        parent_window.destroy()

    def _handle_start_upload(self):
        file_path_str = str(self.upload_source_path) if self.upload_source_path else ""
        caption = self.upload_caption_entry.get().strip()
        destination_entity = self.upload_destination_entity

        if not self.downloader or not self.downloader.client.is_connected():
            messagebox.showerror("Not Connected", "Please login first.")
            self.show_login_screen()
            return

        if not file_path_str or not Path(file_path_str).exists():
            messagebox.showwarning("Missing Source", "Please select a valid file or folder to upload.")
            return
        if not destination_entity:
            messagebox.showwarning("Missing Destination", "Please select a destination chat/channel.")
            return

        source_path = Path(file_path_str)
        self.is_uploading = True

        self.upload_start_btn.configure(state="disabled", text="Uploading...")

        self.upload_thread = threading.Thread(
            target=self._upload_thread_run,
            args=(destination_entity, source_path, caption, self.upload_is_folder_mode),
            daemon=True
        )
        self.upload_thread.start()

    def _upload_thread_run(self, destination: Union[User, Chat, Channel, int, str], source_path: Path,
                           caption: Optional[str], is_folder: bool):
        """Executes the upload operation in a background thread."""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for uploading.")
            asyncio.set_event_loop(loop)

            self.root.after(0, lambda: self.upload_progress_bar.set(0))
            self.root.after(0, lambda: self.upload_progress_label.configure(text="Starting upload..."))

            if is_folder:
                def update_ui_folder_progress(overall_p, f_idx, total_f, c_bytes, t_bytes):
                    self.root.after(0, lambda: self.upload_progress_bar.set(overall_p))
                    if t_bytes > 0:
                        text = f"Uploading file {f_idx}/{total_f}: {humanize.naturalsize(c_bytes)} / {humanize.naturalsize(t_bytes)}"
                    else:
                        text = f"Processing file {f_idx}/{total_f}..."
                    self.root.after(0, lambda: self.upload_progress_label.configure(text=text))

                loop.run_until_complete(
                    self.downloader.upload_folder_media(
                        peer=destination,
                        folder_path=source_path,
                        caption=caption,
                        progress_callback=update_ui_folder_progress,
                        stop_flag=lambda: self.stop_flag
                    )
                )
                self.root.after(0, lambda: messagebox.showinfo("Upload Complete",
                                                               f"Successfully uploaded media from {source_path.name}."))
                self.root.after(0, lambda: self.upload_progress_label.configure(text="Folder upload complete!"))

            else:  # Single file upload
                def update_ui_file_progress(progress_percentage, current_bytes, total_bytes):
                    self.root.after(0, lambda: self.upload_progress_bar.set(progress_percentage))
                    self.root.after(0, lambda: self.upload_progress_label.configure(
                        text=f"Uploading... {humanize.naturalsize(current_bytes)} / {humanize.naturalsize(total_bytes)}"
                    ))

                loop.run_until_complete(
                    self.downloader.upload_media(
                        peer=destination,
                        file_path=source_path,
                        caption=caption,
                        progress_callback=update_ui_file_progress
                    )
                )
                self.root.after(0, lambda: messagebox.showinfo("Upload Complete",
                                                               f"Successfully uploaded {source_path.name}."))
                self.root.after(0, lambda: self.upload_progress_label.configure(text="Single file upload complete!"))

            self.is_uploading = False
            self.root.after(0, lambda: self.upload_start_btn.configure(text="Start Upload", state="normal"))


        except Exception as e:
            error_msg = f"Upload error: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))
            self.root.after(0, lambda: self.upload_progress_label.configure(text=f"Upload failed: {e}"))
            self.is_uploading = False
            self.root.after(0, lambda: self.upload_start_btn.configure(text="Start Upload", state="normal"))

    # ==================== DIALOGS SELECTION SCREEN (Adapted for Panel) ====================

    def _initiate_dialog_fetch(self):
        """Bắt đầu lấy hộp thoại, hiển thị thông báo tải trong bảng điều khiển bên phải."""
        if not self.downloader or not self.downloader.client.is_connected():
            messagebox.showerror("Not Connected", "Please login first.")
            self.show_login_screen()
            return

        self._clear_right_panel()
        ctk.CTkLabel(
            self.right_panel,
            text="Loading dialogs...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim'],
            justify="center"
        ).pack(pady=50, expand=True)

        threading.Thread(target=self._fetch_dialogs_thread_for_panel, daemon=True).start()

    def _fetch_dialogs_thread_for_panel(self):
        """Lấy hộp thoại trong luồng nền, sau đó hiển thị trong right_panel."""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for fetching dialogs.")

            asyncio.set_event_loop(loop)
            dialogs = loop.run_until_complete(self.downloader.list_dialogs(print_to_cli=False))
            self.all_dialogs_info = dialogs

            self.root.after(0, lambda d=dialogs: self._display_dialogs_in_panel(d))
        except Exception as e:
            error_msg = f"Failed to fetch dialogs: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))
            self.root.after(0, self.show_source_screen)

    def _display_dialogs_in_panel(self, dialogs):
        """Hiển thị danh sách hộp thoại TRONG right_panel (để chọn tải xuống)"""
        self._clear_right_panel()

        ctk.CTkLabel(
            self.right_panel,
            text=f"Select Dialogs ({len(dialogs)} found)",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors['text']
        ).pack(pady=(10, 5))

        search_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 10), padx=5)

        self.dialog_search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Search dialogs...",
            fg_color=self.colors['bg'],
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

        self.dialog_list_content_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.dialog_list_content_frame.pack(fill="both", expand=True)

        self._render_dialog_list_in_panel(dialogs, self.dialog_list_content_frame)

        if self.continue_selected_btn:
            self.continue_selected_btn.pack(side="right", padx=(0, 10))
            self.continue_selected_btn.configure(state="normal")

    def _render_dialog_list_in_panel(self, dialogs_to_display: List[Dict[str, Any]], target_frame):
        """Render danh sách hộp thoại trong khung đích đã cho."""
        for widget in target_frame.winfo_children():
            widget.destroy()

        self.dialog_checkboxes = []
        for dialog in dialogs_to_display:
            dialog_frame = ctk.CTkFrame(target_frame, fg_color="transparent")  # Changed to transparent
            dialog_frame.pack(fill="x", pady=2, padx=2)

            var = ctk.IntVar()
            if self.selected_dialogs and any(
                    hasattr(s, 'id') and s.id == dialog['entity'].id for s in self.selected_dialogs
            ):
                var.set(1)

            checkbox = ctk.CTkCheckBox(
                dialog_frame,
                text="",
                variable=var,
                checkbox_width=20,
                checkbox_height=20,
                fg_color=self.colors['accent'],
                hover_color=self.colors['accent_hover']
            )
            checkbox.pack(side="left", padx=10, pady=5)

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
                text=f"Type: {dialog['etype']}",
                font=ctk.CTkFont(size=10),
                text_color=self.colors['text_dim'],
                anchor="w"
            ).pack(fill="x")

            self.dialog_checkboxes.append((var, dialog))

    def _on_dialog_search_key_release(self, event=None):
        """Lọc danh sách hộp thoại dựa trên nội dung nhập tìm kiếm."""
        search_term = self.dialog_search_entry.get().strip().lower()
        if search_term:
            filtered_dialogs = [
                d for d in self.all_dialogs_info
                if search_term in d['title'].lower() or search_term in d['etype'].lower() or (
                            d['username'] and search_term in d['username'].lower())
            ]
        else:
            filtered_dialogs = self.all_dialogs_info
        self._render_dialog_list_in_panel(filtered_dialogs, self.dialog_list_content_frame)

    def _select_all_dialogs(self):
        """Chọn tất cả các hộp thoại hiện đang hiển thị."""
        for var, _ in self.dialog_checkboxes:
            var.set(1)

    def _deselect_all_dialogs(self):
        """Bỏ chọn tất cả các hộp thoại hiện đang hiển thị."""
        for var, _ in self.dialog_checkboxes:
            var.set(0)

    def _execute_continue_selected_from_header(self):
        """Xử lý sự kiện khi nút 'Continue with Selected' trong tiêu đề được nhấn."""
        if self.current_screen == "source" and self.current_source_type == "dialogs":
            self._continue_with_selected_dialogs_from_panel()
        else:
            messagebox.showerror("Lỗi", "Nút này chỉ khả dụng khi chọn 'Select Dialogs'.")

    def _continue_with_selected_dialogs_from_panel(self):
        """Tiếp tục với các hộp thoại đã chọn (sau khi hiển thị trong bảng điều khiển)"""
        selected = [d for var, d in self.dialog_checkboxes if var.get() == 1]

        if not selected:
            messagebox.showwarning("No Selection", "Please select at least one dialog!")
            return

        self.selected_dialogs = [d['entity'] for d in selected]
        self._initiate_scan(self.current_source_type)

    # ==================== FILTER SCREEN ====================
    def show_filter_screen(self):
        self.clear_screen()
        self.current_screen = "filter"

        if self.downloader:
            self.stats = self.downloader.stats.copy()

        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
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

        if self.continue_selected_btn:
            self.continue_selected_btn.pack_forget()
            self.continue_selected_btn.configure(state="disabled")

        content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=3)
        content_frame.grid_rowconfigure(0, weight=1)

        self.filter_left_panel = ctk.CTkFrame(content_frame, fg_color=self.colors['card'], corner_radius=10)
        self.filter_left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        self.filter_left_panel.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self.filter_left_panel, text="FILTERS", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(15, 10))

        self.filter_buttons = {}
        filter_defs = [
            ("Photos Only", "1", self.colors['accent']),
            ("Videos Only", "2", "#9b59b6"),
            ("Both Photos & Videos", "3", "#2ecc71")
        ]
        for text, filter_choice, color in filter_defs:
            btn = ctk.CTkButton(
                self.filter_left_panel,
                text=text,
                fg_color="transparent",
                hover_color=color,
                border_width=2,
                border_color=color,
                command=lambda f=filter_choice: self._select_filter_in_panel(f)
            )
            btn.pack(fill="x", padx=15, pady=5)
            self.filter_buttons[filter_choice] = btn

        self.filter_right_panel = ctk.CTkFrame(content_frame, fg_color=self.colors['card'], corner_radius=10)
        self.filter_right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        self.filter_right_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.filter_right_panel, text="SCAN RESULTS", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(20, 10))

        stats_grid = ctk.CTkFrame(self.filter_right_panel, fg_color="transparent")
        stats_grid.pack(fill="x", pady=10, padx=15)

        for i in range(4):
            stats_grid.grid_columnconfigure(i, weight=1)

        self._create_stat_box(stats_grid, 0, str(self.stats['images_found']), "Photos Found", self.colors['accent'])
        self._create_stat_box(stats_grid, 1, str(self.stats['videos_found']), "Videos Found", "#9b59b6")
        self._create_stat_box(stats_grid, 2, str(self.stats['total_found']), "Total Media", "#2ecc71")
        size_str = humanize.naturalsize(self.stats['total_size'])
        self._create_stat_box(stats_grid, 3, size_str, "Estimated Size", "#e67e22")

        ctk.CTkFrame(self.filter_right_panel, fg_color="transparent", height=20).pack(fill="x", pady=10)

        self.start_download_btn = ctk.CTkButton(
            self.filter_right_panel,
            text="Start Download",
            height=50,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            command=lambda: self.start_download(self.current_filter),
            state="disabled"
        )
        self.start_download_btn.pack(fill="x", padx=30, pady=(20, 30))

        if self.downloader and self.downloader.state.get_last_filter() in self.filter_buttons:
            self._select_filter_in_panel(self.downloader.state.get_last_filter())
        else:
            self._select_filter_in_panel("3")

    def _select_filter_in_panel(self, filter_choice: str):
        """Xử lý việc chọn loại bộ lọc từ bảng điều khiển bên trái, cập nhật giao diện nút."""
        self.current_filter = filter_choice

        for btn_choice, btn_widget in self.filter_buttons.items():
            if btn_choice == filter_choice:
                btn_widget.configure(fg_color=btn_widget.cget("border_color"), text_color=self.colors['bg'])
            else:
                btn_widget.configure(fg_color="transparent", text_color=btn_widget.cget("border_color"))

        self.start_download_btn.configure(state="normal")

    # ==================== DOWNLOAD SCREEN ====================
    def show_download_screen(self):
        self.clear_screen()
        self.current_screen = "download"

        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
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

        if self.continue_selected_btn:
            self.continue_selected_btn.pack_forget()
            self.continue_selected_btn.configure(state="disabled")
        if self.start_download_btn:
            self.start_download_btn.pack_forget()
            self.start_download_btn.configure(state="disabled")

        progress_card = ctk.CTkFrame(self.main_container, fg_color=self.colors['card'], corner_radius=10)
        progress_card.pack(fill="both", expand=True)

        content_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)

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

        stats_grid = ctk.CTkFrame(content_frame, fg_color="transparent")
        stats_grid.pack(fill="x", pady=10)

        for i in range(4):
            stats_grid.grid_columnconfigure(i, weight=1)

        self.stat_boxes = {}
        self._create_download_stat_box(stats_grid, 0, "0", "Downloaded", self.colors['success'], 'downloaded')
        self._create_download_stat_box(stats_grid, 1, "0", "Skipped", self.colors['warning'], 'skipped')
        self._create_download_stat_box(stats_grid, 2, "0", "Errors", self.colors['error'], 'errors')
        self._create_download_stat_box(stats_grid, 3, "0 B", "Size", self.colors['accent'], 'size')

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
        self.log_textbox.configure(state="disabled")

    def _create_download_stat_box(self, parent, col, value, label, color, key):
        """Tạo hộp thống kê cho màn hình tải xuống"""
        box = ctk.CTkFrame(parent, fg_color=self.colors['bg'], corner_radius=8)
        box.grid(row=0, column=col, padx=5, sticky="ew")

        value_label = ctk.CTkLabel(
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

        self.stat_boxes[key] = value_label

    # ==================== HELPER METHODS ====================
    def _create_card(self, parent, title):
        """Tạo container thẻ"""
        card = ctk.CTkFrame(parent, fg_color=self.colors['card'], corner_radius=10)

        if title:
            title_label = ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.colors['text']
            )
            title_label.pack(anchor="w", padx=15, pady=(15, 10))

        return card

    def _create_stat_box(self, parent, col, value, label, color):
        """Tạo hộp thống kê"""
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

    def _show_error(self, message):
        """Hiển thị thông báo lỗi"""
        messagebox.showerror("Error", message)

    def _append_log(self, message: str, color: Optional[str] = None):
        """Ghi thêm tin nhắn vào hộp văn bản nhật ký hoặc cập nhật nhãn tiến độ."""
        target_textbox = None
        if self.current_screen == "download" and hasattr(self, 'log_textbox'):
            target_textbox = self.log_textbox
        elif self.current_screen == "upload" and hasattr(self, 'upload_progress_label'):
            text_color = self.colors.get(color) if color else self.colors['text_dim']
            self.root.after(0, lambda: self.upload_progress_label.configure(text=message, text_color=text_color))
            return

        if target_textbox:
            target_textbox.configure(state="normal")
            if color == "red":
                target_textbox.insert("end", f"{message}\n", "red_tag")
                target_textbox.tag_config("red_tag", foreground=self.colors['error'])
            elif color == "yellow":
                target_textbox.insert("end", f"{message}\n", "yellow_tag")
                target_textbox.tag_config("yellow_tag", foreground=self.colors['warning'])
            elif color == "green":
                target_textbox.insert("end", f"{message}\n", "green_tag")
                target_textbox.tag_config("green_tag", foreground=self.colors['success'])
            elif color == "blue":
                target_textbox.insert("end", f"{message}\n", "blue_tag")
                target_textbox.tag_config("blue_tag", foreground=self.colors['accent'])
            else:
                target_textbox.insert("end", f"{message}\n")
            target_textbox.see("end")
            target_textbox.configure(state="disabled")
        else:
            print(f"[LOG]: {message}")

    # ==================== EVENT HANDLERS ====================
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.download_dir_entry.delete(0, "end")
            self.download_dir_entry.insert(0, directory)

    def handle_login(self):
        """Xử lý đăng nhập và lưu tài khoản mới, sử dụng do_login_flow từ downloader.py"""
        phone = self.phone_entry.get().strip()
        api_id_str = self.api_id_entry.get().strip()
        api_hash = self.api_hash_entry.get().strip()
        download_dir = self.download_dir_entry.get().strip() or "downloads"

        if not all([phone, api_id_str, api_hash]):
            messagebox.showwarning("Missing Info", "Please fill Phone, API ID, and API Hash!")
            return

        try:
            api_id_int = int(api_id_str)
        except ValueError:
            messagebox.showerror("Invalid API ID", "API ID must be a number!")
            return

        new_idx = find_next_account_index(self.envd)

        def login_in_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                updated_envd, logged_in_idx = loop.run_until_complete(
                    do_login_flow(
                        self.envd,
                        self.gui_log_output,
                        self.gui_get_input,
                        phone=phone,
                        api_id=api_id_int,
                        api_hash=api_hash,
                        download_dir=download_dir,
                        account_idx_to_use=new_idx
                    )
                )
                self.root.after(0, lambda: self._post_login_process(updated_envd, logged_in_idx))
            except Exception as e:
                self.root.after(0, lambda: self._show_error(f"Login process failed: {e}"))
                self.root.after(0, self.show_login_screen)

        self.clear_screen()
        ctk.CTkLabel(self.main_container, text="Logging in...", font=ctk.CTkFont(size=14),
                     text_color=self.colors['text_dim']).pack(pady=50)

        threading.Thread(target=login_in_thread, daemon=True).start()

    def _post_login_process(self, updated_envd: Dict[str, str], logged_in_idx: int):
        if logged_in_idx > 0:
            self.envd = updated_envd
            save_env(self.env_path, self.envd)
            self.current_account_idx = logged_in_idx
            self._init_downloader_and_connect()
        else:
            self.show_login_screen()

    def _init_downloader_and_connect(self):
        """Khởi tạo trình tải xuống và kết nối trong nền"""
        cfg = get_account_config(self.envd, self.current_account_idx)

        if not cfg:
            self._show_error("Could not retrieve account configuration. Please check .env file.")
            self.show_login_screen()
            return

        if self.active_loop and not self.active_loop.is_closed():
            self.active_loop.stop()
            self.active_loop.close()
        self.active_loop = asyncio.new_event_loop()

        self.clear_screen()
        loading = ctk.CTkLabel(
            self.main_container,
            text="Connecting to Telegram...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim']
        )
        loading.pack(pady=50)

        threading.Thread(
            target=self._connect_thread,
            args=(cfg, self.active_loop),
            daemon=True
        ).start()

    def _connect_thread(self, cfg: Dict[str, str], loop_to_use: asyncio.AbstractEventLoop):
        """Kết nối với Telegram trong luồng nền"""
        try:
            asyncio.set_event_loop(loop_to_use)

            self.downloader = TelegramDownloader(
                api_id=int(cfg["API_ID"]),
                api_hash=cfg["API_HASH"],
                phone=cfg["PHONE"],
                download_dir=cfg["DOWNLOAD_DIR"],
                account_index=self.current_account_idx,
                log_func=self.gui_log_output,
                input_func=self.gui_get_input
            )

            if loop_to_use.run_until_complete(self.downloader.connect_client()):
                self.root.after(0, self.show_source_screen)
            else:
                self.root.after(0, self.show_login_screen)

        except Exception as e:
            error_msg = f"Connection error: {str(e)}\n\nMake sure your API credentials are correct or check your network."
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))
            self.root.after(0, self.show_login_screen)

    def select_account(self, idx):
        """Chọn tài khoản có sẵn"""
        self.current_account_idx = idx
        self.envd = set_current_account_index(self.envd, idx)
        save_env(self.env_path, self.envd)

        self._init_downloader_and_connect()

    def handle_logout_current(self):
        """Đăng xuất tài khoản hiện tại"""
        if self.current_account_idx == 0 or not self.downloader:
            messagebox.showinfo("No Account", "No account is currently logged in.")
            return

        if messagebox.askyesno("Confirm Logout", f"Logout account #{self.current_account_idx}?"):
            def logout_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                updated_envd = loop.run_until_complete(
                    do_logout_flow(self.envd.copy(), self.gui_log_output, self.current_account_idx))
                self.root.after(0, lambda: self._post_logout_process(updated_envd))

            threading.Thread(target=logout_in_thread, daemon=True).start()

    def handle_logout_and_return(self):
        """Đăng xuất và quay về màn hình đăng nhập (từ màn hình nguồn)"""
        if messagebox.askyesno("Confirm", "Logout and return to login screen?"):
            def logout_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                if self.current_account_idx != 0 and self.downloader:
                    updated_envd = loop.run_until_complete(
                        do_logout_flow(self.envd.copy(), self.gui_log_output, self.current_account_idx))
                else:
                    updated_envd = self.envd.copy()
                self.root.after(0, lambda: self._post_logout_process(updated_envd))

            threading.Thread(target=logout_in_thread, daemon=True).start()

    def _post_logout_process(self, updated_envd: Dict[str, str]):
        self.envd = updated_envd
        save_env(self.env_path, self.envd)
        self.current_account_idx = get_current_account_index(self.envd)
        messagebox.showinfo("Logged Out", "Session files deleted. You can login again.")
        self._disconnect_and_close_loop()
        self.show_login_screen()

    def handle_reset(self):
        """Đặt lại file .env"""
        if messagebox.askyesno("Confirm Reset",
                               "Reset all config? This will delete all account info and saved sessions!"):
            def reset_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                updated_envd = loop.run_until_complete(
                    do_reset_flow(self.envd.copy(), self.gui_log_output, confirm=True))
                self.root.after(0, lambda: self._post_reset_process(updated_envd))

            threading.Thread(target=reset_in_thread, daemon=True).start()

    def _post_reset_process(self, updated_envd: Dict[str, str]):
        self.envd = updated_envd
        save_env(self.env_path, self.envd)
        self.current_account_idx = get_current_account_index(self.envd)
        messagebox.showinfo("Reset", "Config and all session files have been reset!")
        self._disconnect_and_close_loop()
        self.show_login_screen()

    def _update_scan_progress_callback(self, current_messages_scanned: int, total_messages: Optional[int]):
        """Callback cho các cập nhật tiến độ quét."""
        if self.current_screen == "source" and hasattr(self, '_scan_progress_label'):
            scan_progress_label = getattr(self, '_scan_progress_label', None)
            if scan_progress_label:
                self.root.after(0, lambda: scan_progress_label.configure(
                    text=f"Scanning... {current_messages_scanned} messages processed. Found {self.downloader.stats['total_found']} media."
                ))
        self.root.update_idletasks()

    def _initiate_scan(self, source_type: str):
        """Bắt đầu quét, hiển thị thông báo tải trong bảng điều khiển bên phải."""
        if not self.downloader or not self.downloader.client.is_connected():
            messagebox.showerror("Not Connected", "Please login first.")
            self.show_login_screen()
            return

        self.current_source_type = source_type

        self._clear_right_panel()
        ctk.CTkLabel(
            self.right_panel,
            text=f"Scanning media from {source_type}...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim'],
            justify="center"
        ).pack(pady=50, expand=True)

        threading.Thread(target=self._fetch_all_dialogs_and_scan_thread, daemon=True).start()

    def _fetch_all_dialogs_and_scan_thread(self):
        """Lấy tất cả các hộp thoại cho loại nguồn 'all' và sau đó bắt đầu quét."""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available.")
            asyncio.set_event_loop(loop)

            self.root.after(0, lambda: self._scan_progress_label.configure(text="Fetching all dialogs..."))
            dialogs = loop.run_until_complete(self.downloader.list_dialogs(print_to_cli=False))
            self.all_dialogs_info = dialogs
            self.selected_dialogs = [d['entity'] for d in dialogs]
            self.root.after(0, self._scan_media_thread_for_panel)

        except Exception as e:
            error_msg = f"Failed to fetch all dialogs: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))
            self.root.after(0, self.show_source_screen)

    def _scan_media_thread_for_panel(self):
        """Quét media trong nền, sau đó hiển thị màn hình tùy chọn bộ lọc."""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for scanning media.")
            asyncio.set_event_loop(loop)

            success = loop.run_until_complete(
                self.downloader._run_with_source(
                    self.current_source_type,
                    chosen_entities=self.selected_dialogs if self.selected_dialogs != ['me'] else None,
                    confirm_callback=self._gui_confirm_callback,
                    progress_callback_scan=self._update_scan_progress_callback,
                    progress_callback_download=None,
                    stop_flag=lambda: self.stop_flag
                )
            )

            if success and not self.stop_flag:
                self.media_list = self.downloader.media_list
                self.stats = self.downloader.stats.copy()
                self.root.after(0, self.show_filter_screen)
            else:
                self.root.after(0, self.show_source_screen)

        except Exception as e:
            error_msg = f"Scan error: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))
            self.root.after(0, self.show_source_screen)

    def _initiate_continue_session(self):
        """Khôi phục và cố gắng tiếp tục phiên cuối cùng."""
        if not self.downloader:
            messagebox.showerror("Error", "Downloader not initialized.")
            return

        state = self.downloader.state
        prev = state.get_source()

        if not prev or not prev.get("type"):
            messagebox.showinfo("No Session", "No previous session found to continue.")
            self._show_default_right_panel()
            return

        typ = prev.get("type")
        dialog_ids_from_state = prev.get("dialog_ids", [])

        self.current_source_type = typ

        self._clear_right_panel()
        ctk.CTkLabel(
            self.right_panel,
            text="Restoring last session...",
            font=ctk.CTkFont(size=14),
            text_color=self.colors['text_dim'],
            justify="center"
        ).pack(pady=50, expand=True)

        def _restore_dialogs_and_scan_thread():
            try:
                loop = self.active_loop
                if loop is None or loop.is_closed():
                    raise RuntimeError("Active event loop is not available for restoring dialogs.")
                asyncio.set_event_loop(loop)

                restored_entities = []
                if typ == "saved":
                    restored_entities = ['me']
                else:
                    want_ids = [int(x) for x in dialog_ids_from_state if str(x).isdigit() and int(x) != 0]
                    if not want_ids:
                        self.root.after(0, lambda: messagebox.showinfo("No Session",
                                                                       "Could not restore dialogs from previous session."))
                        self.root.after(0, self._show_default_right_panel)
                        return

                    all_dialogs = loop.run_until_complete(self.downloader.list_dialogs(print_to_cli=False))
                    for d_info in all_dialogs:
                        if hasattr(d_info["entity"], "id") and int(d_info["entity"].id) in want_ids:
                            restored_entities.append(d_info["entity"])

                    if not restored_entities:
                        self.root.after(0, lambda: messagebox.showinfo("No Session",
                                                                       "Could not restore dialogs from previous session."))
                        self.root.after(0, self._show_default_right_panel)
                        return

                self.selected_dialogs = restored_entities
                self.root.after(0, self._scan_media_thread_for_panel)

            except Exception as e:
                self.root.after(0,
                                lambda msg=f"Error restoring previous session: {e}": messagebox.showerror("Error", msg))
                self.root.after(0, self._show_default_right_panel)

        threading.Thread(target=_restore_dialogs_and_scan_thread, daemon=True).start()

    def start_download(self, filter_choice):
        """Bắt đầu tải xuống với bộ lọc đã chọn"""
        if not self.downloader:
            messagebox.showerror("Error", "Downloader not initialized.")
            return

        self.current_filter = filter_choice

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

        dialog_ids_for_state = ['me'] if self.selected_dialogs == ['me'] else [int(getattr(d, 'id', 0)) for d in
                                                                               self.selected_dialogs if
                                                                               hasattr(d, 'id')]
        self.downloader.state.set_source(self.current_source_type, dialog_ids_for_state,
                                         total_found=len(self.media_list), last_filter=filter_choice)

        self.show_download_screen()

        source_label = "Saved Messages" if self.selected_dialogs == ['me'] else f"{len(self.selected_dialogs)} dialogs"
        filter_label = {"1": "Photos only", "2": "Videos only", "3": "Both Photos & Videos"}[filter_choice]

        status_text = f"• Source: {source_label}\n"
        status_text += f"• Directory: {self.downloader.download_dir}\n"
        status_text += f"• Filter: {filter_label}\n"
        status_text += f"• Status: Starting..."

        self.status_label.configure(text=status_text)
        self.gui_log_output(f"Download started for {len(self.filtered_media_list)} files.", "blue")
        self.gui_log_output(f"Source: {source_label}, Filter: {filter_label}")
        self.gui_log_output(f"Download directory: {self.downloader.download_dir}")

        self.download_thread = threading.Thread(target=self._download_thread, daemon=True)
        self.download_thread.start()

    def _download_thread(self):
        """Luồng tải xuống"""
        try:
            loop = self.active_loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Active event loop is not available for downloading.")
            asyncio.set_event_loop(loop)

            def stop_check() -> bool:
                return self.stop_flag or not self.is_downloading

            loop.run_until_complete(
                self.downloader.download_all_media(
                    self.filtered_media_list,
                    stop_flag=stop_check,
                    progress_callback=lambda p, c, t, s: self.root.after(0, self._update_download_progress, p, c, t, s)
                )
            )

            self.root.after(0, self._download_complete)

        except Exception as e:
            error_msg = f"Download thread error: {str(e)}"
            self.root.after(0, lambda msg=error_msg: self._show_error(msg))
            self.root.after(0, self.show_source_screen)

    def _update_download_progress(self, progress: float, current: int, total: int, stats: Dict[str, Any]):
        """Cập nhật tiến độ tải xuống trong giao diện người dùng (được gọi từ luồng nền thông qua root.after)."""
        if self.current_screen != "download":
            return

        self.progress_bar.set(progress)
        self.progress_label.configure(text=f"{current}/{total}")

        self.stat_boxes['downloaded'].configure(text=str(stats['downloaded']))
        self.stat_boxes['skipped'].configure(text=str(stats['skipped']))
        self.stat_boxes['errors'].configure(text=str(stats['errors']))
        self.stat_boxes['size'].configure(text=humanize.naturalsize(stats['total_size']))

        source_label = "Saved Messages" if self.selected_dialogs == ['me'] else f"{len(self.selected_dialogs)} dialogs"
        filter_label = {"1": "Photos only", "2": "Videos only", "3": "Both Photos & Videos"}[self.current_filter]

        status_text = f"• Source: {source_label}\n"
        status_text += f"• Directory: {self.downloader.download_dir}\n"
        status_text += f"• Filter: {filter_label}\n"
        status_text += f"• Status: {'Downloading...' if self.is_downloading else 'Paused'}"

        self.status_label.configure(text=status_text)

    def _download_complete(self):
        """Tải xuống hoàn tất"""
        self.gui_log_output("Download session complete.", "blue")
        messagebox.showinfo(
            "Download Complete",
            f"Downloaded: {self.downloader.stats['downloaded']}\n"
            f"Skipped: {self.downloader.stats['skipped']}\n"
            f"Errors: {self.downloader.stats['errors']}\n"
            f"Total size: {humanize.naturalsize(self.downloader.stats['total_size'])}"
        )
        self.is_downloading = False
        self.stop_flag = False
        self.show_source_screen()

    def toggle_download(self):
        """Tạm dừng/Tiếp tục tải xuống"""
        self.is_downloading = not self.is_downloading
        if self.is_downloading:
            self.pause_btn.configure(text="Pause", fg_color=self.colors['warning'], hover_color="#e69500")
            self.gui_log_output("Download resumed.")
        else:
            self.pause_btn.configure(text="Resume", fg_color=self.colors['accent'],
                                     hover_color=self.colors['accent_hover'])
            self.gui_log_output("Download paused.", "yellow")
        current = int(self.progress_label.cget("text").split('/')[0]) if '/' in self.progress_label.cget("text") else 0
        total = int(self.progress_label.cget("text").split('/')[1]) if '/' in self.progress_label.cget("text") else 0
        progress = self.progress_bar.get()
        self._update_download_progress(progress, current, total, self.downloader.stats.copy())

    def stop_download(self):
        """Dừng tải xuống"""
        if messagebox.askyesno("Confirm", "Stop download and return?"):
            self.stop_flag = True
            self.is_downloading = False
            self.pause_btn.configure(text="Pause", fg_color=self.colors['warning'],
                                     hover_color="#e69500")
            self.gui_log_output("Stopping download...", "red")

            self.root.after(0, self.show_source_screen)

    def on_closing(self):
        """Xử lý khi đóng cửa sổ"""
        if self.is_downloading or self.is_uploading:
            if messagebox.askyesno("Confirm Exit", "Operation in progress. Exit anyway?"):
                self.stop_flag = True
                self._disconnect_and_close_loop()
                self.root.destroy()
        else:
            self._disconnect_and_close_loop()
            self.root.destroy()

    def _disconnect_and_close_loop(self):
        """Ngắt kết nối ứng dụng khách Telegram và đóng vòng lặp sự kiện đang hoạt động."""
        if self.downloader and self.downloader.client and self.downloader.client.is_connected():
            try:
                def disconnect_sync():
                    if self.active_loop and not self.active_loop.is_closed():
                        try:
                            asyncio.set_event_loop(self.active_loop)
                            self.active_loop.run_until_complete(self.downloader.client.disconnect())
                        except Exception as e:
                            print(f"Error during Telethon client disconnect in thread: {e}")

                disconnect_thread = threading.Thread(target=disconnect_sync, daemon=True)
                disconnect_thread.start()
                disconnect_thread.join(timeout=2)
            except Exception as e:
                print(f"Error attempting client disconnect: {e}")

        if self.active_loop and not self.active_loop.is_closed():
            self.active_loop.stop()
            self.active_loop.close()
        self.active_loop = None
        self.downloader = None

    def _gui_confirm_callback(self, title: str, message: str) -> bool:
        """Trợ giúp để hiển thị hộp thoại xác nhận và chặn luồng gọi."""
        self._gui_input_result = None
        self._gui_event.clear()

        def show_confirm_dialog():
            result = messagebox.askyesno(title, message)
            self._gui_input_result = result
            self._gui_event.set()

        self.root.after(0, show_confirm_dialog)
        self._gui_event.wait()
        return self._gui_input_result

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
