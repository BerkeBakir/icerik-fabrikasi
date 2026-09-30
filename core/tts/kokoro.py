"""Kokoro-82M ile lokal, ücretsiz seslendirme (24 kHz WAV)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import soundfile as sf

from core.tts import SesSonucu, TTSHatasi

ORNEKLEME = 24000


class KokoroTTS:
    def __init__(self, ses: str = "af_heart", hiz: float = 0.85, paragraf_arasi: float = 1.2,
                 dil: str = "a", pipeline=None):
        self.ses, self.hiz = ses, hiz
        self.paragraf_arasi = paragraf_arasi
        self.dil = dil
        self._pipeline = pipeline

    def _pl(self):
        if self._pipeline is None:
            from kokoro import KPipeline

            self._pipeline = KPipeline(lang_code=self.dil, repo_id="hexgrad/Kokoro-82M")
        return self._pipeline

    def seslendir(self, metin: str, cikti: Path) -> SesSonucu:
        paragraflar = [p.strip() for p in re.split(r"\n\s*\n", metin) if p.strip()]
        sessizlik = np.zeros(int(ORNEKLEME * self.paragraf_arasi), dtype=np.float32)
        parcalar, ses_var = [], False
        for p in paragraflar:
            for _, _, ses in self._pl()(p, voice=self.ses, speed=self.hiz):
                if ses is None:
                    continue
                dizi = ses.numpy() if hasattr(ses, "numpy") else np.asarray(ses)
                parcalar.append(dizi.astype(np.float32))
                ses_var = ses_var or len(dizi) > 0
            parcalar.append(sessizlik)
        if not ses_var:
            raise TTSHatasi("Kokoro ses üretmedi")
        tum = np.concatenate(parcalar)
        wav = Path(cikti).with_suffix(".wav")
        wav.parent.mkdir(parents=True, exist_ok=True)
        sf.write(wav, tum, ORNEKLEME)
        return SesSonucu(wav, len(tum) / ORNEKLEME, [])
