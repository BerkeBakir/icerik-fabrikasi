"""Telegram bildirimleri. Hiçbir koşulda hata fırlatmaz."""
from __future__ import annotations

import logging

import requests

API = "https://api.telegram.org/bot{token}/{metot}"


class Bildirim:
    def __init__(self, token: str | None, chat_id: str | None, log: logging.Logger | None = None, oturum=None):
        self.token = token
        self.chat_id = chat_id
        self.log = log or logging.getLogger(__name__)
        self.oturum = oturum or requests

    def _aktif(self) -> bool:
        return bool(self.token and self.chat_id)

    def _gizle(self, e: Exception) -> str:
        """Hata mesajında token'i gizler."""
        if self.token:
            return str(e).replace(self.token, "***")
        return str(e)

    def mesaj(self, metin: str) -> None:
        if not self._aktif():
            return
        try:
            yanit = self.oturum.post(API.format(token=self.token, metot="sendMessage"),
                                      data={"chat_id": self.chat_id, "text": metin[:4000]}, timeout=15)
            yanit.raise_for_status()
        except Exception as e:  # bildirim asla işi durdurmaz
            self.log.warning("Telegram mesajı gönderilemedi: %s", self._gizle(e))

    def foto(self, yol, aciklama: str) -> None:
        if not self._aktif():
            return
        try:
            with open(yol, "rb") as f:
                yanit = self.oturum.post(API.format(token=self.token, metot="sendPhoto"),
                                         data={"chat_id": self.chat_id, "caption": aciklama[:1000]},
                                         files={"photo": f}, timeout=30)
                yanit.raise_for_status()
        except Exception as e:
            self.log.warning("Telegram fotoğrafı gönderilemedi: %s", self._gizle(e))
            self.mesaj(aciklama)
