# tele-downloader-toolkit/core/state_manager.py

import json
from pathlib import Path
from datetime import datetime
import hashlib
from typing import List, Dict, Any, Optional, Union


class StateManager:
    """
    Manages the persistent state for a specific account's download sessions.
    Stores information about the source, completed messages, and download preferences.
    """

    def __init__(self, account_index: int):
        self.account_index = int(account_index)
        self.state_file = Path(f"session_{self.account_index}_state.json")
        self.state: Dict[str, Any] = {
            "account_index": self.account_index,
            "source": {},
            "completed_ids": [],
            "total_found": 0,
            "ids_hash": "",
            "last_filter": "3",
            "last_updated": None,
        }
        self._load()

    def _load(self):
        """Loads the state from the JSON file."""
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                if int(data.get("account_index", -1)) == self.account_index:
                    self.state.update(data)
        except Exception:
            pass

    def save(self):
        """Saves the current state to the JSON file."""
        self.state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def set_source(self,
                   source_type: str,
                   dialog_ids: Union[List[int], List[str]],
                   total_found: int = 0,
                   ids_hash: str = "",
                   last_filter: Optional[str] = None):
        """
        Sets the source information for the current session.
        Automatically saves the state.
        """
        self.state["source"] = {"type": source_type, "dialog_ids": dialog_ids}
        if total_found:
            self.state["total_found"] = int(total_found)
        if ids_hash:
            self.state["ids_hash"] = ids_hash
        if last_filter is not None:
            self.state["last_filter"] = str(last_filter)
        self.save()

    def mark_completed(self, message_id: int):
        """Marks a message ID as completed and saves the state."""
        if int(message_id) not in self.state["completed_ids"]:
            self.state["completed_ids"].append(int(message_id))
            self.save()

    def is_completed(self, message_id: int) -> bool:
        """Checks if a message ID has been marked as completed."""
        return int(message_id) in set(self.state.get("completed_ids", []))

    def completed_count(self) -> int:
        """Returns the number of completed messages."""
        return len(self.state.get("completed_ids", []))

    def total_found(self) -> int:
        """Returns the total number of media items found in the last scan."""
        return int(self.state.get("total_found", 0))

    def source_label(self) -> str:
        """Returns a human-readable label for the current source."""
        s = self.state.get("source", {})
        typ = s.get("type", "unknown")
        ids = s.get("dialog_ids", [])
        if typ == "saved":
            return "Saved Messages (me)"
        if typ == "all":
            return f"All dialogs/channels ({len(ids)} sources)"
        if typ == "dialogs":
            return f"Selected dialogs ({len(ids)} sources)"
        return "unknown"

    def get_status_lines(self, download_dir: Path) -> List[str]:
        """Returns a list of status strings suitable for display in UI."""
        return [
            f"Account: #{self.account_index}",
            f"Source: {self.source_label()}",
            f"Progress: {self.completed_count()}/{self.total_found()}",
            f"Download directory: {download_dir}",
            f"Media list hash: {self.state.get('ids_hash') or '-'}",
            f"Last filter: {self.state.get('last_filter', '3')}",
            f"Last updated: {self.state.get('last_updated') or '-'}",
        ]

    def get_source(self) -> Dict[str, Any]:
        """Returns the raw source dictionary from the state."""
        return self.state.get("source", {})

    def get_last_filter(self) -> str:
        """Returns the last used media filter type."""
        return str(self.state.get("last_filter", "3"))

    def clear_progress(self):
        """Clears the completed message IDs and total found count, and resets the media list hash."""
        self.state["completed_ids"] = []
        self.state["total_found"] = 0
        self.state["ids_hash"] = ""
        self.save()

    def delete_state_file(self):
        """Deletes the state file from disk."""
        if self.state_file.exists():
            self.state_file.unlink()



