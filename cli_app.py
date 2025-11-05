### File: `tele-downloader-toolkit/cli_app.py`
# !/usr/bin/env python3
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ui.cli.commands import cli_main_entry

if __name__ == "__main__":
    cli_main_entry()


