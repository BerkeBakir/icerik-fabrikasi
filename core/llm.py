"""Gemini ile şemaya uygun JSON üretimi."""
from __future__ import annotations

import json
import logging
import time

from google import genai
from google.genai import errors as genai_hata
from google.genai import types


class LLMHatasi(Exception):
    pass


VARSAYILAN_MODELLER = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-flash-latest"]

DENEME = 3          # LLMHatasi için aynı modelde deneme sayısı
ASIRI_YUK_DENEME = 2  # aşırı yüklü modelde yedeğe geçmeden önceki deneme sayısı
BEKLEME = 10


def _gecici_mi(e: Exception) -> bool:
    """Aşırı yük / geçici hata: 5xx veya 429."""
    if isinstance(e, genai_hata.ServerError):
        return True
    return isinstance(e, genai_hata.ClientError) and e.code == 429


def _model_yok_mu(e: Exception) -> bool:
    return isinstance(e, genai_hata.APIError) and e.code == 404


class Gemini:
    def __init__(self, api_key: str, modeller: list[str] | None = None, istemci=None,
                 log: logging.Logger | None = None, uyku=time.sleep, model: str | None = None):
        self.modeller = [model] if model else list(modeller or VARSAYILAN_MODELLER)
        self.istemci = istemci or genai.Client(api_key=api_key)
        self.log = log or logging.getLogger(__name__)
        self.uyku = uyku

    def json_uret(self, prompt: str, sema: dict, sicaklik: float = 0.8) -> dict:
        def bir_deneme(model: str) -> dict:
            yanit = self.istemci.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=sema,
                    temperature=sicaklik,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            metin = (yanit.text or "").strip()
            try:
                veri = json.loads(metin)
            except json.JSONDecodeError as e:
                raise LLMHatasi(f"geçersiz JSON: {metin[:200]}") from e
            if not isinstance(veri, dict):
                raise LLMHatasi(f"JSON nesne değil: {metin[:200]}")
            eksik = [k for k in sema.get("required", [])
                     if k not in veri or veri[k] is None or (isinstance(veri[k], str) and not veri[k].strip())]
            if eksik:
                raise LLMHatasi(f"eksik alanlar: {eksik}")
            return veri

        son_hata: Exception | None = None
        for model in self.modeller:
            for i in range(DENEME):
                try:
                    return bir_deneme(model)
                except LLMHatasi:
                    if i == DENEME - 1:
                        raise
                    son_hata = None
                except genai_hata.APIError as e:
                    if _model_yok_mu(e):
                        son_hata = e
                        break
                    if not _gecici_mi(e):
                        raise
                    son_hata = e
                    if i == ASIRI_YUK_DENEME - 1:
                        break
                sure = BEKLEME * 2 ** i
                self.log.warning("%s deneme %d başarısız, %.0f sn sonra tekrar", model, i + 1, sure)
                self.uyku(sure)
            self.log.warning("Gemini modeli %s kullanılamıyor (%s), sonraki modele geçiliyor", model, son_hata)
        raise LLMHatasi(f"Tüm Gemini modelleri başarısız: {son_hata}")
