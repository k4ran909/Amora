import io

import cv2
import numpy as np
from PIL import Image

from spark.core.photos import Reject, phash_distance


def _encode(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _decode(raw: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def test_main_photo_with_face_accepted(face_engine, face_a):
    result = face_engine.check(face_a, is_main=True)
    assert result.ok, result.reject
    assert result.embedding.shape == (1, 128)
    assert result.face_score >= 0.8
    assert result.jpeg and len(result.phash) == 16


def test_no_face_rejected(face_engine):
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (600, 600, 3), dtype=np.uint8)
    assert face_engine.check(_encode(noise), is_main=True).reject == Reject.NO_FACE


def test_plain_scenery_rejected(face_engine):
    gradient = np.tile(np.linspace(0, 255, 800, dtype=np.uint8), (600, 1))
    img = cv2.merge([gradient, np.full_like(gradient, 120), 255 - gradient])
    assert face_engine.check(_encode(img), is_main=True).reject == Reject.NO_FACE


def test_too_small_rejected(face_engine, face_a):
    small = cv2.resize(_decode(face_a), (200, 200))
    assert face_engine.check(_encode(small), is_main=True).reject == Reject.TOO_SMALL


def test_unreadable_rejected(face_engine):
    assert face_engine.check(b"not an image", is_main=True).reject == Reject.UNREADABLE


def test_group_photo_rejected_as_main(face_engine, face_a):
    img = _decode(face_a)
    assert face_engine.check(_encode(np.hstack([img, img])), is_main=True).reject == Reject.MULTIPLE_FACES


def test_blurry_rejected(face_engine, face_a):
    blurred = cv2.GaussianBlur(_decode(face_a), (0, 0), 6)
    assert face_engine.check(_encode(blurred), is_main=True).reject in (Reject.BLURRY, Reject.NO_FACE)


def test_extra_photo_same_person_accepted(face_engine, face_a):
    main = face_engine.check(face_a, is_main=True)
    flipped = cv2.flip(_decode(face_a), 1)
    extra = face_engine.check(_encode(flipped), is_main=False, main_embedding=main.embedding)
    assert extra.ok, extra.reject
    assert extra.match_score >= 0.363


def test_extra_photo_group_with_same_person_accepted(face_engine, face_a):
    main = face_engine.check(face_a, is_main=True)
    img = _decode(face_a)
    extra = face_engine.check(_encode(np.hstack([img, img])), is_main=False, main_embedding=main.embedding)
    assert extra.ok, extra.reject


def _crop_to_face(engine, raw: bytes) -> bytes:
    """Crop generously around the largest face so it passes the size rules."""
    img = _decode(raw)
    detector, _ = engine._models()
    detector.setInputSize((img.shape[1], img.shape[0]))
    _, faces = detector.detect(img)
    x, y, w, h = (int(v) for v in max(faces, key=lambda f: f[2] * f[3])[:4])
    pad = int(max(w, h) * 1.2)
    crop = img[max(y - pad, 0): y + h + pad, max(x - pad, 0): x + w + pad]
    return _encode(cv2.resize(crop, (640, 640), interpolation=cv2.INTER_CUBIC))


def test_extra_photo_different_person_rejected(face_engine, face_a, face_b):
    main = face_engine.check(face_a, is_main=True)
    other = face_engine.check(_crop_to_face(face_engine, face_b), is_main=False, main_embedding=main.embedding)
    assert other.reject == Reject.NOT_SAME_PERSON


def test_duplicate_photo_rejected(face_engine, face_a):
    first = face_engine.check(face_a, is_main=True)
    again = face_engine.check(face_a, is_main=True, known_hashes=[first.phash])
    assert again.reject == Reject.DUPLICATE


def test_exif_stripped(face_engine, face_a):
    img = Image.open(io.BytesIO(face_a))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    result = face_engine.check(buf.getvalue(), is_main=True)
    assert result.ok
    assert not Image.open(io.BytesIO(result.jpeg)).getexif()


def test_phash_distance():
    assert phash_distance("ffffffffffffffff", "ffffffffffffffff") == 0
    assert phash_distance("0000000000000000", "000000000000000f") == 4
