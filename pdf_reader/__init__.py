"""Reads values from device report PDFs without AI, checks them against each other, and says plainly when it cannot.

    from pdf_reader import read_pdf
    result = read_pdf(pdf_bytes)
    result.status     # ok | check | unknown_device | no_text | error
    result.values     # {"Weight (kg)": Value(text="75.8 kg", number=75.8, unit="kg", source="text"), ...}
    result.checks     # the automatic checks, each pass or fail

Each device has its own reader module. A text reader has matches() and read(); a picture reader has matches_banner() and
read_image(). Add new ones to TEXT_READERS or IMAGE_READERS.
"""
from __future__ import annotations

from . import age_scanner, kardia_ecg, ocr, tanita_mc780, vihealth_oxygen
from .base import MAX_PDF_BYTES, Check, ReadResult, Value, line_text, load_pages

TEXT_READERS = [tanita_mc780, kardia_ecg, age_scanner]
IMAGE_READERS = [vihealth_oxygen]
ALL_READERS = TEXT_READERS + IMAGE_READERS
__all__ = ["read_pdf", "ReadResult", "Value", "Check", "ALL_READERS", "reader_for"]


def reader_for(device: str):
    return next((r for r in ALL_READERS if r.DEVICE == device), None)


def read_pdf(data: bytes, include_text: bool = False) -> ReadResult:
    """Read a PDF. Never raises: problems come back in the result's status and notes."""
    try:
        pages = load_pages(data)
    except ValueError as e:
        return ReadResult(status="error", notes=[str(e)])
    all_words = [w for page in pages for w in page]
    if not all_words:
        return _read_picture(data)
    compact = "".join(w["text"] for w in all_words)
    for reader in TEXT_READERS:
        if reader.matches(compact):
            try:
                return reader.read(pages, data)
            except Exception:  # a layout the reader did not expect: say so, do not guess
                return ReadResult(device=reader.DEVICE, device_label=reader.LABEL, status="check", has_text_layer=True,
                                  notes=["Could not read: the report looked like this device but its layout was not as expected, so nothing was read."])
    result = ReadResult(status="unknown_device", has_text_layer=True, notes=["The device is not recognised, so the values were not read automatically."])
    if include_text:
        result.text_lines = [line for page in pages for line in line_text(page)]
    return result


def _read_picture(data: bytes) -> ReadResult:
    """A PDF with no text: find out which device made it from the banner at the top, then read it with OCR."""
    if not ocr.available():
        return ReadResult(status="no_text", notes=["The PDF has no text layer (a picture or scan) and text recognition is not installed, so it needs the AI or a person."])
    try:
        banner = ocr.banner_text(data)
        for reader in IMAGE_READERS:
            if reader.matches_banner(banner):
                return reader.read_image(data)
    except Exception:
        return ReadResult(status="error", notes=["The picture could not be read."])
    return ReadResult(status="no_text", notes=["The PDF is a picture and the device is not recognised, so it needs the AI or a person."])
