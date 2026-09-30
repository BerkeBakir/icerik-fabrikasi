"""Reddit'ten anahtarsız RSS ile hikâye seçimi."""
from __future__ import annotations

import html
import logging
import re
import time
import xml.etree.ElementTree as ET

import requests

from core.modeller import Hikaye

RSS_URL = "https://www.reddit.com/r/{sub}/top/.rss?t={t}&limit=50"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
ATOM = "{http://www.w3.org/2005/Atom}"
EDIT_RE = re.compile(r"^\s*\**\s*(edit|update|eta)\b\s*\d*\s*\**\s*[:\-–]", re.IGNORECASE)


def html_to_metin(h: str) -> str:
    m = re.search(r"<!--\s*SC_OFF\s*-->(.*?)<!--\s*SC_ON\s*-->", h, re.DOTALL)
    if not m:
        return ""
    h = m.group(1)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)</(p|li|h\d|blockquote)>", "\n\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    h = html.unescape(h)
    paragraflar = [re.sub(r"[ \t ]+", " ", p).strip() for p in re.split(r"\n\s*\n", h)]
    return "\n\n".join(p for p in paragraflar if p)


def metni_temizle(t: str) -> str:
    t = re.sub(r"https?://\S+", "", t)
    sonuc = []
    for p in t.split("\n\n"):
        if EDIT_RE.match(p):
            break
        sonuc.append(p.strip())
    return "\n\n".join(p for p in sonuc if p)


def rss_ayristir(xml_metni: str) -> list[Hikaye]:
    kok = ET.fromstring(xml_metni)
    hikayeler = []
    for e in kok.findall(f"{ATOM}entry"):
        kimlik = (e.findtext(f"{ATOM}id") or "").strip()
        baslik = html.unescape(e.findtext(f"{ATOM}title") or "").strip()
        govde = metni_temizle(html_to_metin(e.findtext(f"{ATOM}content") or ""))
        if kimlik and govde:
            hikayeler.append(Hikaye(f"reddit:{kimlik.removeprefix('t3_')}", baslik, govde))
    return hikayeler


class RedditKaynak:
    def __init__(self, subredditler: list[str], min_k: int, max_k: int, db, oturum=None,
                 uyku=time.sleep, bekleme: float = 25, log: logging.Logger | None = None):
        self.subredditler = subredditler
        self.min_k, self.max_k = min_k, max_k
        self.db = db
        self.oturum = oturum or requests
        self.uyku = uyku
        self.bekleme = bekleme
        self.log = log or logging.getLogger(__name__)
        self._istek_yapildi = False

    def _getir(self, sub: str, t: str) -> str:
        if self._istek_yapildi:
            self.uyku(self.bekleme)
        self._istek_yapildi = True
        url = RSS_URL.format(sub=sub, t=t)
        for deneme in range(2):
            try:
                r = self.oturum.get(url, headers={"User-Agent": UA}, timeout=20)
                if r.status_code == 200 and "<entry" in r.text:
                    return r.text
                self.log.warning("r/%s RSS cevabı uygun değil (HTTP %s)", sub, r.status_code)
            except requests.RequestException as e:
                self.log.warning("r/%s RSS isteği başarısız: %s", sub, e)
            if deneme == 0:
                self.uyku(60)
        return ""

    def sec(self) -> Hikaye | None:
        for t in ("week", "month"):
            for sub in self.subredditler:
                xml_metni = self._getir(sub, t)
                if not xml_metni:
                    continue
                try:
                    hikayeler = rss_ayristir(xml_metni)
                except ET.ParseError as e:
                    self.log.warning("r/%s RSS ayrıştırılamadı: %s", sub, e)
                    continue
                for h in hikayeler:
                    if self.min_k <= len(h.govde) <= self.max_k and not self.db.hikaye_kullanildi_mi(h.kimlik):
                        self.log.info("Hikâye seçildi: r/%s %s (%d karakter)", sub, h.kimlik, len(h.govde))
                        return h
        return None
