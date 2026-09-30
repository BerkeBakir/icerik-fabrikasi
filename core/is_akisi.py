"""Kanal iş akışı: hikâye -> senaryo -> ses -> video -> yükleme (yeniden başlatılabilir)."""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from core.ayar import KOK, Kanal, calisma_kilidi_yolu, cikti_klasoru, kilit_yolu
from core.db import DB, Is
from core.kaynak import kaynak_olustur
from core.kilit import KilitHatasi, dosya_kilidi
from core.modeller import Hikaye, TiktokSenaryo, YoutubePaketi
from core.render.tiktok_dikey import render_tiktok as _render_tiktok
from core.render.youtube_uyku import render_youtube as _render_youtube
from core.senaryo import etiketleri_birlestir, tiktok_aciklama, tiktok_senaryo, youtube_paketi
from core.tts import SesSonucu, motor_olustur


class IsHatasi(Exception):
    pass


class OnayGerekli(IsHatasi):
    """Paylaşım yapıldı ama doğrulanamadı; kullanıcı --onayla ya da --yeniden-dene demeli."""


@dataclass
class Baglam:
    kanal: Kanal
    db: DB
    llm: Any
    bildirim: Any
    log: logging.Logger
    kok: Path = KOK
    kuru: bool = False
    tts_fabrika: Callable = motor_olustur
    kaynak_fabrika: Callable = kaynak_olustur
    tiktok_fabrika: Callable | None = None       # kanal -> .yukle(video, aciklama, etiketler, gorunurluk, zaman)
    youtube_yukleyici: Callable | None = None    # (kanal, video, baslik, aciklama, etiketler) -> video_id
    render_tiktok: Callable = _render_tiktok
    render_youtube: Callable = _render_youtube
    simdi: Callable = datetime.now
    uyku: Callable = time.sleep


def _saat_metni(dk: float) -> str:
    saat = dk / 60
    return "1 Hour" if saat == 1 else f"{saat:g} Hours"


def _parca_yukle(b: Baglam, is_: Is, parca: int, yukleyici, *args):
    """Part'ı yükler; Post'a tıklandıktan sonra hata olursa işi onay beklemeye alır."""
    k = b.kanal
    try:
        with dosya_kilidi(kilit_yolu(b.kok)):
            return yukleyici.yukle(*args)
    except Exception as e:
        if not getattr(e, "gonderildi", False):
            raise
        b.db.is_ilerlet(is_.id, is_.durum, bekleyen_onay=f"part{parca}")
        mesaj = (f"⚠️ [{k.ad}] Part {parca} paylaşıldı ama doğrulanamadı. TikTok hesabını kontrol et; "
                 f"yayındaysa 'calistir.py {k.ad} --onayla', değilse 'calistir.py {k.ad} --yeniden-dene' çalıştır.")
        ekran = getattr(e, "ekran", None)
        if ekran:
            b.bildirim.foto(ekran, mesaj)
        else:
            b.bildirim.mesaj(mesaj)
        raise OnayGerekli(f"Part {parca} paylaşıldı ama doğrulanamadı: {e}") from e


def _tiktok(b: Baglam, is_: Is, klasor: Path) -> Is:
    k, db = b.kanal, b.db
    if is_.veri.get("bekleyen_onay"):
        b.log.warning("İş #%d onay bekliyor (%s); '--onayla' ya da '--yeniden-dene' çalıştırılmalı",
                      is_.id, is_.veri["bekleyen_onay"])
        raise OnayGerekli(f"İş #{is_.id} onay bekliyor: {is_.veri['bekleyen_onay']}")
    if not is_.gecti_mi("hikaye_secildi"):
        h = b.kaynak_fabrika(k, b.llm, db, b.log).sec()
        if h is None:
            raise IsHatasi("Uygun hikâye bulunamadı")
        if not b.kuru:
            db.hikaye_isaretle(h.kimlik, k.ad)
        is_ = db.is_ilerlet(is_.id, "hikaye_secildi", hikaye=asdict(h))
    if not is_.gecti_mi("senaryo_hazir"):
        s = tiktok_senaryo(b.llm, Hikaye(**is_.veri["hikaye"]), k.etiketler.llm_ekle)
        is_ = db.is_ilerlet(is_.id, "senaryo_hazir", senaryo=asdict(s))
    s = TiktokSenaryo(**is_.veri["senaryo"])
    if not is_.gecti_mi("ses_hazir"):
        tts = b.tts_fabrika(k.ses, b.log)
        sesler = {p: tts.seslendir(getattr(s, p), klasor / f"{p}.mp3").sozluk() for p in ("part1", "part2")}
        is_ = db.is_ilerlet(is_.id, "ses_hazir", ses=sesler)
    if not is_.gecti_mi("video_hazir"):
        videolar = {p: str(b.render_tiktok(k.arka_plan, SesSonucu.sozlukten(is_.veri["ses"][p]), klasor / f"{p}.mp4"))
                    for p in ("part1", "part2")}
        is_ = db.is_ilerlet(is_.id, "video_hazir", video=videolar)
    if b.kuru:
        b.log.info("Kuru mod: videolar hazır, yükleme yapılmadı: %s", is_.veri["video"])
        return is_

    etiketler = etiketleri_birlestir(k.etiketler.sabit, s.etiketler, k.etiketler.llm_ekle)
    yukleyici = b.tiktok_fabrika(k)
    if not is_.gecti_mi("parca1_yuklendi"):
        _parca_yukle(b, is_, 1, yukleyici, Path(is_.veri["video"]["part1"]), tiktok_aciklama(1, s.aciklama),
                     etiketler, k.gorunurluk, None)
        is_ = db.is_ilerlet(is_.id, "parca1_yuklendi", parca1_zaman=b.simdi().isoformat())
        b.bildirim.mesaj(f"✅ [{k.ad}] Part 1 yayında")
    hedef = datetime.fromisoformat(is_.veri["parca1_zaman"]) + timedelta(minutes=k.parca2_gecikme_dk)
    if k.parca2_yontem == "tiktok_zamanla":
        zaman = max(hedef, b.simdi() + timedelta(minutes=16))
    else:
        kalan = (hedef - b.simdi()).total_seconds()
        if kalan > 0:
            b.log.info("Part 2 için %.0f sn bekleniyor", kalan)
            b.uyku(kalan)
        zaman = None
    etkin = _parca_yukle(b, is_, 2, yukleyici, Path(is_.veri["video"]["part2"]), tiktok_aciklama(2, s.aciklama),
                         etiketler, k.gorunurluk, zaman)
    if zaman is not None and etkin is not None:
        zaman = etkin
    is_ = db.is_ilerlet(is_.id, "yuklendi", parca2_zaman=(zaman or b.simdi()).isoformat())
    b.bildirim.mesaj(f"🏁 [{k.ad}] Part 2 {'zamanlandı: ' + zaman.strftime('%d.%m %H:%M') if zaman else 'yayında'}")
    return is_


def _youtube(b: Baglam, is_: Is, klasor: Path) -> Is:
    k, db = b.kanal, b.db
    if not is_.gecti_mi("senaryo_hazir"):
        prompt = Path(k.kaynak.prompt).read_text(encoding="utf-8")
        p = youtube_paketi(b.llm, prompt, k.kaynak.kelime, b.log)
        kimlik = "uretim:" + hashlib.sha1(p.hikaye.encode("utf-8")).hexdigest()[:12]
        if not b.kuru:
            db.hikaye_isaretle(kimlik, k.ad)
        is_ = db.is_ilerlet(is_.id, "senaryo_hazir", paket=asdict(p))
    p = YoutubePaketi(**is_.veri["paket"])
    if not is_.gecti_mi("ses_hazir"):
        ses = b.tts_fabrika(k.ses, b.log).seslendir(p.hikaye, klasor / "hikaye.mp3")
        is_ = db.is_ilerlet(is_.id, "ses_hazir", ses=ses.sozluk())
    if not is_.gecti_mi("video_hazir"):
        video = klasor / "final.mp4"
        n = b.render_youtube(k.arka_plan, Path(is_.veri["ses"]["yol"]), k.ortam_sesi, k.ortam_seviye,
                             k.tekrar, k.tekrar_arasi_sn, k.hedef_sure_dk * 60, video)
        is_ = db.is_ilerlet(is_.id, "video_hazir", video=str(video), tekrar=n)
    if b.kuru:
        b.log.info("Kuru mod: video hazır (%s tekrar), yükleme yapılmadı: %s", is_.veri["tekrar"], is_.veri["video"])
        return is_
    baslik = f"{p.baslik} - Deep Sleep Story ({_saat_metni(k.hedef_sure_dk)})"
    aciklama = p.aciklama + "\n\n" + " ".join(f"#{e}" for e in p.etiketler[:3])
    vid = b.youtube_yukleyici(k, Path(is_.veri["video"]), baslik, aciklama, p.etiketler)
    is_ = db.is_ilerlet(is_.id, "yuklendi", video_id=vid)
    b.bildirim.mesaj(f"🏁 [{k.ad}] YouTube'a yüklendi ({k.gorunurluk}): https://youtu.be/{vid}")
    return is_


def calistir(b: Baglam) -> Is | None:
    k = b.kanal
    with ExitStack() as yigin:
        try:
            yigin.enter_context(dosya_kilidi(calisma_kilidi_yolu(k, b.kok), bekle_sn=-1))
        except KilitHatasi:
            b.log.info("Kanal zaten çalışıyor, çıkılıyor")
            if not b.kuru:
                b.bildirim.mesaj(f"⏭ [{k.ad}] Kanal zaten çalışıyor, bu çalıştırma atlandı")
            return None
        if not b.kuru:
            b.bildirim.mesaj(f"🚀 [{k.ad}] Çalışma başladı")
        return _calistir(b)


def _calistir(b: Baglam) -> Is:
    k = b.kanal
    anahtar = f"{k.ad}__kuru" if b.kuru else k.ad
    is_ = b.db.yarim_is(anahtar)
    if is_ and b.kuru:
        b.log.info("Önceki yarım kuru iş #%d iptal ediliyor", is_.id)
        b.db.is_iptal(is_.id)
        is_ = None
    if is_:
        b.log.info("Yarım iş #%d devam ediyor (durum: %s)", is_.id, is_.durum)
    else:
        is_ = b.db.is_olustur(anahtar)
        b.log.info("Yeni iş #%d", is_.id)
    klasor = cikti_klasoru(k, is_.id, b.kok)
    klasor.mkdir(parents=True, exist_ok=True)
    if b.kuru:
        b.log.info("Kuru mod çıktı klasörü: %s", klasor)
    try:
        is_ = (_tiktok if k.platform == "tiktok" else _youtube)(b, is_, klasor)
    except OnayGerekli as e:
        b.log.warning("İş #%d manuel onay bekliyor: %s", is_.id, e)
        e.bildirildi = True
        raise
    except Exception as e:
        e.bildirildi = True  # main() tekrar bildirmesin
        if getattr(e, "yetki", False):
            b.db.is_hata(is_.id, f"{type(e).__name__}: {e}", say=False)
            b.log.error("İş #%d oturum/yetki bekliyor: %s", is_.id, e)
            b.bildirim.mesaj(f"🔑 [{k.ad}] Oturum/yetki gerekli: {e}. 'calistir.py {k.ad} --giris' çalıştır.")
            raise
        render_edildi = b.db.is_getir(is_.id).gecti_mi("video_hazir")  # is_ bu çalıştırmanın başından kalma
        is_ = b.db.is_hata(is_.id, f"{type(e).__name__}: {e}")
        b.log.exception("İş #%d hata verdi (deneme %d)", is_.id, is_.deneme)
        mesaj = f"🚨 [{k.ad}] İş #{is_.id} hata ({is_.durum}, deneme {is_.deneme}): {e}"
        if is_.durum == "iptal":
            mesaj += " - iş iptal edildi"
            if render_edildi:
                mesaj += f"; videolar korundu: {klasor}"
            else:
                shutil.rmtree(klasor, ignore_errors=True)
        ekran = getattr(e, "ekran", None)
        if ekran:
            b.bildirim.foto(ekran, mesaj)
        else:
            b.bildirim.mesaj(mesaj)
        raise
    if is_.durum == "yuklendi":
        shutil.rmtree(klasor, ignore_errors=True)
    return is_


def _onay_bekleyen(db: DB, kanal_ad: str) -> Is | None:
    is_ = db.yarim_is(kanal_ad)
    return is_ if is_ and is_.veri.get("bekleyen_onay") else None


def onayla(db: DB, kanal_ad: str, kok: Path, simdi: datetime) -> Is | None:
    """Doğrulanamayan paylaşım elle kontrol edildi ve yayında: işi ilerletir."""
    is_ = _onay_bekleyen(db, kanal_ad)
    if is_ is None:
        return None
    if is_.veri["bekleyen_onay"] == "part1":
        return db.is_ilerlet(is_.id, "parca1_yuklendi", parca1_zaman=simdi.isoformat(), bekleyen_onay=None)
    is_ = db.is_ilerlet(is_.id, "yuklendi", parca2_zaman=simdi.isoformat(), bekleyen_onay=None)
    shutil.rmtree(cikti_klasoru(kanal_ad, is_.id, kok), ignore_errors=True)
    return is_


def yeniden_dene(db: DB, kanal_ad: str) -> Is | None:
    """Doğrulanamayan paylaşım yayında değil: bayrağı temizler, sonraki çalıştırma tekrar yükler."""
    is_ = _onay_bekleyen(db, kanal_ad)
    if is_ is None:
        return None
    return db.is_ilerlet(is_.id, is_.durum, bekleyen_onay=None)
