"""Yorum akışı: oku → kaydet → sınıflandır → sınırlar dahilinde eylem → bildirim."""
from __future__ import annotations

import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.db import DB, yorum_kimligi
from core.yorum import HamYorum, YorumIslemHatasi
from core.yorum.siniflandir import SESSIZ, siniflandir

SIKAYET_SINIR = 5
BEGENI_SINIR = 30
SINIFLANDIRMA_SINIR = 40
ARDISIK_HATA_SINIR = 3
UNUTMA_GUN = 8

EYLEM = {"soru": "cevap", "yapici": "cevap", "yorum": "begeni", "hakaret": "sikayet", "spam": "sikayet"}
DURUM = {"cevap": "cevaplandi", "begeni": "begenildi", "sikayet": "sikayet_edildi"}
BEKLEME = {"cevap": (20, 60), "sikayet": (20, 60), "begeni": (3, 8)}


@dataclass
class Ozet:
    cevap: int = 0
    begeni: int = 0
    sikayet: int = 0
    hata: int = 0
    bekleyen: int = 0

    def metin(self, kanal_ad: str) -> str:
        m = f"🧾 [{kanal_ad}] {self.cevap} cevap, {self.begeni} beğeni, {self.sikayet} şikayet"
        if self.hata:
            m += f" ({self.hata} hata)"
        if self.bekleyen:
            m += f", {self.bekleyen} sonraki çalıştırmaya kaldı"
        return m


def _kisa(metin: str, n: int = 40) -> str:
    return metin if len(metin) <= n else metin[: n - 1] + "…"


def baglam_bul(db: DB, kanal_ad: str, video: str) -> str | None:
    """Video başlığıyla eşleşen işin kancası/açıklaması (Gemini'ye bağlam)."""
    govde = video.split("|", 1)[-1].strip().rstrip("…").strip()
    if len(govde) < 15:
        return None
    for is_ in db.son_isler(kanal_ad):
        s = is_.veri.get("senaryo") or {}
        aciklama = s.get("aciklama") or ""
        if aciklama and (aciklama.startswith(govde[:60]) or govde.startswith(aciklama[:60])):
            return f"Story hook: {s.get('hook', '')}\nCaption: {aciklama}"
    return None


def _bildir(bildirim, ekran, mesaj: str) -> None:
    if ekran:
        bildirim.foto(ekran, mesaj)
    else:
        bildirim.mesaj(mesaj)


def _limitler(kanal) -> dict[str, int]:
    return {"cevap": kanal.yorum_en_fazla, "sikayet": SIKAYET_SINIR, "begeni": BEGENI_SINIR}


def _bizim_mi(kanal, db: DB, h: HamYorum) -> bool:
    return h.kullanici.strip().lstrip("@").lower() == (kanal.yorum_hesap or "") or db.yorum_cevap_mi(kanal.ad, h.metin)


def _kuru(kanal, db, llm, hamlar, log) -> Ozet:
    for h in hamlar[:SINIFLANDIRMA_SINIR]:
        if _bizim_mi(kanal, db, h):
            continue
        try:
            k = siniflandir(llm, h, baglam_bul(db, kanal.ad, h.video))
        except Exception as e:
            log.warning("[kuru] @%s sınıflandırılamadı: %s", h.kullanici, e)
            continue
        log.info("[kuru] @%s: %r → %s %r %s", h.kullanici, h.metin, k.tur, k.cevap, k.oneri)
    return Ozet()


def yorumlari_isle(kanal, db: DB, llm, yorumcu, bildirim, log: logging.Logger, kuru: bool = False,
                   uyku=time.sleep, rastgele=random, simdi: datetime | None = None) -> Ozet:
    ozet = Ozet()
    simdi = simdi or datetime.now()
    with yorumcu.oturum() as sayfa:
        hamlar = sayfa.oku()
        log.info("%d yorum okundu", len(hamlar))
        if not hamlar:
            log.warning("Hiç yorum okunamadı")
        if kuru:
            return _kuru(kanal, db, llm, hamlar, log)

        gorunen: dict[str, HamYorum] = {}
        for h in hamlar:
            if _bizim_mi(kanal, db, h):
                continue
            kim = yorum_kimligi(kanal.ad, h.kullanici, h.metin, h.video)
            db.yorum_ekle(kim, kanal.ad, h.kullanici, h.metin, h.video)
            gorunen[kim] = h

        sayac = defaultdict(int)
        limit = _limitler(kanal)
        siniflandirilan = 0
        ardisik_hata = 0
        for y in db.yorum_islenecekler(kanal.ad):
            h = gorunen.get(y.kimlik)
            if h is None:  # bu çalıştırmada görünmüyor: yalnız UNUTMA_GUN'den eskiyse atla
                if datetime.fromisoformat(y.tarih) < simdi - timedelta(days=UNUTMA_GUN):
                    db.yorum_bitir(y.kimlik, "atlandi")
                continue
            if y.durum == "yeni":
                if siniflandirilan >= SINIFLANDIRMA_SINIR:
                    ozet.bekleyen += 1
                    continue
                siniflandirilan += 1
                try:
                    k = siniflandir(llm, h, baglam_bul(db, kanal.ad, h.video))
                except Exception as e:  # Gemini geçici hatası: yorum 'yeni' kalır
                    log.warning("Sınıflandırılamadı (@%s): %s", h.kullanici, e)
                    continue
                y = db.yorum_karar(y.kimlik, k.tur, k.cevap, k.konu, k.oneri)
            if y.tur == SESSIZ:
                db.yorum_bitir(y.kimlik, "atlandi")
                continue
            eylem = EYLEM.get(y.tur or "", "begeni")
            if sayac[eylem] >= limit[eylem]:
                ozet.bekleyen += 1
                continue
            try:
                if eylem == "cevap":
                    sayfa.cevapla(h, y.cevap)
                elif eylem == "sikayet":
                    sayfa.sikayet_et(h, y.tur)
                else:
                    sayfa.begen(h)
            except YorumIslemHatasi as e:
                if e.yetki:
                    raise
                ozet.hata += 1
                ardisik_hata += 1
                log.warning("Eylem başarısız (@%s, %s): %s", h.kullanici, eylem, e)
                if e.gonderildi:  # eylem gerçekleşmiş olabilir: tekrar denenirse çift cevap/şikayet olur
                    db.yorum_belirsiz(y.kimlik, str(e))
                    _bildir(bildirim, e.ekran, f'⚠️ [{kanal.ad}] @{h.kullanici}: {eylem} gönderildi ama '
                                               f'doğrulanamadı (tekrar denenmeyecek): "{h.metin}"')
                else:
                    db.yorum_hata(y.kimlik, str(e))
                if ardisik_hata >= ARDISIK_HATA_SINIR:
                    _bildir(bildirim, e.ekran,
                            f"🚨 [{kanal.ad}] Yorum işleme durdu: üst üste {ardisik_hata} hata. Son hata: {e}")
                    e.bildirildi = True
                    raise
                continue
            ardisik_hata = 0
            db.yorum_bitir(y.kimlik, DURUM[eylem])
            sayac[eylem] += 1
            setattr(ozet, eylem, getattr(ozet, eylem) + 1)
            if eylem == "cevap":
                bildirim.mesaj(f'💬 [{kanal.ad}] @{h.kullanici} ({_kisa(h.video)})\n"{h.metin}"\n↳ "{y.cevap}"')
            elif eylem == "sikayet":
                bildirim.mesaj(f'🚩 [{kanal.ad}] @{h.kullanici} şikayet edildi ({y.tur}): "{h.metin}"')
            uyku(rastgele.uniform(*BEKLEME[eylem]))

    if ozet.cevap or ozet.begeni or ozet.sikayet or ozet.hata:
        bildirim.mesaj(ozet.metin(kanal.ad))
    log.info(ozet.metin(kanal.ad))
    return ozet


def rapor(kanal, db: DB, bildirim, simdi: datetime) -> str:
    kayitlar = db.yapici_yorumlar(kanal.ad, simdi - timedelta(days=7))
    if not kayitlar:
        mesaj = f"📊 [{kanal.ad}] Bu hafta yapıcı yorum yok"
    else:
        gruplar: dict[str, list[str]] = defaultdict(list)
        for y in kayitlar:
            gruplar[y.konu or "diger"].append(y.oneri or y.metin)
        satirlar = [f"📊 [{kanal.ad}] Haftalık yapıcı yorumlar ({len(kayitlar)})"]
        for konu, oneriler in sorted(gruplar.items(), key=lambda g: (-len(g[1]), g[0])):
            ornek = ", ".join(f'"{_kisa(o, 60)}"' for o in oneriler[:3])
            satirlar.append(f"• {konu} ({len(oneriler)}): {ornek}")
        mesaj = "\n".join(satirlar)
    bildirim.mesaj(mesaj)
    return mesaj
