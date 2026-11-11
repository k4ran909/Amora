import urllib.request
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from amora.config import Settings

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / ".cache"
SAMPLES = {  # OpenCV's own sample images (single clear face in each)
    "face_a.jpg": "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg",
    "face_b.jpg": "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/messi5.jpg",
}


def _sample(name: str) -> bytes:
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        try:
            urllib.request.urlretrieve(SAMPLES[name], path)
        except Exception as exc:  # offline
            pytest.skip(f"sample image unavailable: {exc}")
    return path.read_bytes()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        fernet_key=Fernet.generate_key().decode(),
        models_dir=ROOT / "models",
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        owner_tg_ids="111,222",
    )


@pytest.fixture
def face_engine(settings):
    from amora.core.photos import FaceEngine, ModelsMissingError

    try:
        return FaceEngine(settings)
    except ModelsMissingError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def face_a() -> bytes:
    return _sample("face_a.jpg")


@pytest.fixture
def face_b() -> bytes:
    return _sample("face_b.jpg")
