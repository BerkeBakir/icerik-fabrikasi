"""Kanal ayarlarını (kanallar/*.yaml) ve .env'i okur, doğrular."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent.parent

TIKTOK_GORUNURLUK = {"herkes", "arkadaslar", "sadece_ben"}
YOUTUBE_GORUNURLUK = {"public", "unlisted", "private"}
PARCA2_YONTEMLERI = {"tiktok_zamanla", "bekle"}


class AyarHatasi(Exception):
    pass


@dataclass
class Ses:
    motor: str
    ses: str
    hiz: str | float


@dataclass
class Kaynak:
    tip: str
    subredditler: list[str] = field(default_factory=list)
    min: int = 3000
    max: int = 4000
    prompt: Path | None = None
    kelime: int = 2500


@dataclass
class Etiketler:
    sabit: list[str] = field(default_factory=list)
    llm_ekle: int = 0


@dataclass
class Kanal:
    ad: str
    platform: str
    kaynak: Kaynak
    ses: Ses
    arka_plan: Path
    gorunurluk: str
    etiketler: Etiketler = field(default_factory=Etiketler)
    profil: str | None = None
    parca2_gecikme_dk: int = 120
    parca2_yontem: str = "tiktok_zamanla"
    arka_plan_kredi: str | None = None
    yorum_aktif: bool = False
    yorum_en_fazla: int = 10
    yorum_hesap: str | None = None
    token: str | None = None
    tekrar: int = 5
    tekrar_arasi_sn: float = 8.0
    hedef_sure_dk: float = 90.0
    ortam_sesi: Path | None = None
    ortam_seviye: float = 0.25
    kategori: str = "22"


def _zorunlu(d: dict, anahtar: str, yer: str):
    if not isinstance(d, dict) or d.get(anahtar) in (None, "", []):
        raise AyarHatasi(f"{yer}: '{anahtar}' alanı zorunlu")
    return d[anahtar]


def _hiz_dogrula(motor: str, hiz, yer: str):
    if motor == "edge":
        if not (isinstance(hiz, str) and re.fullmatch(r"[+-]\d+%", hiz)):
            raise AyarHatasi(f"{yer}: ses.hiz edge için '+10%' ya da '-5%' biçiminde olmalı, verilen: {hiz!r}")
    elif isinstance(hiz, bool) or not isinstance(hiz, (int, float)) or not 0 < hiz <= 2:
        raise AyarHatasi(f"{yer}: ses.hiz kokoro için 0'dan büyük, en fazla 2 olan bir sayı olmalı, verilen: {hiz!r}")
    return hiz


def kanal_yukle(ad: str, kok: Path = KOK) -> Kanal:
    yol = kok / "kanallar" / f"{ad}.yaml"
    if not yol.exists():
        raise AyarHatasi(f"Kanal dosyası yok: {yol}")
    with open(yol, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    yer = yol.name

    platform = _zorunlu(d, "platform", yer)
    if platform not in ("tiktok", "youtube"):
        raise AyarHatasi(f"{yer}: platform 'tiktok' ya da 'youtube' olmalı")

    kd = _zorunlu(d, "kaynak", yer)
    tip = _zorunlu(kd, "tip", f"{yer} kaynak")
    if tip == "reddit":
        _zorunlu(kd, "subredditler", f"{yer} kaynak")
    elif tip == "uretim":
        _zorunlu(kd, "prompt", f"{yer} kaynak")
    else:
        raise AyarHatasi(f"{yer}: kaynak tipi 'reddit' ya da 'uretim' olmalı")
    if platform == "youtube" and tip != "uretim":
        raise AyarHatasi(f"{yer}: youtube kanalları sadece 'uretim' kaynağını destekler")
    kaynak = Kaynak(
        tip=tip,
        subredditler=list(kd.get("subredditler") or []),
        min=int(kd.get("min", 3000)),
        max=int(kd.get("max", 4000)),
        prompt=kok / kd["prompt"] if kd.get("prompt") else None,
        kelime=int(kd.get("kelime", 2500)),
    )

    sd = _zorunlu(d, "ses", yer)
    motor = _zorunlu(sd, "motor", f"{yer} ses")
    if motor not in ("edge", "kokoro"):
        raise AyarHatasi(f"{yer}: ses motoru 'edge' ya da 'kokoro' olmalı")
    if platform == "tiktok" and motor != "edge":
        raise AyarHatasi(f"{yer}: TikTok altyazısı kelime zamanı ister, ses motoru 'edge' olmalı")
    ses = Ses(motor=motor, ses=_zorunlu(sd, "ses", f"{yer} ses"),
              hiz=_hiz_dogrula(motor, sd.get("hiz", "+0%" if motor == "edge" else 1.0), yer))

    gorunurluk = _zorunlu(d, "gorunurluk", yer)
    gecerli = TIKTOK_GORUNURLUK if platform == "tiktok" else YOUTUBE_GORUNURLUK
    if gorunurluk not in gecerli:
        raise AyarHatasi(f"{yer}: gorunurluk şunlardan biri olmalı: {sorted(gecerli)}")

    ed = d.get("etiketler") or {}
    kanal = Kanal(
        ad=ad,
        platform=platform,
        kaynak=kaynak,
        ses=ses,
        arka_plan=kok / _zorunlu(d, "arka_plan", yer),
        gorunurluk=gorunurluk,
        etiketler=Etiketler(sabit=list(ed.get("sabit") or []), llm_ekle=int(ed.get("llm_ekle", 0))),
    )

    if platform == "tiktok":
        kanal.profil = _zorunlu(d, "profil", yer)
        kanal.parca2_gecikme_dk = int(d.get("parca2_gecikme_dk", 120))
        kanal.parca2_yontem = d.get("parca2_yontem", "tiktok_zamanla")
        if kanal.parca2_yontem not in PARCA2_YONTEMLERI:
            raise AyarHatasi(f"{yer}: parca2_yontem şunlardan biri olmalı: {sorted(PARCA2_YONTEMLERI)}")
        if kanal.parca2_yontem == "tiktok_zamanla" and not 15 <= kanal.parca2_gecikme_dk <= 14400:
            raise AyarHatasi(f"{yer}: parca2_gecikme_dk TikTok zamanlaması için 15-14400 dk arası olmalı")
        if kanal.parca2_yontem == "tiktok_zamanla" and gorunurluk == "sadece_ben":
            raise AyarHatasi(f"{yer}: TikTok gizli videoları zamanlayamaz; sadece_ben ile parca2_yontem: bekle kullan")
        kanal.arka_plan_kredi = (d.get("arka_plan_kredi") or "").strip() or None
        yd = d.get("yorum") or {}
        kanal.yorum_aktif = bool(yd.get("aktif", False))
        kanal.yorum_en_fazla = int(yd.get("en_fazla", 10))
        kanal.yorum_hesap = (str(yd.get("hesap") or "").strip().lstrip("@").lower()) or None
        if kanal.yorum_aktif:
            if not 1 <= kanal.yorum_en_fazla <= 50:
                raise AyarHatasi(f"{yer}: yorum.en_fazla 1-50 arası olmalı")
            if not kanal.yorum_hesap:
                raise AyarHatasi(f"{yer}: yorum.hesap (kanalın TikTok kullanıcı adı) zorunlu")
    else:
        kanal.token = _zorunlu(d, "token", yer)
        kanal.tekrar = int(d.get("tekrar", 5))
        kanal.tekrar_arasi_sn = float(d.get("tekrar_arasi_sn", 8))
        kanal.hedef_sure_dk = float(d.get("hedef_sure_dk", 90))
        od = _zorunlu(d, "ortam_sesi", yer)
        kanal.ortam_sesi = kok / _zorunlu(od, "dosya", f"{yer} ortam_sesi")
        kanal.ortam_seviye = float(od.get("seviye", 0.25))
        kanal.kategori = str(d.get("kategori", "22"))
    return kanal


def ortami_yukle(kok: Path = KOK) -> None:
    load_dotenv(kok / ".env", override=False)


def ortam(anahtar: str, zorunlu: bool = True) -> str | None:
    deger = os.getenv(anahtar)
    if zorunlu and not deger:
        raise AyarHatasi(f".env içinde '{anahtar}' tanımlı değil")
    return deger


def db_yolu(kok: Path = KOK) -> Path:
    return kok / "veri" / "fabrika.db"


def profil_yolu(kanal: Kanal, kok: Path = KOK) -> Path:
    return kok / "profiller" / kanal.profil


def token_yolu(kanal: Kanal, kok: Path = KOK) -> Path:
    return kok / "veri" / "tokenlar" / f"{kanal.token}.json"


def eski_token_yolu(kanal: Kanal, kok: Path = KOK) -> Path:
    return kok / "veri" / "tokenlar" / f"{kanal.token}.pickle"


def client_secret_yolu(kok: Path = KOK) -> Path:
    return kok / "client_secret.json"


def cikti_klasoru(kanal: Kanal | str, is_id: int, kok: Path = KOK) -> Path:
    ad = kanal if isinstance(kanal, str) else kanal.ad
    return kok / "cikti" / ad / f"is_{is_id}"


def calisma_kilidi_yolu(kanal: Kanal | str, kok: Path = KOK) -> Path:
    ad = kanal if isinstance(kanal, str) else kanal.ad
    return kok / "veri" / f"{ad}.calisma.kilit"


def kilit_yolu(kok: Path = KOK) -> Path:
    return kok / "veri" / "tiktok.kilit"


def hata_klasoru(kok: Path = KOK) -> Path:
    return kok / "cikti" / "hatalar"
