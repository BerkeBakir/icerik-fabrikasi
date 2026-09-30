"""Kullanım:
  python calistir.py <kanal>            işi çalıştır (yarım iş varsa devam eder)
  python calistir.py <kanal> --kuru     yükleme hariç her şeyi üret
  python calistir.py <kanal> --giris    TikTok girişi / YouTube yetkisi (bir kerelik)
  python calistir.py --ses-ornekleri    ses örneklerini cikti/ses_ornekleri/ altına üret
"""
from __future__ import annotations

import argparse
import sys

from core import gunluk
from core.ayar import (KOK, AyarHatasi, client_secret_yolu, db_yolu, eski_token_yolu, hata_klasoru,
                       kanal_yukle, ortam, ortami_yukle, profil_yolu, token_yolu)
from core.bildirim import Bildirim
from core.db import DB
from core.onkontrol import onkontrol


def _tiktok_fabrika(log):
    from core.upload.tiktok import TikTokYukleyici

    return lambda kanal: TikTokYukleyici(profil_yolu(kanal), hata_klasoru(), log)


def _youtube_yukleyici(log):
    from core.upload import youtube

    def yukle(kanal, video, baslik, aciklama, etiketler):
        creds = youtube.kimlik_yukle(token_yolu(kanal), client_secret_yolu(), eski_token_yolu(kanal))
        return youtube.yukle(creds, video, baslik, aciklama, etiketler, kanal.kategori, kanal.gorunurluk, log=log)

    return yukle


def _giris(kanal, log) -> int:
    if kanal.platform == "tiktok":
        from core.upload.tiktok import TikTokYukleyici

        TikTokYukleyici(profil_yolu(kanal), hata_klasoru(), log).giris()
        log.info("TikTok oturumu kaydedildi: %s", profil_yolu(kanal))
    else:
        from core.upload import youtube

        youtube.kimlik_yukle(token_yolu(kanal), client_secret_yolu(), eski_token_yolu(kanal), etkilesimli=True)
        log.info("YouTube yetkisi kaydedildi: %s", token_yolu(kanal))
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="İçerik Fabrikası")
    p.add_argument("kanal", nargs="?")
    p.add_argument("--kuru", action="store_true", help="yükleme yapmadan üret")
    p.add_argument("--giris", action="store_true", help="hesap girişi / yetki")
    p.add_argument("--ses-ornekleri", action="store_true")
    a = p.parse_args(argv)
    ortami_yukle()

    if a.ses_ornekleri:
        from core import ses_ornekleri

        for y in ses_ornekleri.uret():
            print(y)
        return 0
    if not a.kanal:
        p.error("kanal adı gerekli")

    try:
        kanal = kanal_yukle(a.kanal)
    except AyarHatasi as e:
        print(f"Ayar hatası: {e}")
        return 2
    log = gunluk.kur(kanal.ad)
    if a.giris:
        return _giris(kanal, log)

    hatalar = onkontrol(kanal, kuru=a.kuru)
    if hatalar:
        for h in hatalar:
            log.error(h)
        return 2

    from core.is_akisi import Baglam, calistir
    from core.llm import Gemini

    bildirim = Bildirim(ortam("TELEGRAM_BOT_TOKEN", False), ortam("TELEGRAM_CHAT_ID", False), log)
    b = Baglam(
        kanal=kanal, db=DB(db_yolu()), bildirim=bildirim, log=log, kok=KOK, kuru=a.kuru,
        llm=Gemini(ortam("GEMINI_API_KEY"), model=ortam("GEMINI_MODEL", False) or "gemini-2.5-flash", log=log),
        tiktok_fabrika=_tiktok_fabrika(log), youtube_yukleyici=_youtube_yukleyici(log),
    )
    if not a.kuru:
        bildirim.mesaj(f"🚀 [{kanal.ad}] Çalışma başladı")
    try:
        is_ = calistir(b)
    except Exception:
        return 1
    log.info("İş #%d bitti: %s", is_.id, is_.durum)
    return 0


if __name__ == "__main__":
    sys.exit(main())
