"""ffmpeg / ffprobe için ince sarmalayıcı."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class MedyaHatasi(Exception):
    pass


def ffmpeg(args: list, cwd: Path | None = None) -> None:
    komut = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    r = subprocess.run(komut, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise MedyaHatasi(f"ffmpeg hata kodu {r.returncode}: {r.stderr[-1500:]}")


def sure(yol) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(yol)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise MedyaHatasi(f"süre okunamadı: {yol}: {r.stderr[-500:]}") from None


def araclar_var_mi() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
