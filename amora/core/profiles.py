"""Profile service: the single place that creates, edits, submits and deletes profiles.

Platform adapters (Telegram, Discord) call into this and never touch the database directly.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from amora.config import Settings
from amora.core.photos import FaceEngine, PhotoCheck
from amora.core.vault import LocalVault, MediaVault, StoredPhoto
from amora.db.models import AdminAction, Photo, PlatformAccount, User, UserStatus

log = logging.getLogger(__name__)

EDITABLE_FIELDS = {
    "terms_accepted_at", "biometric_consent_at", "dob", "gender", "show_me", "looking_for",
    "display_name", "bio", "city", "lat", "lon", "lang", "interests",
}
# Wiped by reset_profile. DOB is deliberately NOT here: once set it never changes, so nobody can "retry" their age.
PROFILE_FIELDS = ("gender","show_me", "looking_for", "display_name", "bio", "city", "lat", "lon", "interests")


class ProfileError(Exception):
    """A user-facing problem (message is safe to show)."""


class ProfileService:
    def __init__(self, sessions: async_sessionmaker, settings: Settings, face: FaceEngine,
                 vault: MediaVault | None = None):
        self.sessions = sessions
        self.s = settings
        self.face = face
        self.vault: MediaVault = vault or LocalVault(settings.data_dir / "vault")
        self._fernet = Fernet(settings.fernet_key.encode())
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------ accounts
    async def get_or_create(self, platform: str, platform_user_id: int | str, username: str | None) -> User:
        pid = str(platform_user_id)
        async with self.sessions() as session, session.begin():
            account = await session.scalar(
                select(PlatformAccount).where(PlatformAccount.platform == platform,
                                              PlatformAccount.platform_user_id == pid)
            )
            if account is None:
                user = User()
                user.accounts.append(PlatformAccount(platform=platform, platform_user_id=pid, username=username))
                session.add(user)
                await session.flush()
                user_id = user.id
                log.info("new user %s via %s", user_id, platform)
            else:
                if username and account.username != username:
                    account.username = username
                user_id = account.user_id
                await session.execute(
                    User.__table__.update().where(User.id == user_id).values(last_active_at=datetime.now(timezone.utc))
                )
        return await self.get(user_id)

    async def get(self, user_id: int) -> User:
        async with self.sessions() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise ProfileError("Profile not found.")
            return user

    async def find_by_platform(self, platform: str, platform_user_id: int | str) -> User | None:
        async with self.sessions() as session:
            account = await session.scalar(
                select(PlatformAccount).where(PlatformAccount.platform == platform,
                                              PlatformAccount.platform_user_id == str(platform_user_id))
            )
            return await session.get(User, account.user_id) if account else None

    # ------------------------------------------------------------------ editing
    async def update(self, user_id: int, **fields: Any) -> User:
        unknown = set(fields) - EDITABLE_FIELDS
        if unknown:
            raise ValueError(f"not editable: {unknown}")
        async with self.sessions() as session, session.begin():
            user = await session.get(User, user_id)
            for key, value in fields.items():
                setattr(user, key, value)
        return await self.get(user_id)

    async def mark_underage(self, user_id: int) -> None:
        """Permanent block. Profile data is wiped; the account row stays so the person can't simply retry."""
        await self.reset_profile(user_id)
        await self._set_status(user_id, UserStatus.UNDERAGE)

    async def reset_profile(self, user_id: int) -> User:
        """Wipe profile fields and photos (keeps terms/consent) so the user can start again."""
        async with self._locks[user_id]:
            user = await self.get(user_id)
            for photo in user.photos:
                await self._safe_vault_delete_photo(user_id, photo)
            async with self.sessions() as session, session.begin():
                db_user = await session.get(User, user_id)
                for photo in list(db_user.photos):
                    await session.delete(photo)
                for key in PROFILE_FIELDS:
                    setattr(db_user, key, [] if key in ("show_me", "interests") else None)
                if db_user.status in (UserStatus.ACTIVE, UserStatus.PENDING, UserStatus.REJECTED, UserStatus.PAUSED):
                    db_user.status = UserStatus.ONBOARDING
                db_user.is_verified = False
                db_user.verified_at = None
        return await self.get(user_id)

    # ------------------------------------------------------------------ photos
    async def add_photo(self, user_id: int, raw: bytes) -> tuple[PhotoCheck, User]:
        if len(raw) > self.s.max_upload_bytes:
            raise ProfileError("That file is too big (max 10 MB).")
        async with self._locks[user_id]:  # albums arrive as parallel messages; keep positions consistent
            user = await self.get(user_id)
            if len(user.photos) >= self.s.max_photos:
                raise ProfileError(f"You already have {self.s.max_photos} photos, which is the maximum.")
            is_main = not user.photos
            main_embedding = None if is_main else self._decrypt(user.photos[0].face_embedding)
            known = await self._hashes_of_other_users(user_id)

            check = await asyncio.to_thread(
                self.face.check, raw, is_main=is_main, main_embedding=main_embedding, known_hashes=known
            )
            if not check.ok:
                return check, user

            stored = await self.vault.store_photo(user_id, check.jpeg)
            async with self.sessions() as session, session.begin():
                session.add(Photo(
                    user_id=user_id, position=len(user.photos),
                    tg_file_id=stored.tg_file_id, vault_msg_id=stored.vault_msg_id, local_path=stored.local_path,
                    width=check.width, height=check.height, phash=check.phash,
                    face_score=check.face_score, match_score=check.match_score,
                    face_embedding=self._encrypt(check.embedding),
                ))
            return check, await self.get(user_id)

    async def remove_last_photo(self, user_id: int) -> User:
        async with self._locks[user_id]:
            user = await self.get(user_id)
            if not user.photos:
                return user
            last = user.photos[-1]
            await self._safe_vault_delete_photo(user_id, last)
            async with self.sessions() as session, session.begin():
                await session.delete(await session.get(Photo, last.id))
            return await self.get(user_id)

    async def _hashes_of_other_users(self, user_id: int) -> list[str]:
        # Fine up to ~100k photos; swap for a BK-tree / pg extension when the user base grows.
        async with self.sessions() as session:
            return list(await session.scalars(select(Photo.phash).where(Photo.user_id != user_id)))

    def _encrypt(self, embedding: np.ndarray) -> bytes:
        return self._fernet.encrypt(np.asarray(embedding, dtype=np.float32).tobytes())

    def _decrypt(self, blob: bytes) -> np.ndarray:
        return np.frombuffer(self._fernet.decrypt(blob), dtype=np.float32).reshape(1, -1).copy()

    async def _safe_vault_delete_photo(self, user_id: int, photo: Photo) -> None:
        try:
            await self.vault.delete_photo(user_id, StoredPhoto(photo.tg_file_id, photo.vault_msg_id, photo.local_path))
        except Exception:
            log.exception("vault photo delete failed (user %s, photo %s)", user_id, photo.id)

    # ------------------------------------------------------------------ submit / review
    def missing_steps(self, user: User) -> list[str]:
        missing = []
        if not user.terms_accepted_at:
            missing.append("terms")
        if not user.dob:
            missing.append("dob")
        if not user.gender:
            missing.append("gender")
        if not user.show_me:
            missing.append("show_me")
        if not user.looking_for:
            missing.append("looking_for")
        if not user.display_name:
            missing.append("name")
        if not user.city and user.lat is None:
            missing.append("location")
        if not user.bio:
            missing.append("bio")
        if len(user.interests or []) < self.s.min_interests:
            missing.append("interests")
        if not user.biometric_consent_at:
            missing.append("consent")
        if len(user.photos) < self.s.min_photos:
            missing.append("photos")
        return missing

    async def submit(self, user_id: int) -> User:
        user = await self.get(user_id)
        if user.status not in (UserStatus.ONBOARDING, UserStatus.REJECTED):
            raise ProfileError("This profile has already been submitted.")
        missing = self.missing_steps(user)
        if missing:
            raise ProfileError("Your profile isn't complete yet: " + ", ".join(missing))
        await self._set_status(user_id, UserStatus.PENDING, reason=None)
        return await self.sync_snapshot(user_id)

    async def review(self, user_id: int, *, approve: bool, reason: str | None, admin_platform: str,
                     admin_id: int | str, admin_name: str | None) -> User:
        user = await self.get(user_id)
        if user.status != UserStatus.PENDING:
            raise ProfileError(f"Already handled (status: {user.status}).")
        new_status = UserStatus.ACTIVE if approve else UserStatus.REJECTED
        await self._set_status(user_id, new_status, reason=None if approve else reason)
        await self.log_admin_action(admin_platform, admin_id, admin_name,
                                    "approve" if approve else "reject", user_id, {"reason": reason})
        return await self.sync_snapshot(user_id)

    async def set_paused(self, user_id: int, paused: bool) -> User:
        user = await self.get(user_id)
        if paused and user.status == UserStatus.ACTIVE:
            await self._set_status(user_id, UserStatus.PAUSED)
        elif not paused and user.status == UserStatus.PAUSED:
            await self._set_status(user_id, UserStatus.ACTIVE)
        return await self.sync_snapshot(user_id)

    async def _set_status(self, user_id: int, status: UserStatus, reason: str | None = None) -> None:
        async with self.sessions() as session, session.begin():
            user = await session.get(User, user_id)
            user.status = status
            user.rejection_reason = reason

    async def pending_users(self, after_id: int = 0, limit: int = 1) -> list[User]:
        async with self.sessions() as session:
            return list(await session.scalars(
                select(User).where(User.status == UserStatus.PENDING, User.id > after_id).order_by(User.id).limit(limit)
            ))

    async def count_by_status(self) -> dict[str, int]:
        async with self.sessions() as session:
            rows = await session.execute(select(User.status, func.count()).group_by(User.status))
            return {status: count for status, count in rows}

    async def count_by_platform(self) -> dict[str, int]:
        async with self.sessions() as session:
            rows = await session.execute(select(PlatformAccount.platform, func.count()).group_by(PlatformAccount.platform))
            return {platform: count for platform, count in rows}

    async def log_admin_action(self, platform: str, admin_id: int | str, admin_name: str | None, action: str,
                               target_user_id: int | None, details: dict | None = None) -> None:
        async with self.sessions() as session, session.begin():
            session.add(AdminAction(admin_platform=platform, admin_platform_id=str(admin_id), admin_name=admin_name,
                                    action=action, target_user_id=target_user_id, details=details or {}))

    # ------------------------------------------------------------------ storage sync + deletion
    def snapshot(self, user: User) -> dict:
        return {
            "schema": 1,
            "user_id": user.id,
            "status": user.status,
            "created_at": user.created_at,
            "accounts": [{"platform": a.platform, "id": a.platform_user_id, "username": a.username}
                         for a in user.accounts],
            "profile": {
                "display_name": user.display_name, "dob": user.dob, "gender": user.gender,
                "show_me": user.show_me, "looking_for": user.looking_for, "bio": user.bio,
                "city": user.city, "lat": user.lat, "lon": user.lon, "interests": user.interests,
                "lang": user.lang, "is_verified": user.is_verified,
            },
            "photos": [{"position": p.position, "tg_file_id": p.tg_file_id, "vault_msg_id": p.vault_msg_id,
                        "phash": p.phash, "face_score": round(p.face_score, 3)} for p in user.photos],
        }

    async def sync_snapshot(self, user_id: int) -> User:
        """Mirror the profile to the vault. Best-effort: a vault outage must never block the user."""
        user = await self.get(user_id)
        try:
            msg_id = await self.vault.store_snapshot(user_id, self.snapshot(user), user.vault_snapshot_msg_id)
        except Exception:
            log.exception("vault snapshot failed for user %s", user_id)
            return user
        if msg_id != user.vault_snapshot_msg_id:
            async with self.sessions() as session, session.begin():
                (await session.get(User, user_id)).vault_snapshot_msg_id = msg_id
            user = await self.get(user_id)
        return user

    async def delete_account(self, user_id: int) -> None:
        """Right to be forgotten: removes the profile from the DB and the vault.

        Banned/underage accounts keep their (now empty) row so the block still applies.
        """
        user = await self.reset_profile(user_id)
        try:
            await self.vault.delete_snapshot(user_id, user.vault_snapshot_msg_id)
        except Exception:
            log.exception("vault snapshot delete failed for user %s", user_id)
        async with self.sessions() as session, session.begin():
            db_user = await session.get(User, user_id)
            if db_user.status in (UserStatus.BANNED, UserStatus.UNDERAGE):
                db_user.vault_snapshot_msg_id = None
                db_user.bio = db_user.display_name = None
            else:
                await session.delete(db_user)
        self._locks.pop(user_id, None)
