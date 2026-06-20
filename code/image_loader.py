import io
import os
from dataclasses import dataclass
from pathlib import Path
from PIL import Image
import pillow_avif  # noqa: F401

from config import DATASET

MAX_EDGE = int(os.getenv("IMAGE_MAX_EDGE", "768"))
JPEG_QUALITY = int(os.getenv("IMAGE_JPEG_QUALITY", "75"))

@dataclass
class ImageResult:
    image_id: str
    path: Path
    valid: bool
    reason: str
    bytes_jpeg: bytes | None

def image_id_from_path(p: str) -> str:
    return Path(p).stem

def load_images(paths_str: str) -> list[ImageResult]:
    results = []
    for rel in [p.strip() for p in paths_str.split(";") if p.strip()]:
        full = DATASET / rel
        img_id = image_id_from_path(rel)
        if not full.exists():
            results.append(ImageResult(img_id, full, False, "file_missing", None))
            continue
        try:
            raw = full.read_bytes()
            img = Image.open(io.BytesIO(raw))
            img.load()
            img = img.convert("RGB")
            w, h = img.size
            if w < 2 or h < 2:
                raise ValueError("degenerate_dimensions")
            scale = min(1.0, MAX_EDGE / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY)
            results.append(ImageResult(img_id, full, True, "ok", buf.getvalue()))
        except Exception as e:
            results.append(ImageResult(img_id, full, False, str(e), None))
    return results
