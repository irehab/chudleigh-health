"""Text recognition (OCR) for report PDFs that are pictures. Runs on this server only; nothing is sent anywhere.

Needs the Tesseract program and the pytesseract package. If either is missing, available() is False and the readers say so
instead of guessing.
"""
from __future__ import annotations

import io


def available() -> bool:
    try:
        import pytesseract
        import pdfplumber  # noqa: F401  (also draws the page)
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def render(data: bytes, scale: float = 2.0, page: int = 0):
    """The page as a grey picture. scale 2.0 is about 144 dots per inch."""
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return pdf.pages[page].to_image(resolution=int(72 * scale)).original.convert("L")


def crop(img, box):
    """box is (left, top, right, bottom) as fractions of the page, so it works at any scale."""
    w, h = img.size
    return img.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))


def read_text(img, psm: int = 6, upscale: int = 2, whitelist: str = "") -> str:
    import pytesseract
    from PIL import Image, ImageOps
    img = ImageOps.autocontrast(img)
    img = img.resize((img.width * upscale, img.height * upscale), Image.LANCZOS)
    config = f"--psm {psm}" + (f" -c tessedit_char_whitelist={whitelist}" if whitelist else "")
    return pytesseract.image_to_string(img, config=config, timeout=30).strip()


def banner_text(data: bytes) -> str:
    """The top of the first page as capital letters, used to recognise which device made a picture-only report."""
    return read_text(crop(render(data, 2.0), (0.0, 0.0, 1.0, 0.075)), psm=6).upper()
