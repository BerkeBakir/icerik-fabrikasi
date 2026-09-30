"""YouTube Data API v3 ile resumable yükleme."""
from __future__ import annotations

import http.client
import logging
import os
import pickle
import time
from pathlib import Path

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
import httplib2
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TEKRARLANABILIR_HTTP = {500, 502, 503, 504}
_AG_HATALARI = (OSError, http.client.HTTPException, httplib2.HttpLib2Error, TransportError)


class YukleHatasi(Exception):
    """yetki=True: kullanıcının '--giris' çalıştırması gerekir."""

    def __init__(self, mesaj: str, yetki: bool = False):
        super().__init__(mesaj)
        self.yetki = yetki


def _kayitli_kimlik(token_yol: Path, eski_pickle: Path | None):
    """(creds, yeni_mi): bozuk dosya 'kimlik yok' sayılır."""
    if token_yol.exists():
        try:
            return Credentials.from_authorized_user_file(str(token_yol), SCOPES), False
        except (ValueError, OSError):
            return None, False
    if eski_pickle and Path(eski_pickle).exists():
        try:
            with open(eski_pickle, "rb") as f:
                return pickle.load(f), True
        except Exception:
            return None, False
    return None, False


def kimlik_yukle(token_yol: Path, client_secret: Path, eski_pickle: Path | None = None,
                 etkilesimli: bool = False) -> Credentials:
    token_yol = Path(token_yol)
    creds, yazilacak = _kayitli_kimlik(token_yol, eski_pickle)

    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            yazilacak = True
        except RefreshError:
            creds = None
        except TransportError as e:
            raise YukleHatasi(f"YouTube token yenilenemedi (ağ): {e}") from e

    if not creds or not creds.valid:
        if not etkilesimli:
            raise YukleHatasi("YouTube yetkisi yok ya da geçersiz; 'calistir.py <kanal> --giris' çalıştır",
                              yetki=True)
        if not Path(client_secret).exists():
            raise YukleHatasi(f"client_secret.json bulunamadı: {client_secret}")
        creds = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES).run_local_server(port=0)
        yazilacak = True

    if yazilacak:
        token_yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = token_yol.with_suffix(".json.tmp")
        gecici.write_text(creds.to_json(), encoding="utf-8")
        os.replace(gecici, token_yol)
    return creds


def _temizle(t: str) -> str:
    return t.replace("<", "").replace(">", "")


def _bayt_kirp(t: str, sinir: int) -> str:
    return t.encode("utf-8")[:sinir].decode("utf-8", "ignore")


def govde_olustur(baslik: str, aciklama: str, etiketler: list[str], kategori: str, gorunurluk: str) -> dict:
    secilen, toplam = [], 0
    for e in etiketler:
        e = _temizle(e)[:30]
        if e and toplam + len(e) + 2 <= 480:
            secilen.append(e)
            toplam += len(e) + 2
    return {
        "snippet": {
            "title": _temizle(baslik).strip()[:100] or "Sleep Story",
            "description": _bayt_kirp(_temizle(aciklama), 4900),
            "tags": secilen,
            "categoryId": str(kategori),
        },
        "status": {"privacyStatus": gorunurluk, "selfDeclaredMadeForKids": False},
    }


def yukle(creds, video: Path, baslik: str, aciklama: str, etiketler: list[str], kategori: str,
          gorunurluk: str, servis=None, deneme: int = 10, uyku=time.sleep,
          log: logging.Logger | None = None) -> str:
    log = log or logging.getLogger(__name__)
    servis = servis or build("youtube", "v3", credentials=creds)
    istek = servis.videos().insert(
        part="snippet,status",
        body=govde_olustur(baslik, aciklama, etiketler, kategori, gorunurluk),
        media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True),
    )
    yanit, hata = None, 0
    while yanit is None:
        try:
            durum, yanit = istek.next_chunk()
            hata = 0
            if durum:
                log.info("YouTube yükleme: %%%d", int(durum.progress() * 100))
            continue
        except HttpError as e:
            if e.resp.status not in TEKRARLANABILIR_HTTP:
                raise YukleHatasi(f"YouTube API hatası: {e}") from e
            sebep = e
        except _AG_HATALARI as e:
            sebep = e
        hata += 1
        if hata > deneme:
            raise YukleHatasi(f"{deneme} denemeden sonra vazgeçildi: {sebep}") from sebep
        log.warning("YouTube yükleme hatası (%s), tekrar deneniyor (%d/%d)", sebep, hata, deneme)
        uyku(min(60, 2 ** hata))
    if "id" not in yanit:
        raise YukleHatasi(f"Beklenmeyen YouTube cevabı: {yanit}")
    return yanit["id"]
