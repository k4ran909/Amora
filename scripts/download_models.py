"""Download the OpenCV Zoo face models into ./models (or $MODELS_DIR). Safe to re-run."""

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    target = Path(os.environ.get("MODELS_DIR", Path(__file__).resolve().parent.parent / "models"))
    target.mkdir(parents=True, exist_ok=True)
    failed = False
    for name, (url, expected) in MODELS.items():
        path = target / name
        if path.exists() and sha256(path) == expected:
            print(f"ok       {name}")
            continue
        print(f"download {name}")
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        actual = sha256(tmp)
        if actual != expected:
            tmp.unlink()
            print(f"CHECKSUM MISMATCH for {name}: got {actual}", file=sys.stderr)
            failed = True
            continue
        tmp.replace(path)
        print(f"ok       {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
