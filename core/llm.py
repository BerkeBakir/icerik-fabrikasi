"""Gemini ile şemaya uygun JSON üretimi."""
from __future__ import annotations

import json
import logging
import time

from google import genai
from google.genai import types

from core.tekrar import tekrar_dene


class LLMHatasi(Exception):
    pass


class Gemini:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", istemci=None,
                 log: logging.Logger | None = None, uyku=time.sleep):
        self.model = model
        self.istemci = istemci or genai.Client(api_key=api_key)
        self.log = log or logging.getLogger(__name__)
        self.uyku = uyku

    def json_uret(self, prompt: str, sema: dict, sicaklik: float = 0.8) -> dict:
        def bir_deneme() -> dict:
            yanit = self.istemci.models.generate_content(
                model=self.model,
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

        return tekrar_dene(bir_deneme, deneme=3, bekleme=10, uyku=self.uyku, log=self.log)
