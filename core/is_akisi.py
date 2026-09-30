"""Kanal iş akışı: hikâye -> senaryo -> ses -> video -> yükleme (yeniden başlatılabilir)."""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from core.ayar import KOK, Kanal, cikti_klasoru, kilit_yolu
from core.db import DB, Is
from core.kaynak import kaynak_olustur
from core.kilit import dosya_kilidi
from core.modeller import Hikaye, TiktokSenaryo, YoutubePaketi
from core.render.tiktok_dikey import render_tiktok as _render_tiktok
from core.render.youtube_uyku import render_youtube as _render_youtube
from core.senaryo import etiketleri_birlestir, tiktok_aciklama, tiktok_senaryo, youtube_paketi
from core.tts import SesSonucu, motor_olustur


class IsHatasi(Exception):
    pass


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


def _tiktok(b: Baglam, is_: Is, klasor: Path) -> Is:
    k, db = b.kanal, b.db
    if not is_.gecti_mi("hikaye_secildi"):
        h = b.kaynak_fabrika(k, b.llm, db, b.log).sec()
        if h is None:
            raise IsHatasi("Uygun hikâye bulunamadı")
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
        with dosya_kilidi(kilit_yolu(b.kok)):
            yukleyici.yukle(Path(is_.veri["video"]["part1"]), tiktok_aciklama(1, s.aciklama),
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
    with dosya_kilidi(kilit_yolu(b.kok)):
        yukleyici.yukle(Path(is_.veri["video"]["part2"]), tiktok_aciklama(2, s.aciklama),
                        etiketler, k.gorunurluk, zaman)
    is_ = db.is_ilerlet(is_.id, "yuklendi", parca2_zaman=(zaman or b.simdi()).isoformat())
    b.bildirim.mesaj(f"🏁 [{k.ad}] Part 2 {'zamanlandı: ' + zaman.strftime('%H:%M') if zaman else 'yayında'}")
    return is_


def _youtube(b: Baglam, is_: Is, klasor: Path) -> Is:
    k, db = b.kanal, b.db
    if not is_.gecti_mi("senaryo_hazir"):
        prompt = Path(k.kaynak.prompt).read_text(encoding="utf-8")
        p = youtube_paketi(b.llm, prompt, k.kaynak.kelime, b.log)
        kimlik = "uretim:" + hashlib.sha1(p.hikaye.encode("utf-8")).hexdigest()[:12]
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


def calistir(b: Baglam) -> Is:
    k = b.kanal
    is_ = b.db.yarim_is(k.ad)
    if is_:
        b.log.info("Yarım iş #%d devam ediyor (durum: %s)", is_.id, is_.durum)
    else:
        is_ = b.db.is_olustur(k.ad)
        b.log.info("Yeni iş #%d", is_.id)
    klasor = cikti_klasoru(k, is_.id, b.kok)
    klasor.mkdir(parents=True, exist_ok=True)
    try:
        is_ = (_tiktok if k.platform == "tiktok" else _youtube)(b, is_, klasor)
    except Exception as e:
        is_ = b.db.is_hata(is_.id, f"{type(e).__name__}: {e}")
        b.log.exception("İş #%d hata verdi (deneme %d)", is_.id, is_.deneme)
        mesaj = f"🚨 [{k.ad}] İş #{is_.id} hata ({is_.durum}, deneme {is_.deneme}): {e}"
        ekran = getattr(e, "ekran", None)
        if ekran:
            b.bildirim.foto(ekran, mesaj)
        else:
            b.bildirim.mesaj(mesaj)
        raise
    if is_.durum == "yuklendi":
        shutil.rmtree(klasor, ignore_errors=True)
    return is_
