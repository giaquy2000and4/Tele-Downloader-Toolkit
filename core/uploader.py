# tele-downloader-toolkit/core/uploader.py

import os
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Union, Tuple  # <--- ADDED Tuple HERE

# Assuming TelegramClientWrapper from core/client
from .client import TelegramClientWrapper, LogFuncType

# Telethon types for peer resolution
try:
    from telethon.tl.types import User, Chat, Channel
    from telethon.tl.patched import Message
    from telethon.errors import FloodWaitError, PeerFloodError
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install: pip install telethon")
    sys.exit(1)

# Progress callback type for UI updates (progress_percentage, current_bytes, total_bytes)
# For single file upload.
UploadFileProgressCallback = Callable[[float, int, int], None]

# Progress callback type for folder upload (overall_progress, current_file_index, total_files, current_file_bytes, total_file_bytes)
UploadFolderProgressCallback = Callable[[float, int, int, int, int], None]


class MediaUploader:
    """
    Handles uploading of single media files or entire folders of media
    to Telegram chats/channels/users.
    """

    def __init__(self,
                 client_wrapper: TelegramClientWrapper,
                 log_func: LogFuncType):

        self._client_wrapper = client_wrapper
        self._log_func = log_func

    @property
    def client(self):
        return self._client_wrapper.client

    def is_media_file(self, file_path: Path) -> bool:
        """Checks if a file has a common media extension."""
        if not file_path.is_file():
            return False

        # Common image and video extensions
        media_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp',  # Images
            '.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.gifv'  # Videos (gifv is often a video)
        }
        return file_path.suffix.lower() in media_extensions

    async def upload_single_media(
            self,
            peer: Union[User, Chat, Channel, int, str],  # Can be entity, ID, or username
            file_path: Path,
            caption: Optional[str] = None,
            progress_callback: Optional[UploadFileProgressCallback] = None
    ) -> Optional[Message]:
        """
        Uploads a single media file to a specified peer (user/chat/channel).
        Returns the Telethon Message object if successful, None otherwise.
        """
        if not self._client_wrapper.is_connected():
            self._log_func("Telegram client is not connected. Please ensure you are logged in.", "red")
            raise ConnectionError("Telegram client is not connected.")

        if not file_path.is_file():
            self._log_func(f"File not found at '{file_path}'.", "red")
            raise FileNotFoundError(f"Source file not found: {file_path}")

        if not self.is_media_file(file_path):
            self._log_func(f"File '{file_path.name}' is not a recognized media type. Skipping.", "yellow")
            return None

        peer_entity = None
        peer_name_for_log = str(peer)
        try:
            # Resolve peer entity if it's an ID or username string
            if isinstance(peer, (int, str)):
                self._log_func(f"Resolving destination '{peer}'...", "blue")
                peer_entity = await self._client_wrapper.client.get_entity(peer)
            else:
                peer_entity = peer  # Already an entity object

            # Use entity's title or first_name for logging
            peer_name_for_log = getattr(peer_entity, 'title',
                                        getattr(peer_entity, 'first_name', str(peer))).strip()
            self._log_func(f"Attempting to upload '{file_path.name}' to '{peer_name_for_log}'...", "blue")

        except Exception as e:
            self._log_func(f"Error resolving destination '{peer}': {e}", "red")
            raise ValueError(f"Invalid destination '{peer}'. Please check the ID or username.") from e

        try:
            # Telethon's send_file can take a progress_callback (current, total bytes)
            def telethon_progress_adapter(current: int, total: int):
                if progress_callback:
                    progress = current / total if total > 0 else 0
                    progress_callback(progress, current, total)

            message = await self._client_wrapper.client.send_file(
                peer_entity,
                file=str(file_path),
                caption=caption,
                progress_callback=telethon_progress_adapter
            )
            self._log_func(
                f"Successfully uploaded '{file_path.name}' to '{peer_name_for_log}'. Message ID: {message.id}",
                "green"
            )
            return message
        except (FloodWaitError, PeerFloodError) as e:
            self._log_func(f"Flood control error while uploading '{file_path.name}': {e}", "yellow")
            await asyncio.sleep(getattr(e, 'seconds', 5) + 2)  # Wait if flood error, with a buffer
            raise  # Re-raise after logging and waiting
        except Exception as e:
            self._log_func(f"Error uploading '{file_path.name}' to '{peer_name_for_log}': {e}", "red")
            raise  # Re-raise for caller to handle

    async def upload_folder_media(
            self,
            peer: Union[User, Chat, Channel, int, str],
            folder_path: Path,
            caption: Optional[str] = None,
            progress_callback: Optional[UploadFolderProgressCallback] = None,
            stop_flag: Optional[Callable[[], bool]] = None
    ) -> Tuple[int, int]:  # Returns (uploaded_count, failed_count)
        """
        Uploads all detected media files from a specified folder to a peer.
        """
        if not self._client_wrapper.is_connected():
            self._log_func("Telegram client is not connected. Please ensure you are logged in.", "red")
            raise ConnectionError("Telegram client is not connected.")
        if not folder_path.is_dir():
            self._log_func(f"Folder not found at '{folder_path}'.", "red")
            raise FileNotFoundError(f"Source folder not found: {folder_path}")
        if stop_flag is None:
            stop_flag = lambda: False  # Default to always continue

        media_files = [f for f in folder_path.iterdir() if self.is_media_file(f)]
        if not media_files:
            self._log_func(f"No media files found in '{folder_path}'.", "yellow")
            return 0, 0

        total_files = len(media_files)
        uploaded_count = 0
        failed_count = 0

        self._log_func(
            f"Starting batch upload of {total_files} media files from '{folder_path.name}'...",
            "blue"
        )

        # Resolve peer entity once to avoid repeated calls in loop
        peer_entity = None
        peer_name_for_log = str(peer)
        try:
            if isinstance(peer, (int, str)):
                peer_entity = await self._client_wrapper.client.get_entity(peer)
            else:
                peer_entity = peer
            peer_name_for_log = getattr(peer_entity, 'title',
                                        getattr(peer_entity, 'first_name', str(peer))).strip()
            self._log_func(f"Resolved destination: '{peer_name_for_log}'", "blue")
        except Exception as e:
            self._log_func(f"Error resolving destination '{peer}': {e}", "red")
            raise ValueError(f"Invalid destination '{peer}'. Please check the ID or username.") from e

        for i, file_path in enumerate(media_files):
            if stop_flag():
                self._log_func("Upload stopped by user.", "red")
                break

            self._log_func(f"[{i + 1}/{total_files}] Uploading '{file_path.name}'...", "blue")

            # Inner progress callback for the single file being uploaded
            def file_progress_adapter(progress_percentage: float, current_bytes: int, total_bytes: int):
                if progress_callback:
                    # overall_progress considers total files and current file's progress
                    overall_progress = (uploaded_count + failed_count + progress_percentage) / total_files
                    progress_callback(overall_progress, i + 1, total_files, current_bytes, total_bytes)

            try:
                await self.upload_single_media(
                    peer_entity,  # Use the already resolved entity
                    file_path,
                    caption,
                    progress_callback=file_progress_adapter
                )
                uploaded_count += 1
            except Exception as e:
                failed_count += 1
                self._log_func(f"Failed to upload '{file_path.name}': {e}", "red")

            # Ensure overall progress is updated even if a file fails or finishes without final callback from Telethon
            if progress_callback:
                # Update overall progress for this file's completion (or failure)
                overall_progress = (uploaded_count + failed_count) / total_files
                progress_callback(overall_progress, i + 1, total_files, 0,
                                  0)  # Current/total file bytes 0 for completion

        self._log_func(
            f"Batch upload finished. Uploaded {uploaded_count}/{total_files} files. Failed: {failed_count}",
            "green" if failed_count == 0 else "yellow"
        )
        return uploaded_count, failed_count