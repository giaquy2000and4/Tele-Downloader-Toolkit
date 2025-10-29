# tele-downloader-toolkit/ui/cli/formatters.py

import sys
import os
import re  # Import re for regex operations
from typing import Optional, Dict, Any, Callable, List

try:
    from colorama import Fore, Style
    import colorama
except ImportError:
    class NoColor:
        def __getattr__(self, name):
            return ''


    Fore = NoColor()
    Style = NoColor()
    colorama = None

try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, **kwargs: x  # Dummy tqdm if not installed

import getpass  # For sensitive input in CLI
import humanize  # For human-readable sizes

# ============================ UI Configuration (Console-specific) =============================

WIDTH = 78
USE_COLOR = True
BAR_CHAR = "─"

if colorama:
    colorama.init(autoreset=True)


def _strip_ansi_codes(s: str) -> str:
    """Removes ANSI escape codes from a string to get its visible length."""
    # This regex matches common ANSI escape sequences for colors and cursor movements.
    return re.sub(r'\x1b\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]', '', s)


def c(text: str, color: Optional[str]) -> str:
    """Applies ANSI color to text if USE_COLOR is True and color_tag is provided."""
    if not USE_COLOR or color is None:
        return text
    color_map = {
        "red": Fore.RED,
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "blue": Fore.BLUE,
        "cyan": Fore.CYAN,
        "reset": Style.RESET_ALL  # For completeness, not directly used in f-string
    }
    prefix = color_map.get(color.lower(), "")
    if prefix:
        return f"{prefix}{text}{Style.RESET_ALL}"
    return text


def pad(text: str, width: int = WIDTH, align: str = "left") -> str:
    """Pads text to a given width with optional alignment, accounting for ANSI codes."""
    text = text if text is not None else ""
    # strip ANSI escape codes before calculating length for padding
    clean_text = _strip_ansi_codes(text)

    # Calculate how many extra characters ANSI codes add to the string's length
    ansi_code_length = len(text) - len(clean_text)

    # If the clean text is already too long, truncate it visually
    if len(clean_text) > width:
        # Truncate the clean text part, then add "..."
        truncated_clean = clean_text[: width - 3] + "..."
        # Reconstruct the string: this is a simplification. Ideally, you'd apply
        # the original colors to the truncated part, but that's complex.
        # For CLI output, simply truncating the plain text is usually acceptable.
        return truncated_clean.ljust(width)  # Pad based on visual width

    # Pad the original string (with ANSI codes) but using the clean text's length
    # to ensure correct visual alignment.
    if align == "left":
        return text.ljust(width + ansi_code_length)
    elif align == "right":
        return text.rjust(width + ansi_code_length)
    else:
        return text.center(width + ansi_code_length)


def line(char: str = BAR_CHAR, width: int = WIDTH) -> str:
    """Generates a horizontal line of characters."""
    return char * width


def box(lines: List[str], width: int = WIDTH) -> str:
    """Draws a box around a list of text lines, accounting for ANSI codes."""
    inner_width = width - 2
    top = "┌" + ("─" * inner_width) + "┐"
    bottom = "└" + ("─" * inner_width) + "┘"

    formatted_inner_lines = []
    for s in lines:
        clean_s = _strip_ansi_codes(s)
        ansi_code_length = len(s) - len(clean_s)

        if len(clean_s) > inner_width:
            # Truncate visually, then pad
            display_s = clean_s[:inner_width - 3] + "..."
            display_s_padded = display_s.ljust(inner_width)
        else:
            # Pad the original string (with ANSI codes) to the required visual width
            display_s_padded = s.ljust(inner_width + ansi_code_length)

        formatted_inner_lines.append("│" + display_s_padded + "│")

    # Fix: Extract newline character outside of f-string expression
    newline = '\n'
    inner_content = newline.join(formatted_inner_lines)
    return f"{top}{newline}{inner_content}{newline}{bottom}"


# ============================ CLI-specific I/O Functions =============================

def console_log_func(message: str, color_tag: Optional[str] = None):
    """
    Simple console logger.
    Used by core components when running in CLI mode.
    """
    print(c(message, color_tag))


def console_input_func(prompt: str, default: Optional[str] = None, hide_input: bool = False) -> str:
    """
    Simple console input.
    Used by core components when running in CLI mode.
    """
    if hide_input:
        try:
            return getpass.getpass(prompt + ": ")
        except Exception:
            console_log_func("Warning: getpass failed, input will be echoed.", "yellow")
            return input(prompt + ": ")

    full_prompt = prompt
    if default is not None:
        full_prompt += f" (default: {default})"

    user_input = input(full_prompt + ": ")
    return user_input.strip() or (default or "")


# CLI progress callback for download and upload
def cli_progress_callback(
        progress: float,
        current_processed_items_or_bytes: int,  # current (files processed or bytes uploaded)
        total_items_or_bytes: int,  # total (files to process or bytes to upload)
        is_download: bool = False,
        is_single_file_upload: bool = False,
        is_folder_upload: bool = False,
        current_file_bytes: Optional[int] = None,  # Used for folder upload, current bytes of THIS file
        total_file_bytes: Optional[int] = None  # Used for folder upload, total bytes of THIS file
):
    bar_length = 50
    filled_length = int(bar_length * progress)
    bar = '#' * filled_length + '-' * (bar_length - filled_length)
    percent = f"{progress * 100:.1f}"

    message_content = ""

    if is_folder_upload:
        file_progress_str = ""
        if current_file_bytes is not None and total_file_bytes is not None and total_file_bytes > 0:
            file_progress_str = f" (File: {humanize.naturalsize(current_file_bytes)}/{humanize.naturalsize(total_file_bytes)})"
        message_content = f'Folder Upload: [{current_processed_items_or_bytes}/{total_items_or_bytes}] |{bar}| {percent}%{file_progress_str}'
    elif is_single_file_upload:
        message_content = f'Single Upload: |{bar}| {percent}% ({humanize.naturalsize(current_processed_items_or_bytes)}/{humanize.naturalsize(total_items_or_bytes)})'
    elif is_download:
        message_content = f'Download: |{bar}| {percent}% ({current_processed_items_or_bytes}/{total_items_or_bytes} files)'
    else:
        message_content = f'Progress: |{bar}| {percent}% ({current_processed_items_or_bytes}/{total_items_or_bytes})'

    sys.stdout.write("\r{}".format(message_content))
    sys.stdout.flush()
    if progress >= 1.0:
        sys.stdout.write('\n')


def cli_scan_progress_callback(current_messages_scanned: int, total_messages: Optional[int]):
    """
    Callback for scan progress in CLI.
    total_messages is often not known upfront during iteration.
    """
    message_content = f'Scanning... Processed {current_messages_scanned} messages. '
    sys.stdout.write("\r{}".format(message_content))
    sys.stdout.flush()
    if total_messages is not None and current_messages_scanned >= total_messages:
        sys.stdout.write('\n')