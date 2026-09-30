"""Kullanım:
  python calistir.py <kanal>            işi çalıştır (yarım iş varsa devam eder)
  python calistir.py <kanal> --kuru     yükleme hariç her şeyi üret
  python calistir.py <kanal> --giris    TikTok girişi / YouTube yetkisi (bir kerelik)
  python calistir.py <kanal> --onayla         doğrulanamayan TikTok paylaşımı yayında: işi ilerlet
  python calistir.py <kanal> --yeniden-dene   doğrulanamayan TikTok paylaşımı yayında değil: tekrar yükle
  python calistir.py --ses-ornekleri    ses örneklerini cikti/ses_ornekleri/ altına üret
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

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


def _onay(kanal, onay: bool) -> int:
    from core.is_akisi import onayla, yeniden_dene

    db = DB(db_yolu())
    is_ = onayla(db, kanal.ad, KOK, datetime.now()) if onay else yeniden_dene(db, kanal.ad)
    if is_ is None:
        print(f"[{kanal.ad}] Onay bekleyen iş yok")
        return 1
    if onay:
        print(f"[{kanal.ad}] İş #{is_.id} onaylandı, yeni durum: {is_.durum}")
    else:
        print(f"[{kanal.ad}] İş #{is_.id} bir sonraki çalıştırmada tekrar yüklenecek (durum: {is_.durum})")
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="İçerik Fabrikası")
    p.add_argument("kanal", nargs="?")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--kuru", action="store_true", help="yükleme yapmadan üret")
    g.add_argument("--giris", action="store_true", help="hesap girişi / yetki")
    g.add_argument("--ses-ornekleri", action="store_true")
    g.add_argument("--onayla", action="store_true", help="doğrulanamayan paylaşım yayında, işi ilerlet")
    g.add_argument("--yeniden-dene", action="store_true", help="doğrulanamayan paylaşımı tekrar yükle")
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
        try:
            return _giris(kanal, log)
        except Exception as e:
            log.error("Giriş başarısız: %s", e)
            print(f"Giriş hatası ({type(e).__name__}): {e}")
            return 1
    if a.onayla or a.yeniden_dene:
        return _onay(kanal, a.onayla)

    bildirim = Bildirim(ortam("TELEGRAM_BOT_TOKEN", False), ortam("TELEGRAM_CHAT_ID", False), log)
    hatalar = onkontrol(kanal, kuru=a.kuru)
    if hatalar:
        for h in hatalar:
            log.error(h)
        if not a.kuru:
            bildirim.mesaj(f"🚨 [{kanal.ad}] Ön kontrol başarısız:\n" + "\n".join(hatalar))
        return 2

    from core.is_akisi import Baglam, OnayGerekli, calistir
    from core.llm import Gemini

    try:
        b = Baglam(
            kanal=kanal, db=DB(db_yolu()), bildirim=bildirim, log=log, kok=KOK, kuru=a.kuru,
            llm=Gemini(ortam("GEMINI_API_KEY"), model=ortam("GEMINI_MODEL", False) or "gemini-2.5-flash", log=log),
            tiktok_fabrika=_tiktok_fabrika(log), youtube_yukleyici=_youtube_yukleyici(log),
        )
    except Exception as e:
        log.exception("Başlatma hatası")
        if not a.kuru:
            bildirim.mesaj(f"🚨 [{kanal.ad}] Başlatma hatası: {type(e).__name__}: {e}")
        return 1
    try:
        is_ = calistir(b)
    except OnayGerekli as e:
        log.warning("Manuel onay gerekli: %s", e)
        return 3
    except Exception as e:
        if not getattr(e, "bildirildi", False):
            log.exception("Beklenmeyen hata")
            if not a.kuru:
                bildirim.mesaj(f"🚨 [{kanal.ad}] Beklenmeyen hata: {type(e).__name__}: {e}")
        return 1
    if is_ is None:
        log.info("Kanal zaten çalışıyor, çıkılıyor")
        return 0
    log.info("İş #%d bitti: %s", is_.id, is_.durum)
    return 0


if __name__ == "__main__":
    sys.exit(main())
