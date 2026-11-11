"""Photo checks: every profile photo must show a real, clear face.

Models (OpenCV Zoo, Apache-2.0/MIT, OK for commercial use):
  * YuNet  - face detection + 5 landmarks
  * SFace  - 128-d face embedding, used to check that extra photos show the same person as the main one

The engine is synchronous and CPU-bound; callers run it via asyncio.to_thread. OpenCV releases the GIL
during inference, and each thread gets its own model instances (the OpenCV objects are not thread-safe).
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable

import cv2
import imagehash
import numpy as np
from PIL import Image, ImageOps

from amora.config import Settings

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"

Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs early
_MAX_STORED_SIDE = 1600   # stored JPEG size
_MAX_DETECT_SIDE = 1024   # face analysis size


class Reject(StrEnum):
    UNREADABLE = "unreadable"
    TOO_SMALL = "too_small"
    NO_FACE = "no_face"
    MULTIPLE_FACES = "multiple_faces"
    FACE_TOO_SMALL = "face_too_small"
    NOT_FRONTAL = "not_frontal"
    BLURRY = "blurry"
    NOT_SAME_PERSON = "not_same_person"
    DUPLICATE = "duplicate"


REJECT_MESSAGES: dict[Reject, str] = {
    Reject.UNREADABLE: "I couldn't open that file. Please send a normal JPG or PNG photo.",
    Reject.TOO_SMALL: "That image is too small. Please send a higher-quality photo.",
    Reject.NO_FACE: "I couldn't find a face. Please upload a clear photo of <b>you</b>, where your face is visible.",
    Reject.MULTIPLE_FACES: "Your main photo must show only you. Group photos are fine as extra photos.",
    Reject.FACE_TOO_SMALL: "Your face is too small in this photo. Try a closer photo (head and shoulders).",
    Reject.NOT_FRONTAL: "Please use a photo where you're facing the camera.",
    Reject.BLURRY: "This photo is too blurry. Please try a sharper one.",
    Reject.NOT_SAME_PERSON: "This photo doesn't seem to show the same person as your main photo. "
                            "Every photo must include <b>you</b>.",
    Reject.DUPLICATE: "This photo is already used on another profile, so it can't be used here.",
}


class ModelsMissingError(RuntimeError):
    pass


@dataclass
class PhotoCheck:
    ok: bool
    reject: Reject | None = None
    jpeg: bytes | None = None
    width: int = 0
    height: int = 0
    phash: str | None = None
    embedding: np.ndarray | None = None  # float32 (1, 128)
    face_score: float = 0.0
    match_score: float | None = None
    face_count: int = 0

    @property
    def message(self) -> str:
        return REJECT_MESSAGES[self.reject] if self.reject else "Looks great!"


def phash_distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


class FaceEngine:
    def __init__(self, settings: Settings):
        self.s = settings
        self.yunet_path = Path(settings.models_dir) / YUNET_FILE
        self.sface_path = Path(settings.models_dir) / SFACE_FILE
        missing = [p.name for p in (self.yunet_path, self.sface_path) if not p.exists()]
        if missing:
            raise ModelsMissingError(
                f"Face models missing in {settings.models_dir}: {', '.join(missing)}. "
                "Run: python scripts/download_models.py"
            )
        self._local = threading.local()
        self._models()  # fail fast if the model files are corrupt

    # ---- model handles (one set per thread) ----
    def _models(self) -> tuple[cv2.FaceDetectorYN, cv2.FaceRecognizerSF]:
        if not hasattr(self._local, "detector"):
            self._local.detector = cv2.FaceDetectorYN.create(
                str(self.yunet_path), "", (320, 320), self.s.face_min_score, 0.3, 5000
            )
            self._local.recognizer = cv2.FaceRecognizerSF.create(str(self.sface_path), "")
        return self._local.detector, self._local.recognizer

    # ---- public API ----
    def check(
        self,
        raw: bytes,
        *,
        is_main: bool,
        main_embedding: np.ndarray | None = None,
        known_hashes: Iterable[str] = (),
    ) -> PhotoCheck:
        try:
            pil = self._normalize(raw)
        except Exception:
            return PhotoCheck(ok=False, reject=Reject.UNREADABLE)
        if min(pil.size) < self.s.min_image_side:
            return PhotoCheck(ok=False, reject=Reject.TOO_SMALL)

        pil.thumbnail((_MAX_STORED_SIDE, _MAX_STORED_SIDE), Image.Resampling.LANCZOS)
        result = self._analyze(pil, is_main=is_main, main_embedding=main_embedding)
        if not result.ok:
            return result

        result.phash = str(imagehash.phash(pil))
        if any(phash_distance(result.phash, h) <= self.s.phash_max_distance for h in known_hashes):
            return PhotoCheck(ok=False, reject=Reject.DUPLICATE, phash=result.phash)

        out = io.BytesIO()
        pil.save(out, format="JPEG", quality=88, optimize=True)  # re-encode: drops EXIF/GPS metadata
        result.jpeg = out.getvalue()
        result.width, result.height = pil.size
        return result

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        _, recognizer = self._models()
        return float(recognizer.match(a, b, cv2.FaceRecognizerSF_FR_COSINE))

    # ---- internals ----
    @staticmethod
    def _normalize(raw: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = ImageOps.exif_transpose(img)  # apply phone rotation before throwing EXIF away
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            return background
        return img.convert("RGB")

    def _analyze(self, pil: Image.Image, *, is_main: bool, main_embedding: np.ndarray | None) -> PhotoCheck:
        detector, recognizer = self._models()
        bgr = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
        scale = _MAX_DETECT_SIDE / max(bgr.shape[:2])
        if scale < 1:
            bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        h, w = bgr.shape[:2]
        image_area = float(h * w)

        detector.setInputSize((w, h))
        _, faces = detector.detect(bgr)
        if faces is None or len(faces) == 0:
            return PhotoCheck(ok=False, reject=Reject.NO_FACE)
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        if is_main:
            if len(faces) > 1 and faces[0][2] * faces[0][3] < self.s.face_dominance_ratio * faces[1][2] * faces[1][3]:
                return PhotoCheck(ok=False, reject=Reject.MULTIPLE_FACES, face_count=len(faces))
            face = faces[0]
            if face[2] * face[3] / image_area < self.s.face_min_area_main:
                return PhotoCheck(ok=False, reject=Reject.FACE_TOO_SMALL, face_count=len(faces))
            if not _is_frontal(face):
                return PhotoCheck(ok=False, reject=Reject.NOT_FRONTAL, face_count=len(faces))
            if _sharpness(gray, face) < self.s.face_min_sharpness:
                return PhotoCheck(ok=False, reject=Reject.BLURRY, face_count=len(faces))
            embedding = recognizer.feature(recognizer.alignCrop(bgr, face)).copy()
            return PhotoCheck(ok=True, embedding=embedding, face_score=float(face[-1]), face_count=len(faces))

        # Extra photo: at least one reasonably sized face must be the same person as the main photo.
        if main_embedding is None:
            raise ValueError("main_embedding is required for extra photos")
        candidates = [f for f in faces if f[2] * f[3] / image_area >= self.s.face_min_area_extra]
        if not candidates:
            return PhotoCheck(ok=False, reject=Reject.FACE_TOO_SMALL, face_count=len(faces))
        best: tuple[float, np.ndarray, np.ndarray] | None = None
        for face in candidates:
            emb = recognizer.feature(recognizer.alignCrop(bgr, face)).copy()
            score = float(recognizer.match(main_embedding, emb, cv2.FaceRecognizerSF_FR_COSINE))
            if best is None or score > best[0]:
                best = (score, emb, face)
        score, emb, face = best
        if score < self.s.face_match_threshold:
            return PhotoCheck(ok=False, reject=Reject.NOT_SAME_PERSON, match_score=score, face_count=len(faces))
        if _sharpness(gray, face) < self.s.face_min_sharpness:
            return PhotoCheck(ok=False, reject=Reject.BLURRY, match_score=score, face_count=len(faces))
        return PhotoCheck(ok=True, embedding=emb, face_score=float(face[-1]), match_score=score,
                          face_count=len(faces))


def _is_frontal(face: np.ndarray) -> bool:
    """Nose should sit between the eyes horizontally; rejects strong profile (side-on) shots."""
    x, y, w, h = face[:4]
    points = face[4:14].reshape(5, 2)
    pad_w, pad_h = w * 0.1, h * 0.1
    inside = ((points[:, 0] >= x - pad_w) & (points[:, 0] <= x + w + pad_w)
              & (points[:, 1] >= y - pad_h) & (points[:, 1] <= y + h + pad_h))
    if not inside.all():
        return False
    eye_a, eye_b, nose = points[0][0], points[1][0], points[2][0]
    left, right = min(eye_a, eye_b), max(eye_a, eye_b)
    if right - left < 2:
        return False
    ratio = (nose - left) / (right - left)
    return 0.15 <= ratio <= 0.85


def _sharpness(gray: np.ndarray, face: np.ndarray) -> float:
    x, y, w, h = (int(round(v)) for v in face[:4])
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, gray.shape[1]), min(y + h, gray.shape[0])
    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0.0
    crop = cv2.resize(gray[y0:y1, x0:x1], (128, 128), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(crop, cv2.CV_64F).var())
