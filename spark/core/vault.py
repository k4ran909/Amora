"""Where photos and profile snapshots are permanently stored.

Production: TelegramVault (spark/adapters/telegram/vault.py) - a private Telegram channel acts as the
master copy. Every photo becomes a permanent Telegram file_id, and every profile has a JSON snapshot
document that can rebuild the database.

Local testing without a vault channel: LocalVault writes the same things to data/vault/.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class StoredPhoto:
    tg_file_id: str | None = None
    vault_msg_id: int | None = None
    local_path: str | None = None


class MediaVault(Protocol):
    async def store_photo(self, user_id: int, jpeg: bytes) -> StoredPhoto: ...

    async def delete_photo(self, user_id: int, photo: StoredPhoto) -> None: ...

    async def store_snapshot(self, user_id: int, snapshot: dict, previous_msg_id: int | None) -> int | None: ...

    async def delete_snapshot(self, user_id: int, msg_id: int | None) -> None: ...


class LocalVault:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _dir(self, user_id: int) -> Path:
        path = self.root / f"u{user_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def store_photo(self, user_id: int, jpeg: bytes) -> StoredPhoto:
        path = self._dir(user_id) / f"{uuid.uuid4().hex}.jpg"
        path.write_bytes(jpeg)
        return StoredPhoto(local_path=str(path))

    async def delete_photo(self, user_id: int, photo: StoredPhoto) -> None:
        if photo.local_path:
            Path(photo.local_path).unlink(missing_ok=True)

    async def store_snapshot(self, user_id: int, snapshot: dict, previous_msg_id: int | None) -> int | None:
        path = self._dir(user_id) / "profile.json"
        path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return None

    async def delete_snapshot(self, user_id: int, msg_id: int | None) -> None:
        (self._dir(user_id) / "profile.json").unlink(missing_ok=True)
