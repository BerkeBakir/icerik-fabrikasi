from __future__ import annotations

import asyncio
import time
from pathlib import Path

import edge_tts

from core import medya
from core.tekrar import tekrar_dene
from core.tts import Kelime, SesSonucu, TTSHatasi


class EdgeTTS:
    def __init__(self, ses: str, hiz: str = "+0%", iletisim=edge_tts.Communicate,
                 sure_fn=medya.sure, uyku=time.sleep):
        self.ses, self.hiz = ses, hiz
        self.iletisim = iletisim
        self.sure_fn = sure_fn
        self.uyku = uyku

    async def _uret(self, metin: str, cikti: Path) -> SesSonucu:
        c = self.iletisim(metin, self.ses, rate=self.hiz, boundary="WordBoundary")
        kelimeler: list[Kelime] = []
        with open(cikti, "wb") as f:
            async for parca in c.stream():
                if parca["type"] == "audio":
                    f.write(parca["data"])
                elif parca["type"] == "WordBoundary":
                    bas = parca["offset"] / 1e7
                    kelimeler.append(Kelime(parca["text"], round(bas, 3), round(bas + parca["duration"] / 1e7, 3)))
        if not kelimeler or Path(cikti).stat().st_size == 0:
            raise TTSHatasi("Edge-TTS boş ses döndürdü")
        return SesSonucu(Path(cikti), self.sure_fn(cikti), kelimeler)

    def seslendir(self, metin: str, cikti: Path) -> SesSonucu:
        Path(cikti).parent.mkdir(parents=True, exist_ok=True)
        return tekrar_dene(lambda: asyncio.run(self._uret(metin, Path(cikti))),
                           deneme=3, bekleme=5, uyku=self.uyku)
