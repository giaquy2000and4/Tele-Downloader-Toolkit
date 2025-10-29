# tele-downloader-toolkit/storage/config.py

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    from dotenv import load_dotenv, set_key, dotenv_values
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install python-dotenv")
    sys.exit(1)

# Template for the .env file if it doesn't exist
ENV_TEMPLATE = """# Telegram Media Toolkit Configuration
# Multi-account support: Each account is prefixed with ACCOUNT_N_ where N is the index.
# CURRENT_ACCOUNT specifies which account index is currently active.

CURRENT_ACCOUNT=0

# Example Account Configuration:
# ACCOUNT_1_PHONE=+84123456789
# ACCOUNT_1_API_ID=123456
# ACCOUNT_1_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxx
# ACCOUNT_1_DOWNLOAD_DIR=/absolute/path/to/downloads
#
# You can add more accounts by incrementing the index:
# ACCOUNT_2_PHONE=+84987654321
# ACCOUNT_2_API_ID=987654
# ACCOUNT_2_API_HASH=yyyyyyyyyyyyyyyyyyyyyyyyyyyy
# ACCOUNT_2_DOWNLOAD_DIR=/absolute/path/to/downloads_account_2
"""


def ensure_env_exists(env_path: Path) -> None:
    """
    Ensures that the .env file exists. If not, it creates it with a template.
    """
    if not env_path.exists():
        env_path.write_text(ENV_TEMPLATE, encoding="utf-8")


def load_env(env_path: Path) -> Dict[str, str]:
    """
    Loads environment variables from the .env file into os.environ and returns them as a dictionary.
    """
    # Load into os.environ
    load_dotenv(dotenv_path=str(env_path))
    # Also parse for direct access, as os.environ might be slow or not desired for all lookups
    return dotenv_values(dotenv_path=str(env_path))


def save_env(env_path: Path, data: Dict[str, str]) -> None:
    """
    Saves the provided dictionary data into the .env file.
    Note: set_key updates single keys; for a full overwrite, you might need to rewrite the file.
    This uses set_key which is safer for partial updates.
    """
    for k, v in data.items():
        set_key(dotenv_path=str(env_path), key_to_set=k, value_to_set=v)

    # After saving, reload to ensure internal state (e.g., in os.environ) is consistent
    load_dotenv(dotenv_path=str(env_path), override=True)


def get_current_account_index(envd: Dict[str, str]) -> int:
    """
    Retrieves the currently active account index from the environment data.
    Defaults to 0 if not found or invalid.
    """
    try:
        return int(str(envd.get("CURRENT_ACCOUNT", "0")).strip())
    except ValueError:
        return 0


def get_account_config(envd: Dict[str, str], idx: int) -> Dict[str, str]:
    """
    Retrieves the configuration for a specific account index.
    Prioritizes account-specific config.
    """
    config = {
        "PHONE": envd.get(f"ACCOUNT_{idx}_PHONE", ""),
        "API_ID": envd.get(f"ACCOUNT_{idx}_API_ID", ""),
        "API_HASH": envd.get(f"ACCOUNT_{idx}_API_HASH", ""),
        "DOWNLOAD_DIR": envd.get(f"ACCOUNT_{idx}_DOWNLOAD_DIR", ""),
    }

    # Provide a default download directory if not specified for the account
    if not config["DOWNLOAD_DIR"]:
        config["DOWNLOAD_DIR"] = "downloads"  # A safe default relative to execution dir

    return config


def set_current_account_index(envd: Dict[str, str], idx: int) -> Dict[str, str]:
    """
    Sets the CURRENT_ACCOUNT index in the environment data and returns the updated dictionary.
    """
    envd["CURRENT_ACCOUNT"] = str(idx)
    return envd


def find_next_account_index(envd: Dict[str, str]) -> int:
    """
    Finds the next available integer index for a new account.
    Looks for existing ACCOUNT_N_PHONE keys.
    """
    existing_idxs = {
        int(k.split("_")[1])
        for k in envd.keys()
        if k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()
    }
    return 1 if not existing_idxs else max(existing_idxs) + 1


def update_account_config(envd: Dict[str, str], idx: int, config_data: Dict[str, str]) -> Dict[str, str]:
    """
    Updates the configuration for a specific account index in the environment data.
    """
    for key, value in config_data.items():
        envd[f"ACCOUNT_{idx}_{key.upper()}"] = value
    return envd


def delete_account_config(envd: Dict[str, str], idx: int) -> Dict[str, str]:
    """
    Deletes all configuration entries for a specific account index.
    """
    keys_to_delete = [
        f"ACCOUNT_{idx}_PHONE",
        f"ACCOUNT_{idx}_API_ID",
        f"ACCOUNT_{idx}_API_HASH",
        f"ACCOUNT_{idx}_DOWNLOAD_DIR"
    ]
    for key in keys_to_delete:
        envd.pop(key, None)

    # If the current active account is being deleted, reset CURRENT_ACCOUNT
    if get_current_account_index(envd) == idx:
        envd["CURRENT_ACCOUNT"] = "0"

    return envd


def get_all_account_indices(envd: Dict[str, str]) -> List[int]:
    """
    Returns a sorted list of all existing account indices.
    """
    idxs = {
        int(k.split("_")[1])
        for k in envd.keys()
        if k.startswith("ACCOUNT_") and k.endswith("_PHONE") and k.split("_")[1].isdigit()
    }
    return sorted(list(idxs))
