# tele-downloader-toolkit/core/downloader.py

import os
import sys
import hashlib
import time
import humanize
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Union

from .client import TelegramClientWrapper, LogFuncType, InputFuncType
from .state_manager import StateManager

try:
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, User, Chat, Channel
    from telethon.errors import FloodWaitError, PeerFloodError
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install telethon")
    sys.exit(1)

DownloadProgressCallback = Callable[[float, int, int, Dict[str, Any]], None]
ScanProgressCallback = Callable[[int, Optional[int]], None]


class MediaDownloader:
    """
    Handles scanning for media in Telegram dialogs, filtering, and downloading.
    It orchestrates operations using TelegramClientWrapper and StateManager.
    """

    def __init__(self,
                 client_wrapper: TelegramClientWrapper,
                 download_dir: Path,
                 account_index: int,
                 log_func: LogFuncType):

        self._client_wrapper = client_wrapper
        self._log_func = log_func
        self.download_dir = download_dir
        self.account_index = account_index

        self.state = StateManager(self.account_index)

        self.download_dir.mkdir(parents=True, exist_ok=True)

        self.stats = {
            'total_found': 0,
            'images_found': 0,
            'videos_found': 0,
            'downloaded': 0,
            'skipped': 0,
            'errors': 0,
            'total_size': 0,
        }

        self.media_list: List[Dict[str, Any]] = []

    @property
    def client(self):
        return self._client_wrapper.client

    async def list_dialogs(self) -> List[dict]:
        """
        Fetches all dialogs (chats/channels/users) for the current account.
        Returns a list of dictionaries containing dialog information.
        """
        self._log_func("Fetching dialogs (chats/channels)...", "blue")
        rows = []
        idx = 0
        try:
            async for d in self._client_wrapper.client.iter_dialogs():
                entity = d.entity
                etype = entity.__class__.__name__
                title = (getattr(d, "name", None) or getattr(entity, "title", None)
                         or getattr(entity, "first_name", None) or "Unknown").strip()
                uname = f"@{getattr(entity, 'username', '')}" if getattr(entity, 'username', None) else ""
                idx += 1
                rows.append({
                    "index": idx,
                    "dialog": d,
                    "entity": entity,
                    "title": title,
                    "username": uname,
                    "etype": etype,
                    "id": getattr(entity, 'id', None)
                })
        except Exception as e:
            self._log_func(f"Error fetching dialogs: {e}", "red")
        self._log_func(f"Found {len(rows)} dialogs.", "blue")
        return rows

    async def scan_media_in_dialogs(self,
                                    dialog_entities: List[Union[User, Chat, Channel]],
                                    progress_callback: Optional[ScanProgressCallback] = None
                                    ) -> List[Dict[str, Any]]:
        """
        Scans specified dialog entities for media messages.
        Returns a list of dictionaries, each describing a media message.
        """
        dialog_titles = ", ".join([getattr(e, 'title', getattr(e, 'first_name', str(e))) for e in dialog_entities])
        self._log_func(f"Scanning {len(dialog_entities)} dialog(s) for media: {dialog_titles[:100]}...", "blue")
        media_messages: List[Dict[str, Any]] = []
        message_count = 0
        self.stats = {
            'total_found': 0, 'images_found': 0, 'videos_found': 0,
            'downloaded': 0, 'skipped': 0, 'errors': 0, 'total_size': 0,
        }

        for entity in dialog_entities:
            try:
                async for message in self._client_wrapper.client.iter_messages(entity):
                    message_count += 1
                    if progress_callback:
                        progress_callback(message_count, None)

                    if not getattr(message, "media", None):
                        continue
                    if isinstance(message.media, MessageMediaPhoto):
                        self.stats['images_found'] += 1
                        media_messages.append({'message': message, 'type': 'photo', 'date': message.date})
                    elif isinstance(message.media, MessageMediaDocument):
                        doc = message.media.document
                        mime = getattr(doc, "mime_type", "") or ""
                        if mime.startswith("video/"):
                            self.stats['videos_found'] += 1
                            media_messages.append({'message': message, 'type': 'video', 'date': message.date})
                        elif mime.startswith("image/"):
                            self.stats['images_found'] += 1
                            media_messages.append({'message': message, 'type': 'photo', 'date': message.date})
            except Exception as e:
                self._log_func(f"Error scanning dialog {getattr(entity, 'title', str(entity))}: {e}", "red")

        self.stats['total_found'] = len(media_messages)
        if progress_callback:
            progress_callback(message_count, message_count)

        self._log_func(
            f"Found {len(media_messages)} media in {message_count} messages across {len(dialog_entities)} dialog(s).",
            "blue"
        )
        return media_messages

    async def scan_saved_messages(self,
                                  progress_callback: Optional[ScanProgressCallback] = None
                                  ) -> List[Dict[str, Any]]:
        """
        Scans 'Saved Messages' for media.
        Returns a list of dictionaries, each describing a media message.
        """
        self._log_func("Scanning Saved Messages...", "blue")
        media_messages: List[Dict[str, Any]] = []
        message_count = 0
        self.stats = {
            'total_found': 0, 'images_found': 0, 'videos_found': 0,
            'downloaded': 0, 'skipped': 0, 'errors': 0, 'total_size': 0,
        }

        try:
            async for message in self._client_wrapper.client.iter_messages('me'):
                message_count += 1
                if progress_callback:
                    progress_callback(message_count, None)

                if not getattr(message, "media", None):
                    continue
                if isinstance(message.media, MessageMediaPhoto):
                    self.stats['images_found'] += 1
                    media_messages.append({'message': message, 'type': 'photo', 'date': message.date})
                elif isinstance(message.media, MessageMediaDocument):
                    doc = message.media.document
                    mime = getattr(doc, "mime_type", "") or ""
                    if mime.startswith("video/"):
                        self.stats['videos_found'] += 1
                        media_messages.append({'message': message, 'type': 'video', 'date': message.date})
                    elif mime.startswith("image/"):
                        self.stats['images_found'] += 1
                        media_messages.append({'message': message, 'type': 'photo', 'date': message.date})
        except Exception as e:
            self._log_func(f"Error scanning Saved Messages: {e}", "red")

        self.stats['total_found'] = len(media_messages)
        if progress_callback:
            progress_callback(message_count, message_count)

        self._log_func(f"Found {len(media_messages)} media in {message_count} messages.", "blue")
        return media_messages

    def _ext_from_mime_or_name(self, mime: str, name: Optional[str]) -> str:
        """Determines file extension based on MIME type or original file name."""
        if name and "." in name:
            return "." + name.split(".")[-1].lower()
        if mime.startswith("video/"):
            return ".mp4"
        if mime.startswith("image/"):
            if 'png' in mime: return '.png'
            if 'gif' in mime: return '.gif'
            return ".jpg"
        return ""

    def _target_path_for(self, media_info: Dict[str, Any]) -> Path:
        """Generates a unique target file path for a media message."""
        message = media_info['message']
        file_type = media_info['type']

        year_folder = self.download_dir / str(message.date.year)
        month_folder = year_folder / f"{message.date.month:02d}"
        month_folder.mkdir(parents=True, exist_ok=True)

        if file_type == 'photo':
            return month_folder / f"photo_{message.id}.jpg"
        else:
            doc = message.media.document
            mime = getattr(doc, "mime_type", "") or ""
            orig_name = None
            for attr in getattr(doc, "attributes", []):
                if hasattr(attr, 'file_name') and getattr(attr, 'file_name'):
                    orig_name = attr.file_name
                    break
            ext = self._ext_from_mime_or_name(mime, orig_name)
            return month_folder / f"video_{message.id}{ext}"

    @staticmethod
    def _hash_ids(ids: List[int]) -> str:
        """Generates a stable SHA256 hash from a list of message IDs."""
        b = ",".join(str(i) for i in sorted(set(int(x) for x in ids))).encode("utf-8")
        return hashlib.sha256(b).hexdigest()

    async def download_media_batch(self,
                                   media_list: List[Dict[str, Any]],
                                   stop_flag: Callable[[], bool],
                                   progress_callback: Optional[DownloadProgressCallback] = None) -> None:
        """
        Downloads a batch of media files from the given list.
        stop_flag: a callable that returns True if the download should stop.
        progress_callback: a callable for UI updates (progress, current_processed, total_items, stats).
        """
        total_items = len(media_list)
        current_processed = 0

        self._log_func(f"Starting download of {total_items} media items.", "blue")

        for item in media_list:
            if stop_flag():
                self._log_func("Download stopped by user.", "red")
                break

            msg = item["message"]
            target_path = self._target_path_for(item)

            if self.state.is_completed(int(msg.id)) or (target_path.exists() and os.path.getsize(target_path) > 0):
                self.stats['skipped'] += 1
                self.state.mark_completed(int(msg.id))
                self._log_func(f"Skipping Message ID {msg.id}: Already downloaded or file exists.", "yellow")
            else:
                try:
                    self._log_func(f"Downloading Message ID {msg.id} to {target_path.name}...", "blue")

                    path_str = await self._client_wrapper.client.download_media(msg, file=str(target_path))

                    if path_str and Path(path_str).exists():
                        size = os.path.getsize(path_str)
                        self.stats['downloaded'] += 1
                        self.stats['total_size'] += size
                        self.state.mark_completed(int(msg.id))
                        self._log_func(f"Successfully downloaded: {target_path.name} ({humanize.naturalsize(size)})",
                                       "green")
                    else:
                        raise Exception("Downloaded file path is invalid or file not found.")

                except FloodWaitError as e:
                    self._log_func(
                        f"Flood wait error while downloading: Waiting {e.seconds} seconds...",
                        "yellow"
                    )
                    await asyncio.sleep(e.seconds + 5)
                    self.stats['errors'] += 1
                except PeerFloodError:
                    self._log_func(
                        f"Peer flood error. Too many requests to this peer. Skipping for now.",
                        "yellow"
                    )
                    self.stats['errors'] += 1
                except Exception as e:
                    self.stats['errors'] += 1
                    self._log_func(f"Error downloading message ID {msg.id}: {e}", "red")

            current_processed += 1
            progress = current_processed / total_items if total_items > 0 else 0
            if progress_callback:
                progress_callback(progress, current_processed, total_items, self.stats.copy())

        if progress_callback:
            progress_callback(1.0, total_items, total_items, self.stats.copy())

        self._log_func("All media download attempts processed.", "blue")

    async def run_download_flow(self,
                                src_type: str,
                                chosen_entities: Optional[List[Union[User, Chat, Channel]]] = None,
                                media_filter: str = "3",
                                confirm_reset_callback: Optional[Callable[[str, str], bool]] = None,
                                scan_progress_callback: Optional[ScanProgressCallback] = None,
                                download_progress_callback: Optional[DownloadProgressCallback] = None,
                                stop_flag: Optional[Callable[[], bool]] = None
                                ) -> bool:
        """
        Executes the full media download flow: scan, filter, check state, and download.
        Returns True if successful, False otherwise or if cancelled.
        """
        if stop_flag is None:
            stop_flag = lambda: False

        if src_type == "saved":
            scanned_media = await self.scan_saved_messages(scan_progress_callback)
            dialog_ids_for_state = ["me"]
        elif src_type == "all" or src_type == "dialogs":
            if not chosen_entities:
                self._log_func("No entities provided for scanning.", "red")
                return False
            scanned_media = await self.scan_media_in_dialogs(chosen_entities, scan_progress_callback)
            dialog_ids_for_state = [int(getattr(e, 'id', 0)) for e in chosen_entities if getattr(e, 'id', 0)]
        else:
            self._log_func(f"Unknown source type: {src_type}", "red")
            return False

        if not scanned_media:
            self._log_func("No media found for download.", "yellow")
            self.media_list = []
            return False

        self.media_list = scanned_media

        current_message_ids = [int(m['message'].id) for m in scanned_media]
        ids_hash = self._hash_ids(current_message_ids)

        prev_source = self.state.get_source()
        hash_mismatch = False
        if prev_source and prev_source.get("type") == src_type:
            prev_dialog_ids = [int(x) for x in prev_source.get("dialog_ids", []) if str(x).isdigit()]
            cur_dialog_ids = [int(x) for x in dialog_ids_for_state if str(x).isdigit()]

            if sorted(prev_dialog_ids) == sorted(cur_dialog_ids):
                prev_hash = self.state.state.get("ids_hash", "")
                if prev_hash and prev_hash != ids_hash:
                    hash_mismatch = True

        self.state.set_source(src_type, dialog_ids_for_state, total_found=len(scanned_media), ids_hash=ids_hash,
                              last_filter=media_filter)

        if hash_mismatch:
            self._log_func("Media list changed since last session (hash mismatch).", "yellow")
            should_reset = False
            if confirm_reset_callback:
                should_reset = confirm_reset_callback("Confirm Reset Progress",
                                                      "Media list has changed since last session. Reset progress?")
            else:
                self._log_func("No confirmation callback provided for hash mismatch. Cannot prompt for reset.", "red")
                should_reset = False

            if should_reset:
                self.state.clear_progress()
                self._log_func("Progress reset.", "green")
            else:
                self._log_func("Continuing with existing progress.", "yellow")

        filtered_media = self.filter_media_list(scanned_media, media_filter)
        if not filtered_media:
            self._log_func("No media found after applying filter.", "yellow")
            return False

        resumable_media = []
        initial_skipped_count = 0
        for m in filtered_media:
            mid = int(m['message'].id)
            target = self._target_path_for(m)
            if self.state.is_completed(mid) or (target.exists() and os.path.getsize(target) > 0):
                initial_skipped_count += 1
                self.state.mark_completed(mid)
                continue
            resumable_media.append(m)

        self.stats['skipped'] = initial_skipped_count

        if not resumable_media:
            self._log_func("No items left to download (all completed or skipped).", "green")
            return True

        if stop_flag():
            self._log_func("Download aborted before starting.", "red")
            return False

        await self.download_media_batch(resumable_media, stop_flag, download_progress_callback)

        return True

    def filter_media_list(self, media_list: List[Dict[str, Any]], filter_type: str) -> List[Dict[str, Any]]:
        """
        Filters a list of media messages based on the specified type.
        filter_type: "1" for photos, "2" for videos, "3" for both.
        """
        if filter_type == "1":
            return [m for m in media_list if m['type'] == 'photo']
        elif filter_type == "2":
            return [m for m in media_list if m['type'] == 'video']
        else:
            return media_list