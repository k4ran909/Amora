from datetime import date, datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from spark.core.admin import AdminService
from spark.core.profiles import ProfileError, ProfileService
from spark.db.base import init_db, make_engine, make_sessionmaker
from spark.db.models import Platform, Role, UserStatus


@pytest.fixture
async def profiles(settings, face_engine):
    engine = make_engine(settings.database_url)
    await init_db(engine)
    yield ProfileService(make_sessionmaker(engine), settings, face_engine)
    await engine.dispose()


async def _complete_profile(profiles: ProfileService, face_a: bytes, tg_id: int = 1):
    user = await profiles.get_or_create(Platform.TELEGRAM, tg_id, "tester")
    now = datetime.now(timezone.utc)
    user = await profiles.update(
        user.id, terms_accepted_at=now, biometric_consent_at=now, dob=date(2000, 1, 1), gender="woman",
        show_me=["man"], looking_for="relationship", display_name="Priya", city="Mumbai",
        bio="I love hiking and coffee.", interests=["hiking", "coffee", "books"],
    )
    check, user = await profiles.add_photo(user.id, face_a)
    assert check.ok, check.reject
    return user


async def test_get_or_create_is_idempotent(profiles):
    a = await profiles.get_or_create(Platform.TELEGRAM, 42, "bob")
    b = await profiles.get_or_create(Platform.TELEGRAM, 42, "bob2")
    assert a.id == b.id
    assert b.account(Platform.TELEGRAM).username == "bob2"


async def test_missing_steps_in_order(profiles):
    user = await profiles.get_or_create(Platform.TELEGRAM, 7, None)
    assert profiles.missing_steps(user)[:3] == ["terms", "dob", "gender"]


async def test_full_flow_submit_and_approve(profiles, face_a, settings):
    user = await _complete_profile(profiles, face_a)
    assert profiles.missing_steps(user) == []

    flipped = cv2.imencode(".jpg", cv2.flip(cv2.imdecode(np.frombuffer(face_a, np.uint8), 1), 1))[1].tobytes()
    check, user = await profiles.add_photo(user.id, flipped)
    assert check.ok and len(user.photos) == 2 and user.photos[1].position == 1

    user = await profiles.submit(user.id)
    assert user.status == UserStatus.PENDING
    snapshot = Path(settings.data_dir) / "vault" / f"u{user.id}" / "profile.json"
    assert snapshot.exists() and '"status": "pending"' in snapshot.read_text(encoding="utf-8")

    pending = await profiles.pending_users()
    assert [u.id for u in pending] == [user.id]

    user = await profiles.review(user.id, approve=True, reason=None, admin_platform=Platform.TELEGRAM,
                                 admin_id=111, admin_name="owner")
    assert user.status == UserStatus.ACTIVE
    with pytest.raises(ProfileError):
        await profiles.review(user.id, approve=True, reason=None, admin_platform=Platform.TELEGRAM,
                              admin_id=111, admin_name="owner")


async def test_submit_incomplete_fails(profiles):
    user = await profiles.get_or_create(Platform.TELEGRAM, 9, None)
    with pytest.raises(ProfileError):
        await profiles.submit(user.id)


async def test_same_photo_cannot_be_reused_by_another_user(profiles, face_a):
    await _complete_profile(profiles, face_a, tg_id=1)
    other = await profiles.get_or_create(Platform.TELEGRAM, 2, None)
    check, _ = await profiles.add_photo(other.id, face_a)
    assert not check.ok and check.reject == "duplicate"


async def test_embeddings_are_encrypted(profiles, face_a):
    user = await _complete_profile(profiles, face_a)
    blob = user.photos[0].face_embedding
    assert len(blob) > 512  # Fernet token, not raw 512-byte float32[128]
    assert profiles._decrypt(blob).shape == (1, 128)


async def test_reset_keeps_dob_and_removes_photos(profiles, face_a, settings):
    user = await _complete_profile(profiles, face_a)
    photo_path = Path(user.photos[0].local_path)
    assert photo_path.exists()
    user = await profiles.reset_profile(user.id)
    assert user.photos == [] and user.bio is None
    assert user.dob == date(2000, 1, 1)
    assert not photo_path.exists()


async def test_underage_block_is_sticky(profiles, face_a):
    user = await _complete_profile(profiles, face_a)
    await profiles.mark_underage(user.id)
    await profiles.delete_account(user.id)  # deleting must not lift the block
    again = await profiles.get_or_create(Platform.TELEGRAM, 1, "tester")
    assert again.id == user.id and again.status == UserStatus.UNDERAGE


async def test_delete_account_removes_everything(profiles, face_a):
    user = await _complete_profile(profiles, face_a)
    await profiles.delete_account(user.id)
    fresh = await profiles.get_or_create(Platform.TELEGRAM, 1, "tester")
    assert fresh.id != user.id and fresh.photos == []


async def test_owner_role_from_env(profiles, settings):
    admin = AdminService(settings, profiles)
    assert await admin.role_of(Platform.TELEGRAM, 111) == Role.OWNER
    assert await admin.role_of(Platform.TELEGRAM, 999) == Role.USER
    assert await admin.has_role(Platform.TELEGRAM, 222, Role.ADMIN)
    assert not await admin.has_role(Platform.DISCORD, 111, Role.MOD)
