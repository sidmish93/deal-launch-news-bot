"""Turn a downloaded filing into the files a phone can open."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

# Telegram bots can attach up to 50 MB. Stay under that, per file and per zip.
MAX_BYTES = 48 * 1024 * 1024
MAX_FILES = 8

_UNSAFE = re.compile(r'[\x00-\x1f<>:"|?*\\]')


@dataclass(frozen=True)
class Unzipped:
    files: list[tuple[str, bytes]]
    skipped: int


def is_zip_url(url: str) -> bool:
    path = (url or "").split("?", 1)[0].split("#", 1)[0].lower()
    return path.endswith(".zip")


def unzip(blob: bytes) -> Unzipped:
    """Return the documents inside a zip. Raises if the bytes are not a zip."""
    if not blob.startswith(b"PK"):
        raise ValueError("not a zip")
    files: list[tuple[str, bytes]] = []
    skipped = 0
    used: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        chosen = []
        for info in archive.infolist():
            name = _member_name(info.filename)
            if name is None:
                continue
            if info.file_size <= 0 or info.file_size > MAX_BYTES:
                skipped += 1
                continue
            chosen.append((name, info))
        if len(chosen) > MAX_FILES:
            skipped += len(chosen) - MAX_FILES
            chosen = chosen[:MAX_FILES]
        for name, info in chosen:
            data = archive.read(info)
            if len(data) > MAX_BYTES:
                skipped += 1
                continue
            files.append((_unique(name, used), data))
    return Unzipped(files, skipped)


def _member_name(filename: str) -> str | None:
    name = (filename or "").replace("\\", "/").strip()
    if not name or name.endswith("/"):
        return None
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    if any(part == "__MACOSX" or part.startswith(".") for part in parts):
        return None
    base = _UNSAFE.sub(" ", parts[-1]).strip()
    base = re.sub(r"\s+", " ", base)
    if not base or "." not in base:
        return None
    return base[:120]


def _unique(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    stem, dot, ext = name.rpartition(".")
    stem = stem or name
    ext = f".{ext}" if dot else ""
    number = 2
    while True:
        candidate = f"{stem} {number}{ext}"[:120]
        if candidate not in used:
            used.add(candidate)
            return candidate
        number += 1
