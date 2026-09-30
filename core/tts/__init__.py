"""Ortak TTS arayüzü: seslendir(metin, cikti) -> SesSonucu."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path


class TTSHatasi(Exception):
    pass


@dataclass
class Kelime:
    metin: str
    baslangic: float
    bitis: float


@dataclass
class SesSonucu:
    yol: Path
    sure: float
    kelimeler: list[Kelime] = field(default_factory=list)

    def sozluk(self) -> dict:
        return {"yol": str(self.yol), "sure": self.sure, "kelimeler": [asdict(k) for k in self.kelimeler]}

    @classmethod
    def sozlukten(cls, d: dict) -> "SesSonucu":
        return cls(Path(d["yol"]), float(d["sure"]), [Kelime(**k) for k in d.get("kelimeler", [])])


class YedekliTTS:
    def __init__(self, ana, yedek, log: logging.Logger | None = None):
        self.ana, self.yedek = ana, yedek
        self.log = log or logging.getLogger(__name__)

    def seslendir(self, metin: str, cikti: Path) -> SesSonucu:
        try:
            return self.ana.seslendir(metin, cikti)
        except Exception as e:
            self.log.warning("Ana TTS başarısız (%s), yedek motora geçiliyor", e)
            return self.yedek.seslendir(metin, cikti)


def motor_olustur(ses, log: logging.Logger | None = None):
    from core.tts.edge import EdgeTTS

    if ses.motor == "edge":
        return EdgeTTS(ses.ses, str(ses.hiz))
    from core.tts.kokoro import KokoroTTS

    return YedekliTTS(KokoroTTS(ses.ses, float(ses.hiz)),
                      EdgeTTS("en-US-AndrewMultilingualNeural", "-15%"), log)
