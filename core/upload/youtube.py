"""YouTube Data API v3 ile resumable yükleme."""
from __future__ import annotations

import logging
import pickle
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TEKRARLANABILIR_HTTP = {500, 502, 503, 504}


class YukleHatasi(Exception):
    pass


def kimlik_yukle(token_yol: Path, client_secret: Path, eski_pickle: Path | None = None,
                 etkilesimli: bool = False) -> Credentials:
    token_yol = Path(token_yol)
    creds = None
    if token_yol.exists():
        creds = Credentials.from_authorized_user_file(str(token_yol), SCOPES)
    elif eski_pickle and Path(eski_pickle).exists():
        with open(eski_pickle, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif etkilesimli:
            if not Path(client_secret).exists():
                raise YukleHatasi(f"client_secret.json bulunamadı: {client_secret}")
            creds = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES).run_local_server(port=0)
        else:
            raise YukleHatasi("YouTube yetkisi yok ya da geçersiz; 'calistir.py <kanal> --giris' çalıştır")

    token_yol.parent.mkdir(parents=True, exist_ok=True)
    token_yol.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _temizle(t: str) -> str:
    return t.replace("<", "").replace(">", "")


def govde_olustur(baslik: str, aciklama: str, etiketler: list[str], kategori: str, gorunurluk: str) -> dict:
    secilen, toplam = [], 0
    for e in etiketler:
        e = _temizle(e)[:30]
        if e and toplam + len(e) + 2 <= 480:
            secilen.append(e)
            toplam += len(e) + 2
    return {
        "snippet": {
            "title": _temizle(baslik).strip()[:100],
            "description": _temizle(aciklama)[:4900],
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
            if durum:
                log.info("YouTube yükleme: %%%d", int(durum.progress() * 100))
        except HttpError as e:
            if e.resp.status not in TEKRARLANABILIR_HTTP:
                raise YukleHatasi(f"YouTube API hatası: {e}") from e
            hata += 1
            if hata > deneme:
                raise YukleHatasi(f"{deneme} denemeden sonra vazgeçildi: {e}") from e
            uyku(min(60, 2 ** hata))
        except (ConnectionError, OSError, TimeoutError) as e:
            hata += 1
            if hata > deneme:
                raise YukleHatasi(f"{deneme} denemeden sonra vazgeçildi: {e}") from e
            log.warning("Bağlantı hatası (%s), tekrar deneniyor", e)
            uyku(min(60, 2 ** hata))
    if "id" not in yanit:
        raise YukleHatasi(f"Beklenmeyen YouTube cevabı: {yanit}")
    return yanit["id"]
