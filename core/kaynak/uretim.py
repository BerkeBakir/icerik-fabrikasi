from __future__ import annotations

import logging
from pathlib import Path

from core.modeller import Hikaye
from core.senaryo import serbest_hikaye


class UretimKaynak:
    def __init__(self, llm, prompt_yolu: Path, db, log: logging.Logger | None = None):
        self.llm = llm
        self.prompt_yolu = Path(prompt_yolu)
        self.db = db
        self.log = log or logging.getLogger(__name__)

    def sec(self) -> Hikaye | None:
        prompt = self.prompt_yolu.read_text(encoding="utf-8")
        for _ in range(2):
            h = serbest_hikaye(self.llm, prompt)
            if not self.db.hikaye_kullanildi_mi(h.kimlik):
                return h
            self.log.warning("Üretilen hikâye daha önce kullanılmış, yeniden üretiliyor")
        return None
