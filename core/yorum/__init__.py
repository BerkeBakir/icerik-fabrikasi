"""TikTok yorum yöneticisi: ortak türler."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HamYorum:
    """Studio yorum sayfasından okunan tek yorum."""
    kullanici: str
    metin: str
    video: str


class YorumIslemHatasi(Exception):
    """Tarayıcı eylemi başarısız. yetki=True: oturum kapalı ('--giris' gerekli)."""

    def __init__(self, mesaj: str, ekran: Path | None = None, yetki: bool = False):
        super().__init__(mesaj)
        self.ekran = ekran
        self.yetki = yetki
