# tele-downloader-toolkit/ui/cli/commands.py

import argparse
import asyncio
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

import humanize

# Import core components using relative paths
from ...core.client import TelegramClientWrapper
from ...core.downloader import MediaDownloader
from ...core.uploader import MediaUploader
from ...core.state_manager import StateManager

# Import storage components using relative path
from ...storage import config

# Import CLI formatting and I/O wrappers from the same directory
from .formatters import (
    console_log_func,
    console_input_func,
    cli_progress_callback,
    cli_scan_progress_callback,
    WIDTH,
    c,
    pad,
    box,
    # Fore is not used directly here; c() with string color tags is preferred.
    # If your linter still complains, you can remove 'Fore' from this import.
)


# --- Helper to initialize and connect core components for a command ---
async def _initialize_downloader_and_uploader_for_command(
        env_path: Path,
        account_index: int
) -> Optional[Tuple[TelegramClientWrapper, MediaDownloader, MediaUploader]]:
    """
    Loads config, initializes and connects the TelegramClientWrapper,
    then initializes MediaDownloader and MediaUploader.
    Returns (client_wrapper, downloader, uploader) or None on failure.
    """
    envd = config.load_env(env_path)
    cfg = config.get_account_config(envd, account_index)

    if not all([cfg["PHONE"], cfg["API_ID"], cfg["API_HASH"]]):
        console_log_func(
            pad(f"Account configuration for index {account_index} is incomplete. "
                "Please ensure PHONE, API_ID, API_HASH are set.", WIDTH, "left"), "red")
        return None

    try:
        api_id_int = int(cfg["API_ID"])
    except ValueError:
        console_log_func(
            pad(f"Invalid API_ID '{cfg['API_ID']}' for account #{account_index}. Must be a number.", WIDTH, "left"),
            "red")
        return None

    client_wrapper = TelegramClientWrapper(
        api_id=api_id_int,
        api_hash=cfg["API_HASH"],
        phone=cfg["PHONE"],
        account_index=account_index,
        log_func=console_log_func,
        input_func=console_input_func
    )

    if not await client_wrapper.connect_client():
        console_log_func(pad("Failed to connect client.", WIDTH, "left"), "red")
        return None

    download_dir_path = Path(cfg["DOWNLOAD_DIR"])
    downloader = MediaDownloader(
        client_wrapper=client_wrapper,
        download_dir=download_dir_path,
        account_index=account_index,
        log_func=console_log_func
    )

    uploader = MediaUploader(
        client_wrapper=client_wrapper,
        log_func=console_log_func
    )

    return client_wrapper, downloader, uploader


# --- CLI Command Implementations ---

async def run_cli_login(args):
    env_path = Path(".env")
    envd = config.load_env(env_path)

    # Determine which account index to use/create
    account_idx_to_use = None
    accounts = []
    idxs = config.get_all_account_indices(envd)
    for idx in idxs:
        acc_cfg = config.get_account_config(envd, idx)
        accounts.append({'id': idx, 'phone': acc_cfg['PHONE']})

    if accounts:
        console_log_func(pad("Existing accounts:", WIDTH, "left"), "blue")
        for acc in accounts:
            console_log_func(pad(f"  {acc['id']}: {acc['phone']}", WIDTH, "left"))

        while account_idx_to_use is None:
            choice = console_input_func("Enter account index to use or 'new' to add a new account", default="new",
                                        hide_input=False)
            if choice.lower() == 'new':
                account_idx_to_use = config.find_next_account_index(envd)
                break
            try:
                chosen_idx = int(choice)
                if chosen_idx in idxs:
                    account_idx_to_use = chosen_idx
                    break
                else:
                    console_log_func("Invalid index. Please try again.", "red")
            except ValueError:
                console_log_func("Invalid input. Enter an index or 'new'.", "red")
    else:
        console_log_func("No existing accounts. Creating a new one.", "yellow")
        account_idx_to_use = config.find_next_account_index(envd)

    current_cfg = config.get_account_config(envd, account_idx_to_use)

    # Prompt for missing info, or use provided args/env values
    resolved_phone = args.phone or (current_cfg["PHONE"] if current_cfg["PHONE"] else None) or console_input_func(
        "Enter phone number (e.g., +84123456789)", hide_input=False)

    resolved_api_id_str = str(args.api_id) if args.api_id else (
        current_cfg["API_ID"] if current_cfg["API_ID"] else None)
    if resolved_api_id_str is None:
        while True:
            try:
                resolved_api_id_str = console_input_func("Enter API ID (from my.telegram.org)", hide_input=False)
                int(resolved_api_id_str)  # Validate it's an int
                break
            except ValueError:
                console_log_func("API ID must be a number.", "red")

    resolved_api_hash = args.api_hash or (
        current_cfg["API_HASH"] if current_cfg["API_HASH"] else None) or console_input_func(
        "Enter API Hash (from my.telegram.org)", hide_input=True)  # Mask API hash input

    resolved_download_dir = args.download_dir or (
        current_cfg["DOWNLOAD_DIR"] if current_cfg["DOWNLOAD_DIR"] else None) or console_input_func(
        "Enter download directory",
        default="downloads",
        hide_input=False)

    # Update envd with resolved details for the selected index
    account_data_to_save = {
        "PHONE": resolved_phone,
        "API_ID": resolved_api_id_str,
        "API_HASH": resolved_api_hash,
        "DOWNLOAD_DIR": resolved_download_dir,
    }
    envd = config.update_account_config(envd, account_idx_to_use, account_data_to_save)
    envd = config.set_current_account_index(envd, account_idx_to_use)
    config.save_env(env_path, envd)  # Save immediately after updates

    # Initialize and connect ClientWrapper to verify credentials
    client_wrapper = TelegramClientWrapper(
        api_id=int(resolved_api_id_str),
        api_hash=resolved_api_hash,
        phone=resolved_phone,
        account_index=account_idx_to_use,
        log_func=console_log_func,
        input_func=console_input_func
    )

    console_log_func(
        pad(f"Attempting to connect with account #{account_idx_to_use} ({resolved_phone})...", WIDTH, "left"),
        "blue")
    try:
        if await client_wrapper.connect_client():
            console_log_func(pad(f"Successfully logged in with account #{account_idx_to_use}.", WIDTH, "left"), "green")
            await client_wrapper.disconnect_client()  # Disconnect after successful auth
            console_log_func(
                pad(f"Login command finished. Active account set to #{account_idx_to_use}.", WIDTH, "left"), "green")
        else:
            console_log_func(pad("Login verification failed. Please check your credentials.", WIDTH, "left"), "red")
            console_log_func(pad("Login command failed.", WIDTH, "left"), "red")
    except Exception as e:
        console_log_func(pad(f"An error occurred during login verification: {e}", WIDTH, "left"), "red")
        console_log_func(pad("Login command failed.", WIDTH, "left"), "red")


async def run_cli_logout(args):
    env_path = Path(".env")
    envd = config.load_env(env_path)

    idx_to_logout = args.account_index if args.account_index is not None else config.get_current_account_index(envd)

    if idx_to_logout == 0:
        console_log_func(pad("No account is currently logged in or specified for logout.", WIDTH, "left"), "yellow")
        return

    console_log_func(pad(f"Logging out account #{idx_to_logout}...", WIDTH, "left"), "blue")

    # Attempt to disconnect client if session file might exist
    try:
        acc_cfg = config.get_account_config(envd, idx_to_logout)
        if all([acc_cfg["PHONE"], acc_cfg["API_ID"], acc_cfg["API_HASH"]]):
            temp_client_wrapper = TelegramClientWrapper(
                api_id=int(acc_cfg["API_ID"]), api_hash=acc_cfg["API_HASH"],
                phone=acc_cfg["PHONE"], account_index=idx_to_logout,
                log_func=console_log_func, input_func=console_input_func
            )
            session_file_path = Path("sessions") / f"session_{idx_to_logout}.session"
            if session_file_path.exists():  # Only try to connect if a session file is present
                try:
                    await temp_client_wrapper.client.connect()
                    await temp_client_wrapper.disconnect_client()
                except Exception:
                    # Ignore connection/disconnect errors if session is already invalid or client isn't fully authorized
                    pass
    except Exception:
        pass  # Ignore any errors during temp client init/disconnect

    # Clear relevant env vars
    envd = config.delete_account_config(envd, idx_to_logout)
    config.save_env(env_path, envd)

    # Purge session and state files for this account
    try:
        session_file = Path("sessions") / f"session_{idx_to_logout}.session"
        state_manager = StateManager(idx_to_logout)  # Initialize to get the state file path

        if session_file.exists():
            session_file.unlink()
            console_log_func(pad(f"Deleted session file: {session_file}", WIDTH, "left"), "blue")

        if state_manager.state_file.exists():
            state_manager.delete_state_file()
            console_log_func(pad(f"Deleted state file: {state_manager.state_file}", WIDTH, "left"), "blue")

    except Exception as e:
        console_log_func(pad(f"Error purging session/state files for account #{idx_to_logout}: {e}", WIDTH, "left"),
                         "red")

    console_log_func(pad(f"Account #{idx_to_logout} logged out successfully.", WIDTH, "left"), "green")


async def run_cli_reset(args):
    env_path = Path(".env")
    envd = config.load_env(env_path)

    confirm_reset = console_input_func(
        "Are you sure you want to reset ALL config and delete ALL session files? (yes/no)",
        hide_input=False).lower() == 'yes'
    if not confirm_reset:
        console_log_func(pad("Reset cancelled.", WIDTH, "left"), "yellow")
        return

    console_log_func(pad("Resetting all configurations and deleting all session files...", WIDTH, "left"), "red")

    # Clear all account-specific entries and reset CURRENT_ACCOUNT
    new_envd = {"CURRENT_ACCOUNT": "0"}
    config.save_env(env_path, new_envd)  # Overwrite .env with just current_account=0

    # Purge all session files
    try:
        session_dir = Path("sessions")
        if session_dir.exists():
            for f in session_dir.iterdir():
                if f.is_file() and f.name.startswith("session_"):
                    f.unlink()
            console_log_func(pad(f"Deleted all files in {session_dir}", WIDTH, "left"), "blue")

        # Also check for state files in base directory (e.g., session_1_state.json)
        # Iterate through potential indices from previous envd to ensure all state files are removed
        for idx in config.get_all_account_indices(envd) + [0]:  # Add 0 in case state for default account exists
            state_manager = StateManager(idx)
            if state_manager.state_file.exists():
                state_manager.delete_state_file()
        console_log_func(pad("Deleted all state files.", WIDTH, "left"), "blue")

    except Exception as e:
        console_log_func(pad(f"Error purging session/state files: {e}", WIDTH, "left"), "red")

    console_log_func(pad("All configurations and session files have been reset.", WIDTH, "left"), "green")


async def run_cli_upload(args):
    env_path = Path(".env")
    current_account_idx = config.get_current_account_index(config.load_env(env_path))

    if current_account_idx == 0:
        console_log_func(pad("No active account found. Please login first using 'cli_app.py login'.", WIDTH, "left"),
                         "red")
        return

    components = await _initialize_downloader_and_uploader_for_command(env_path, current_account_idx)
    if not components:
        return
    client_wrapper, _, uploader = components  # We only need uploader and client_wrapper for disconnect

    try:
        file_or_folder_path = Path(args.path)
        destination = args.to
        caption = args.caption

        if file_or_folder_path.is_file():
            console_log_func(
                pad(f"Starting upload of '{file_or_folder_path.name}' to '{destination}'...", WIDTH, "left"), "blue")
            await uploader.upload_single_media(
                peer=destination,
                file_path=file_or_folder_path,
                caption=caption,
                progress_callback=lambda p, c_bytes, t_bytes: cli_progress_callback(p, c_bytes, t_bytes,
                                                                                    is_single_file_upload=True)
            )
            console_log_func(pad(f"Upload completed successfully for '{file_or_folder_path.name}'.", WIDTH, "left"),
                             "green")
        elif file_or_folder_path.is_dir():
            console_log_func(
                pad(f"Starting batch upload from folder '{file_or_folder_path.name}' to '{destination}'...", WIDTH,
                    "left"), "blue")
            await uploader.upload_folder_media(
                peer=destination,
                folder_path=file_or_folder_path,
                caption=caption,
                progress_callback=lambda overall_p, f_idx, total_f, c_bytes, t_bytes: cli_progress_callback(
                    overall_p, f_idx, total_f, is_folder_upload=True, current_file_bytes=c_bytes,
                    total_file_bytes=t_bytes)
            )
            console_log_func(pad(f"Batch upload from '{file_or_folder_path.name}' completed.", WIDTH, "left"), "green")
        else:
            console_log_func(
                pad(f"Error: Path '{file_or_folder_path}' is neither a file nor a directory.", WIDTH, "left"), "red")

    except Exception as e:
        console_log_func(pad(f"Error during upload: {e}", WIDTH, "left"), "red")
    finally:
        await client_wrapper.disconnect_client()


async def run_cli_download(args):
    env_path = Path(".env")
    current_account_idx = config.get_current_account_index(config.load_env(env_path))

    if current_account_idx == 0:
        console_log_func(pad("No active account found. Please login first using 'cli_app.py login'.", WIDTH, "left"),
                         "red")
        return

    components = await _initialize_downloader_and_uploader_for_command(env_path, current_account_idx)
    if not components:
        return
    client_wrapper, downloader, _ = components  # We only need downloader and client_wrapper for disconnect

    try:
        source_type = args.source
        media_filter = args.filter

        chosen_entities = []
        if source_type == "dialogs" or source_type == "all":
            all_dialogs_info = await downloader.list_dialogs()  # Get all dialogs first
            if source_type == "all":
                chosen_entities = [d['entity'] for d in all_dialogs_info]
            elif source_type == "dialogs":
                if not args.dialogs:
                    console_log_func(pad("--dialogs argument is required for --source dialogs.", WIDTH, "left"), "red")
                    return

                # Filter dialogs based on provided IDs/usernames
                for identifier in args.dialogs:
                    found = False
                    # Try to parse as int ID
                    try:
                        dialog_id = int(identifier)
                        for d_info in all_dialogs_info:
                            if getattr(d_info['entity'], 'id', None) == dialog_id:
                                chosen_entities.append(d_info['entity'])
                                found = True
                                break
                    except ValueError:
                        # If not an int, treat as username
                        if identifier.startswith('@'):  # Ensure it's a username format
                            identifier = identifier[1:]  # Remove '@'
                        for d_info in all_dialogs_info:
                            if d_info['username'] and d_info['username'].lower() == f"@{identifier}".lower():
                                chosen_entities.append(d_info['entity'])
                                found = True
                                break
                    if not found:
                        console_log_func(
                            pad(f"Warning: Could not find dialog '{identifier}'. Skipping.", WIDTH, "left"), "yellow")

                if not chosen_entities:
                    console_log_func(pad("No valid dialogs selected for download.", WIDTH, "left"), "red")
                    return
        elif source_type == "saved":
            # For 'saved', no specific entities are passed, 'me' is handled internally by scan_saved_messages
            chosen_entities = []
        elif source_type == "continue":
            # State manager will handle restoring the entities
            state_data = downloader.state.get_source()
            if not state_data or not state_data.get("type"):
                console_log_func(pad("No previous session found to continue.", WIDTH, "left"), "yellow")
                return False

            # Override source_type and filter_type from state for continue
            source_type = state_data.get("type", "all")  # Default to all if not in state
            media_filter = downloader.state.get_last_filter()

            if source_type == "saved":
                chosen_entities = []  # Signifies 'me'
            else:  # Must be "all" or "dialogs"
                dialog_ids_from_state = state_data.get("dialog_ids", [])
                all_dialogs_info = await downloader.list_dialogs()  # Refresh dialogs
                restored_entities = []
                want_ids = [int(x) for x in dialog_ids_from_state if
                            isinstance(x, (int, str)) and str(x).isdigit() and int(x) != 0]
                for d_info in all_dialogs_info:
                    if hasattr(d_info["entity"], "id") and int(d_info["entity"].id) in want_ids:
                        restored_entities.append(d_info["entity"])
                if not restored_entities:
                    console_log_func(
                        pad("Could not restore dialogs from previous session. Cannot continue.", WIDTH, "left"), "red")
                    return False
                chosen_entities = restored_entities

        # Use a simple lambda for confirm_reset_callback for CLI
        cli_confirm_reset = lambda title, message: console_input_func(f"{title}: {message} (yes/no)", "no",
                                                                      False).lower() == 'yes'

        await downloader.run_download_flow(
            src_type=source_type,
            chosen_entities=chosen_entities,
            media_filter=media_filter,
            confirm_reset_callback=cli_confirm_reset,
            scan_progress_callback=cli_scan_progress_callback,
            download_progress_callback=lambda p, c, t, s_dict: cli_progress_callback(p, c, t, is_download=True)
        )

        console_log_func(pad("Download command finished.", WIDTH, "left"), "green")

    except Exception as e:
        console_log_func(pad(f"Error during download: {e}", WIDTH, "left"), "red")
    finally:
        await client_wrapper.disconnect_client()


async def run_cli_status(args):
    env_path = Path(".env")
    envd = config.load_env(env_path)
    current_account_idx = config.get_current_account_index(envd)

    if current_account_idx == 0:
        console_log_func(c(pad("No active account selected for status.", WIDTH, "left"), "yellow"))
        return

    cfg = config.get_account_config(envd, current_account_idx)

    # Initialize a StateManager to read the state file, no need for full client init/connect
    try:
        # Check if core config for this account is even present
        if not all([cfg["PHONE"], cfg["API_ID"], cfg["API_HASH"]]):
            console_log_func(
                pad(f"Account #{current_account_idx} configuration is incomplete in .env file.", WIDTH, "left"),
                "yellow")
            console_log_func(pad(f"Phone: {cfg['PHONE']}", WIDTH, "left"), "yellow")
            console_log_func(pad(f"API ID: {cfg['API_ID']}", WIDTH, "left"), "yellow")
            console_log_func(pad(f"API Hash: {'*' * len(cfg['API_HASH']) if cfg['API_HASH'] else ''}", WIDTH, "left"),
                             "yellow")
            console_log_func(pad(f"Download Dir: {cfg['DOWNLOAD_DIR']}", WIDTH, "left"), "yellow")
            return

        state_manager = StateManager(current_account_idx)

        lines = [c(pad("ACCOUNT STATUS", WIDTH - 2), "cyan"), pad("", WIDTH - 2)]
        lines.extend(
            [pad(s, WIDTH - 2) for s in state_manager.get_status_lines(Path(cfg['DOWNLOAD_DIR']))])  # Pass download_dir
        console_log_func(c(box(lines), "cyan"))

    except Exception as e:
        console_log_func(pad(f"Error retrieving status for account #{current_account_idx}: {e}", WIDTH, "left"), "red")


# --- Main CLI Entry Point ---

async def cli_main_entry():
    parser = argparse.ArgumentParser(
        description="Telegram Media Downloader and Uploader CLI",
        formatter_class=argparse.RawTextHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    # --- Login/Auth Command ---
    login_parser = subparsers.add_parser("login", help="Log in to a Telegram account or manage accounts.")
    login_parser.add_argument("--phone", help="Phone number for login (e.g., +84123456789)")
    login_parser.add_argument("--api-id", type=int, help="Telegram API ID")
    login_parser.add_argument("--api-hash", help="Telegram API Hash")
    login_parser.add_argument("--download-dir", default="downloads",
                              help="Default download directory for this account.")
    login_parser.set_defaults(func=run_cli_login)

    # --- Logout Command ---
    logout_parser = subparsers.add_parser("logout", help="Logout the current active account or a specific one.")
    logout_parser.add_argument("--account-index", type=int, default=None,
                               help="Optional: Logout a specific account index instead of the current active one.")
    logout_parser.set_defaults(func=run_cli_logout)

    # --- Reset Command ---
    reset_parser = subparsers.add_parser("reset", help="Reset all configurations and delete session files.")
    reset_parser.set_defaults(func=run_cli_reset)

    # --- Upload Command ---
    upload_parser = subparsers.add_parser("upload", help="Upload a file or all media from a folder to Telegram.")
    upload_parser.add_argument("-p", "--path", required=True,
                               help="Path to the file or folder to upload.")
    upload_parser.add_argument("-t", "--to", required=True, help="Destination (chat ID, @username, or phone number).")
    upload_parser.add_argument("-c", "--caption", default="", help="Optional caption for the file(s).")
    upload_parser.set_defaults(func=run_cli_upload)

    # --- Download Command ---
    download_parser = subparsers.add_parser("download", help="Download media from Telegram.")
    download_parser.add_argument("-s", "--source", choices=["saved", "dialogs", "all", "continue"], default="all",
                                 help=(
                                     "Source to download from:\n"
                                     "  - saved: Your 'Saved Messages'\n"
                                     "  - dialogs: Specific chats/channels (requires --dialogs)\n"
                                     "  - all: All chats/channels you are part of\n"
                                     "  - continue: Continue last download session (restores source and filter)"
                                 ))
    download_parser.add_argument("--dialogs", nargs='*',
                                 help="List of dialog IDs or @usernames to download from "
                                      "(required for --source dialogs, e.g., --dialogs 12345 @mychannel). "
                                      "Ignored for 'saved' or 'all'.")
    download_parser.add_argument("-F", "--filter", choices=["1", "2", "3"], default="3",
                                 help=(
                                     "Media type filter:\n"
                                     "  - 1: Photos only\n"
                                     "  - 2: Videos only\n"
                                     "  - 3: Both photos and videos (default)"
                                 ))
    download_parser.set_defaults(func=run_cli_download)

    # --- Status Command ---
    status_parser = subparsers.add_parser("status", help="Show current account status and last session progress.")
    status_parser.set_defaults(func=run_cli_status)

    args = parser.parse_args()

    # Ensure .env file exists before any command runs
    env_path = Path(".env")
    config.ensure_env_exists(env_path)

    # Execute the function associated with the chosen subcommand
    if hasattr(args, 'func'):
        asyncio.run(args.func(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        asyncio.run(cli_main_entry())
    except KeyboardInterrupt:
        console_log_func(pad("CLI operation interrupted. Goodbye!", WIDTH, "left"), "red")
    except Exception as e:
        console_log_func(pad(f"Fatal CLI error: {e}", WIDTH, "left"), "red")
        sys.exit(1)







