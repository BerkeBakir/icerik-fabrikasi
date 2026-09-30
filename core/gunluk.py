from __future__ import annotations

import logging
import sys
from pathlib import Path

from core.ayar import KOK


def kur(kanal: str, kok: Path = KOK) -> logging.Logger:
    log = logging.getLogger(f"fabrika.{kanal}")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    bicim = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    klasor = kok / "veri" / "log"
    klasor.mkdir(parents=True, exist_ok=True)
    dosya = logging.FileHandler(klasor / f"{kanal}.log", encoding="utf-8")
    dosya.setFormatter(bicim)
    konsol = logging.StreamHandler(sys.stdout)
    konsol.setFormatter(bicim)
    log.addHandler(dosya)
    log.addHandler(konsol)
    return log
