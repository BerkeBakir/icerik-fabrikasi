# İçerik Fabrikası Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Tikok-Otomasyon` ve `Youtube-Otomasyon-GoogleTTS` repolarını, kanal başına yaml ile yönetilen, yeniden başlatılabilir, ücretsiz araçlarla çalışan tek bir Python projesinde (`icerik-fabrikasi`) birleştirmek.

**Architecture:** `calistir.py <kanal>` bir kanal yaml'ını okur, SQLite'taki yarım işi bulur ya da yeni iş açar ve `hikaye → senaryo → ses → video → yükleme` adımlarını sırayla, her adımın çıktısını DB'ye yazarak yürütür. Dış servisler (Gemini, Reddit RSS, Edge-TTS/Kokoro, ffmpeg, Playwright/TikTok, YouTube API) `core/` altında küçük, bağımlılıkları enjekte edilebilen modüllerdir; iş akışı testleri sahte nesnelerle çalışır.

**Tech Stack:** Python 3.11, google-genai (Gemini), edge-tts, kokoro + soundfile, ffmpeg/ffprobe (PATH'te), Playwright (sistem Chrome'u), google-api-python-client, SQLite, PyYAML, python-dotenv, pytest.

**Spec:** `docs/superpowers/specs/2026-09-29-icerik-fabrikasi-design.md`

## Global Constraints

- Proje kökü: `D:\Claude Code\icerik-fabrikasi`. Sanal ortam: `.venv` (Python 3.11.9, zaten oluşturuldu). Tüm komutlar kökten, `.venv/Scripts/python.exe` ile çalıştırılır. Aşağıda `PY` = `.venv/Scripts/python.exe`.
- Tamamen ücretsiz: ücretli API yok. LLM = Gemini (`GEMINI_MODEL` env, varsayılan `gemini-2.5-flash`).
- Reddit: sadece anahtarsız RSS (`https://www.reddit.com/r/<sub>/top/.rss?t=<week|month>&limit=50`), tarayıcı user-agent'ı, istekler arası ≥25 sn.
- TikTok ses motoru her zaman `edge` (kelime zamanları gerekli). YouTube varsayılanı `kokoro`, hata olursa Edge-TTS'e düşer.
- TikTok Part 2 gecikmesi varsayılan **120 dk**; `tiktok_zamanla` yönteminde 15 dk – 10 gün (14400 dk) sınırı.
- YouTube: `hedef_sure_dk` 90, `tekrar` 5, `tekrar_arasi_sn` 8, son 30 sn fade-out, kategori varsayılan `"22"`, varsayılan görünürlük ilk hafta `private`.
- Otomasyon asla şifre girmez; TikTok girişi kullanıcı tarafından `--giris` ile elle yapılır.
- Gizli/üretilen dosyalar git dışı: `.env`, `client_secret*.json`, `profiller/`, `veri/`, `cikti/`, `assets/`, `*.mp3 *.mp4 *.wav` (`.gitignore` zaten var).
- Log ve konsol metinlerinde emoji yok (Windows konsolu); Telegram mesajlarında serbest.
- Kod dili: tanımlayıcılar ve mesajlar Türkçe (ASCII dışı harf yok: `ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c` tanımlayıcılarda; metin/mesaj içinde Türkçe karakter serbest).
- Her görev sonunda: `PY -m pytest -q` tamamı yeşil, sonra commit.

## Dosya haritası

```
icerik-fabrikasi/
  requirements.txt  pytest.ini  README.md
  calistir.py                 CLI: <kanal> [--kuru] [--giris] | --ses-ornekleri
  zamanla.py                  Windows Görev Zamanlayıcı kayıt/silme
  tasima.py                   eski repolardan tek seferlik taşıma
  kanallar/tiktok_hikaye1.yaml  kanallar/ornek_tiktok_korku.yaml  kanallar/youtube_slumberlab.yaml
  prompts/korku.txt  prompts/uyku_hikayesi.txt
  core/
    __init__.py
    ayar.py          Kanal dataclass'ları, kanal_yukle, ortam, yol yardımcıları
    medya.py         ffmpeg/ffprobe sarmalayıcı
    db.py            SQLite: hikayeler, isler; ADIMLAR; Is
    kilit.py         dosya kilidi (tek TikTok yüklemesi)
    tekrar.py        tekrar_dene
    bildirim.py      Telegram
    gunluk.py        logger kurulumu
    modeller.py      Hikaye, TiktokSenaryo, YoutubePaketi
    llm.py           Gemini.json_uret
    senaryo.py       şemalar, prompt'lar, etiket yardımcıları
    kaynak/__init__.py  kaynak_olustur
    kaynak/reddit.py    RSS kaynağı
    kaynak/uretim.py    LLM kaynağı
    tts/__init__.py     Kelime, SesSonucu, TTSHatasi, motor_olustur, YedekliTTS
    tts/edge.py  tts/kokoro.py
    render/__init__.py
    render/altyazi.py      .ass üretimi
    render/tiktok_dikey.py
    render/youtube_uyku.py
    upload/__init__.py
    upload/youtube.py
    upload/tiktok_secici.py
    upload/tiktok.py
    onkontrol.py
    is_akisi.py      Baglam, calistir (tiktok/youtube akışları)
    ses_ornekleri.py
  tests/  (her modül için test_*.py)
```

---

### Task 1: Proje iskeleti, ayar ve medya yardımcıları

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `core/__init__.py`, `core/ayar.py`, `core/medya.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_ayar.py`, `tests/test_medya.py`

**Interfaces:**
- Produces:
  - `core.ayar`: `KOK: Path`, `AyarHatasi`, dataclass'lar `Ses(motor, ses, hiz)`, `Kaynak(tip, subredditler, min, max, prompt, kelime)`, `Etiketler(sabit, llm_ekle)`, `Kanal(...)` (alanlar aşağıdaki kodda), `kanal_yukle(ad, kok=KOK) -> Kanal`, `ortami_yukle(kok=KOK)`, `ortam(anahtar, zorunlu=True) -> str|None`, `db_yolu(kok)`, `profil_yolu(kanal, kok)`, `token_yolu(kanal, kok)`, `eski_token_yolu(kanal, kok)`, `client_secret_yolu(kok)`, `cikti_klasoru(kanal, is_id, kok)`, `kilit_yolu(kok)`, `hata_klasoru(kok)`
  - `core.medya`: `MedyaHatasi`, `ffmpeg(args: list, cwd: Path|None=None) -> None`, `sure(yol) -> float`, `araclar_var_mi() -> bool`

- [ ] **Step 1: Bağımlılık ve pytest dosyaları**

`requirements.txt`:
```
edge-tts>=7.2
google-genai>=2.0
python-dotenv>=1.0
PyYAML>=6.0
requests>=2.31
playwright>=1.50
google-api-python-client>=2.100
google-auth-oauthlib>=1.2
numpy>=1.26
soundfile>=0.12
kokoro>=0.9.4
pytest>=8
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
markers =
    ffmpeg: ffmpeg/ffprobe gerektirir
```

`core/__init__.py` ve `tests/__init__.py`: boş dosya.

`tests/conftest.py`:
```python
import shutil

import pytest


def pytest_collection_modifyitems(config, items):
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    atla = pytest.mark.skip(reason="ffmpeg/ffprobe PATH'te yok")
    for item in items:
        if "ffmpeg" in item.keywords:
            item.add_marker(atla)
```

Kur: `PY -m pip install -r requirements.txt` (kokoro torch indirir, birkaç dakika sürebilir). Ardından `PY -m playwright install chromium` (Chrome yoksa yedek).

- [ ] **Step 2: Başarısız testleri yaz**

`tests/test_ayar.py`:
```python
import textwrap

import pytest

from core.ayar import AyarHatasi, kanal_yukle, profil_yolu, token_yolu


def yaz(kok, ad, metin):
    (kok / "kanallar").mkdir(exist_ok=True)
    (kok / "kanallar" / f"{ad}.yaml").write_text(textwrap.dedent(metin), encoding="utf-8")


TIKTOK = """
platform: tiktok
profil: hikaye1
kaynak: {tip: reddit, subredditler: [AmItheAsshole], min: 3000, max: 4000}
ses: {motor: edge, ses: en-US-AndrewMultilingualNeural, hiz: "+10%"}
arka_plan: assets/arka_plan/orbital.mp4
etiketler: {sabit: [storytime, reddit], llm_ekle: 3}
gorunurluk: herkes
"""

YOUTUBE = """
platform: youtube
token: slumberlab
kaynak: {tip: uretim, prompt: prompts/uyku_hikayesi.txt, kelime: 2500}
ses: {motor: kokoro, ses: af_heart, hiz: 0.85}
arka_plan: assets/arka_plan/gece.mp4
ortam_sesi: {dosya: assets/yagmur.mp3, seviye: 0.3}
gorunurluk: private
"""


def test_tiktok_kanali_varsayilanlarla_yuklenir(tmp_path):
    yaz(tmp_path, "t1", TIKTOK)
    k = kanal_yukle("t1", kok=tmp_path)
    assert k.platform == "tiktok"
    assert k.kaynak.subredditler == ["AmItheAsshole"]
    assert k.ses.hiz == "+10%"
    assert k.arka_plan == tmp_path / "assets/arka_plan/orbital.mp4"
    assert k.etiketler.sabit == ["storytime", "reddit"]
    assert k.etiketler.llm_ekle == 3
    assert k.parca2_gecikme_dk == 120
    assert k.parca2_yontem == "tiktok_zamanla"
    assert profil_yolu(k, tmp_path) == tmp_path / "profiller" / "hikaye1"


def test_youtube_kanali_yuklenir(tmp_path):
    yaz(tmp_path, "y1", YOUTUBE)
    k = kanal_yukle("y1", kok=tmp_path)
    assert k.kaynak.prompt == tmp_path / "prompts/uyku_hikayesi.txt"
    assert k.ses.hiz == 0.85
    assert k.tekrar == 5 and k.tekrar_arasi_sn == 8.0 and k.hedef_sure_dk == 90.0
    assert k.ortam_sesi == tmp_path / "assets/yagmur.mp3"
    assert k.ortam_seviye == 0.3
    assert k.kategori == "22"
    assert token_yolu(k, tmp_path) == tmp_path / "veri" / "tokenlar" / "slumberlab.json"


def test_mutlak_arka_plan_yolu_korunur(tmp_path):
    yaz(tmp_path, "t1", TIKTOK.replace("assets/arka_plan/orbital.mp4", "D:/medya/orbital.mp4"))
    k = kanal_yukle("t1", kok=tmp_path)
    assert str(k.arka_plan).replace("\\", "/") == "D:/medya/orbital.mp4"


@pytest.mark.parametrize(
    "eski,yeni,mesaj",
    [
        ("platform: tiktok", "platform: instagram", "platform"),
        ("motor: edge", "motor: kokoro", "edge"),
        ("gorunurluk: herkes", "gorunurluk: public", "gorunurluk"),
        ("tip: reddit, subredditler: [AmItheAsshole]", "tip: reddit, subredditler: []", "subredditler"),
        ("profil: hikaye1", "", "profil"),
    ],
)
def test_gecersiz_tiktok_ayarlari_reddedilir(tmp_path, eski, yeni, mesaj):
    yaz(tmp_path, "t1", TIKTOK.replace(eski, yeni))
    with pytest.raises(AyarHatasi, match=mesaj):
        kanal_yukle("t1", kok=tmp_path)


def test_gecikme_tiktok_sinirinda_olmali(tmp_path):
    yaz(tmp_path, "t1", TIKTOK + "parca2_gecikme_dk: 10\n")
    with pytest.raises(AyarHatasi, match="parca2_gecikme_dk"):
        kanal_yukle("t1", kok=tmp_path)


def test_youtube_reddit_kaynagini_reddeder(tmp_path):
    yaz(tmp_path, "y1", YOUTUBE.replace(
        "{tip: uretim, prompt: prompts/uyku_hikayesi.txt, kelime: 2500}",
        "{tip: reddit, subredditler: [x]}"))
    with pytest.raises(AyarHatasi, match="uretim"):
        kanal_yukle("y1", kok=tmp_path)


def test_olmayan_kanal(tmp_path):
    with pytest.raises(AyarHatasi, match="yok"):
        kanal_yukle("yok", kok=tmp_path)
```

`tests/test_medya.py`:
```python
import subprocess

import pytest

from core import medya


@pytest.mark.ffmpeg
def test_sure_okunur(tmp_path):
    yol = tmp_path / "bir.wav"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=1.5", yol])
    assert medya.sure(yol) == pytest.approx(1.5, abs=0.05)


@pytest.mark.ffmpeg
def test_ffmpeg_hatasi_mesajla_firlatir(tmp_path):
    with pytest.raises(medya.MedyaHatasi, match="ffmpeg"):
        medya.ffmpeg(["-i", tmp_path / "olmayan.mp4", tmp_path / "x.mp4"])


@pytest.mark.ffmpeg
def test_sure_bozuk_dosyada_hata(tmp_path):
    yol = tmp_path / "bozuk.mp3"
    yol.write_bytes(b"abc")
    with pytest.raises(medya.MedyaHatasi):
        medya.sure(yol)
```

- [ ] **Step 3: Testlerin başarısız olduğunu gör**

Run: `PY -m pytest tests/test_ayar.py tests/test_medya.py -q`
Expected: FAIL (`ModuleNotFoundError: core.ayar`)

- [ ] **Step 4: `core/ayar.py`**

```python
"""Kanal ayarlarını (kanallar/*.yaml) ve .env'i okur, doğrular."""
from __future__ import annotations

import os
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
              hiz=sd.get("hiz", "+0%" if motor == "edge" else 1.0))

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


def cikti_klasoru(kanal: Kanal, is_id: int, kok: Path = KOK) -> Path:
    return kok / "cikti" / kanal.ad / f"is_{is_id}"


def kilit_yolu(kok: Path = KOK) -> Path:
    return kok / "veri" / "tiktok.kilit"


def hata_klasoru(kok: Path = KOK) -> Path:
    return kok / "cikti" / "hatalar"
```

- [ ] **Step 5: `core/medya.py`**

```python
"""ffmpeg / ffprobe için ince sarmalayıcı."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class MedyaHatasi(Exception):
    pass


def ffmpeg(args: list, cwd: Path | None = None) -> None:
    komut = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    r = subprocess.run(komut, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise MedyaHatasi(f"ffmpeg hata kodu {r.returncode}: {r.stderr[-1500:]}")


def sure(yol) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(yol)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise MedyaHatasi(f"süre okunamadı: {yol}: {r.stderr[-500:]}") from None


def araclar_var_mi() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
```

- [ ] **Step 6: Testler geçsin**

Run: `PY -m pytest -q`
Expected: tümü PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini core tests
git commit -m "feat: proje iskeleti, kanal ayarlari ve medya yardimcilari"
```

---

### Task 2: Veritabanı ve dosya kilidi

**Files:**
- Create: `core/db.py`, `core/kilit.py`, `tests/test_db.py`, `tests/test_kilit.py`

**Interfaces:**
- Produces:
  - `core.db`: `ADIMLAR = ["yeni","hikaye_secildi","senaryo_hazir","ses_hazir","video_hazir","parca1_yuklendi","yuklendi"]`; `Is(id, kanal, durum, veri: dict, hata, deneme)` + `Is.gecti_mi(adim) -> bool`; `DB(yol)` metotları: `hikaye_kullanildi_mi(kimlik) -> bool`, `hikaye_isaretle(kimlik, kanal)`, `is_olustur(kanal) -> Is`, `yarim_is(kanal) -> Is|None`, `is_getir(is_id) -> Is`, `is_ilerlet(is_id, durum, **veri) -> Is`, `is_hata(is_id, mesaj, en_fazla=3) -> Is`
  - `core.kilit`: `KilitHatasi`, `dosya_kilidi(yol, bekle_sn=1800, eski_sn=7200, uyku=time.sleep)` (context manager)

- [ ] **Step 1: Başarısız testler**

`tests/test_db.py`:
```python
from core.db import DB


def test_hikaye_isaretleme(tmp_path):
    db = DB(tmp_path / "v" / "f.db")
    assert not db.hikaye_kullanildi_mi("reddit:abc")
    db.hikaye_isaretle("reddit:abc", "k1")
    db.hikaye_isaretle("reddit:abc", "k2")  # ikinci kez hata vermez
    assert db.hikaye_kullanildi_mi("reddit:abc")


def test_is_ilerler_ve_veri_birlesir(tmp_path):
    db = DB(tmp_path / "f.db")
    is_ = db.is_olustur("k1")
    assert is_.durum == "yeni" and is_.veri == {}
    db.is_ilerlet(is_.id, "hikaye_secildi", hikaye={"kimlik": "x"})
    is_ = db.is_ilerlet(is_.id, "senaryo_hazir", senaryo={"part1": "a"})
    assert is_.durum == "senaryo_hazir"
    assert is_.veri == {"hikaye": {"kimlik": "x"}, "senaryo": {"part1": "a"}}
    assert is_.gecti_mi("hikaye_secildi") and is_.gecti_mi("senaryo_hazir")
    assert not is_.gecti_mi("ses_hazir")


def test_yarim_is_bulunur_bitmis_is_bulunmaz(tmp_path):
    db = DB(tmp_path / "f.db")
    a = db.is_olustur("k1")
    assert db.yarim_is("k1").id == a.id
    assert db.yarim_is("k2") is None
    db.is_ilerlet(a.id, "yuklendi")
    assert db.yarim_is("k1") is None


def test_uc_hatadan_sonra_is_iptal(tmp_path):
    db = DB(tmp_path / "f.db")
    a = db.is_olustur("k1")
    db.is_hata(a.id, "bir")
    b = db.is_hata(a.id, "iki")
    assert b.durum == "yeni" and b.deneme == 2 and b.hata == "iki"
    c = db.is_hata(a.id, "uc")
    assert c.durum == "iptal"
    assert db.yarim_is("k1") is None


def test_basarili_ilerleme_hatayi_temizler(tmp_path):
    db = DB(tmp_path / "f.db")
    a = db.is_olustur("k1")
    db.is_hata(a.id, "gecici")
    b = db.is_ilerlet(a.id, "hikaye_secildi")
    assert b.hata is None and b.deneme == 1
```

`tests/test_kilit.py`:
```python
import os

import pytest

from core.kilit import KilitHatasi, dosya_kilidi


def test_kilit_alinir_ve_birakilir(tmp_path):
    yol = tmp_path / "k" / "a.kilit"
    with dosya_kilidi(yol):
        assert yol.exists()
    assert not yol.exists()


def test_dolu_kilit_zaman_asimi(tmp_path):
    yol = tmp_path / "a.kilit"
    yol.write_text("123")
    with pytest.raises(KilitHatasi):
        with dosya_kilidi(yol, bekle_sn=-1, uyku=lambda s: None):
            pass
    assert yol.exists()  # başkasının kilidine dokunulmaz


def test_eski_kilit_temizlenir(tmp_path):
    yol = tmp_path / "a.kilit"
    yol.write_text("123")
    os.utime(yol, (0, 0))
    with dosya_kilidi(yol, eski_sn=60):
        assert yol.read_text() == str(os.getpid())
```

- [ ] **Step 2: Başarısız olduğunu gör**

Run: `PY -m pytest tests/test_db.py tests/test_kilit.py -q` → FAIL (modül yok)

- [ ] **Step 3: `core/db.py`**

```python
"""SQLite: kullanılan hikâyeler ve yeniden başlatılabilir işler."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ADIMLAR = ["yeni", "hikaye_secildi", "senaryo_hazir", "ses_hazir", "video_hazir", "parca1_yuklendi", "yuklendi"]
BITMIS = ("yuklendi", "iptal")


def _simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Is:
    id: int
    kanal: str
    durum: str
    veri: dict
    hata: str | None
    deneme: int

    def gecti_mi(self, adim: str) -> bool:
        if self.durum not in ADIMLAR:
            return False
        return ADIMLAR.index(self.durum) >= ADIMLAR.index(adim)


class DB:
    def __init__(self, yol: Path):
        Path(yol).parent.mkdir(parents=True, exist_ok=True)
        self.bag = sqlite3.connect(str(yol))
        self.bag.row_factory = sqlite3.Row
        self.bag.executescript(
            """
            CREATE TABLE IF NOT EXISTS hikayeler (
                kimlik TEXT PRIMARY KEY, kanal TEXT NOT NULL, tarih TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS isler (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kanal TEXT NOT NULL, durum TEXT NOT NULL,
                veri TEXT NOT NULL, hata TEXT, deneme INTEGER NOT NULL DEFAULT 0,
                olusturma TEXT NOT NULL, guncelleme TEXT NOT NULL);
            """
        )
        self.bag.commit()

    def hikaye_kullanildi_mi(self, kimlik: str) -> bool:
        return self.bag.execute("SELECT 1 FROM hikayeler WHERE kimlik=?", (kimlik,)).fetchone() is not None

    def hikaye_isaretle(self, kimlik: str, kanal: str) -> None:
        self.bag.execute("INSERT OR IGNORE INTO hikayeler VALUES (?,?,?)", (kimlik, kanal, _simdi()))
        self.bag.commit()

    def _satir(self, r) -> Is:
        return Is(r["id"], r["kanal"], r["durum"], json.loads(r["veri"]), r["hata"], r["deneme"])

    def is_getir(self, is_id: int) -> Is:
        return self._satir(self.bag.execute("SELECT * FROM isler WHERE id=?", (is_id,)).fetchone())

    def is_olustur(self, kanal: str) -> Is:
        c = self.bag.execute(
            "INSERT INTO isler (kanal, durum, veri, olusturma, guncelleme) VALUES (?,?,?,?,?)",
            (kanal, "yeni", "{}", _simdi(), _simdi()),
        )
        self.bag.commit()
        return self.is_getir(c.lastrowid)

    def yarim_is(self, kanal: str) -> Is | None:
        r = self.bag.execute(
            f"SELECT * FROM isler WHERE kanal=? AND durum NOT IN ({','.join('?' * len(BITMIS))}) "
            "ORDER BY id DESC LIMIT 1",
            (kanal, *BITMIS),
        ).fetchone()
        return self._satir(r) if r else None

    def is_ilerlet(self, is_id: int, durum: str, **veri) -> Is:
        mevcut = self.is_getir(is_id)
        mevcut.veri.update(veri)
        self.bag.execute(
            "UPDATE isler SET durum=?, veri=?, hata=NULL, guncelleme=? WHERE id=?",
            (durum, json.dumps(mevcut.veri, ensure_ascii=False), _simdi(), is_id),
        )
        self.bag.commit()
        return self.is_getir(is_id)

    def is_hata(self, is_id: int, mesaj: str, en_fazla: int = 3) -> Is:
        mevcut = self.is_getir(is_id)
        deneme = mevcut.deneme + 1
        durum = "iptal" if deneme >= en_fazla else mevcut.durum
        self.bag.execute(
            "UPDATE isler SET durum=?, hata=?, deneme=?, guncelleme=? WHERE id=?",
            (durum, mesaj[:2000], deneme, _simdi(), is_id),
        )
        self.bag.commit()
        return self.is_getir(is_id)
```

- [ ] **Step 4: `core/kilit.py`**

```python
"""Basit dosya kilidi: aynı anda tek TikTok yüklemesi."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path


class KilitHatasi(Exception):
    pass


@contextmanager
def dosya_kilidi(yol: Path, bekle_sn: float = 1800, eski_sn: float = 7200, uyku=time.sleep):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    baslangic = time.time()
    while True:
        try:
            fd = os.open(yol, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                yas = time.time() - yol.stat().st_mtime
            except FileNotFoundError:
                continue
            if yas > eski_sn:
                yol.unlink(missing_ok=True)
                continue
            if time.time() - baslangic > bekle_sn:
                raise KilitHatasi(f"Kilit boşalmadı: {yol}")
            uyku(10)
    try:
        yield
    finally:
        yol.unlink(missing_ok=True)
```

- [ ] **Step 5: Testler geçsin** — Run: `PY -m pytest -q` → PASS

- [ ] **Step 6: Commit**

```bash
git add core/db.py core/kilit.py tests/test_db.py tests/test_kilit.py
git commit -m "feat: SQLite is durumu ve dosya kilidi"
```

---

### Task 3: Tekrar deneme, Telegram bildirimi, log

**Files:**
- Create: `core/tekrar.py`, `core/bildirim.py`, `core/gunluk.py`, `tests/test_tekrar.py`, `tests/test_bildirim.py`

**Interfaces:**
- Produces:
  - `core.tekrar.tekrar_dene(fn, *, deneme=3, bekleme=2.0, carpan=2.0, hatalar=(Exception,), uyku=time.sleep, log=None)` — `fn()` sonucunu döner, son denemede hatayı yeniden fırlatır.
  - `core.bildirim.Bildirim(token, chat_id, log=None, oturum=None)` → `.mesaj(metin)`, `.foto(yol, aciklama)`; asla hata fırlatmaz.
  - `core.gunluk.kur(kanal: str, kok=KOK) -> logging.Logger`

- [ ] **Step 1: Başarısız testler**

`tests/test_tekrar.py`:
```python
import pytest

from core.tekrar import tekrar_dene


def test_ikinci_denemede_basarir():
    cagri = {"n": 0}
    beklemeler = []

    def fn():
        cagri["n"] += 1
        if cagri["n"] < 2:
            raise ValueError("gecici")
        return "tamam"

    assert tekrar_dene(fn, deneme=3, bekleme=5, uyku=beklemeler.append) == "tamam"
    assert beklemeler == [5]


def test_ussel_bekleme_ve_son_hata():
    beklemeler = []

    def fn():
        raise ValueError("hep")

    with pytest.raises(ValueError, match="hep"):
        tekrar_dene(fn, deneme=3, bekleme=2, carpan=3, uyku=beklemeler.append)
    assert beklemeler == [2, 6]


def test_listede_olmayan_hata_hemen_firlar():
    beklemeler = []

    def fn():
        raise KeyError("x")

    with pytest.raises(KeyError):
        tekrar_dene(fn, deneme=3, hatalar=(ValueError,), uyku=beklemeler.append)
    assert beklemeler == []
```

`tests/test_bildirim.py`:
```python
from core.bildirim import Bildirim


class SahteOturum:
    def __init__(self, patla=False):
        self.cagrilar = []
        self.patla = patla

    def post(self, url, **kw):
        self.cagrilar.append((url, kw))
        if self.patla:
            raise ConnectionError("ag yok")


def test_mesaj_gonderilir():
    o = SahteOturum()
    Bildirim("TOK", "42", oturum=o).mesaj("merhaba")
    url, kw = o.cagrilar[0]
    assert url == "https://api.telegram.org/botTOK/sendMessage"
    assert kw["data"] == {"chat_id": "42", "text": "merhaba"}


def test_token_yoksa_sessiz():
    o = SahteOturum()
    Bildirim(None, "42", oturum=o).mesaj("x")
    assert o.cagrilar == []


def test_ag_hatasi_yutulur():
    Bildirim("T", "1", oturum=SahteOturum(patla=True)).mesaj("x")


def test_foto_basarisizsa_mesaja_duser(tmp_path):
    o = SahteOturum(patla=True)
    Bildirim("T", "1", oturum=o).foto(tmp_path / "yok.png", "hata oldu")
    assert o.cagrilar[-1][0].endswith("/sendMessage")
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_tekrar.py tests/test_bildirim.py -q` → FAIL

- [ ] **Step 3: `core/tekrar.py`**

```python
from __future__ import annotations

import time


def tekrar_dene(fn, *, deneme: int = 3, bekleme: float = 2.0, carpan: float = 2.0,
                hatalar: tuple = (Exception,), uyku=time.sleep, log=None):
    for i in range(deneme):
        try:
            return fn()
        except hatalar as e:
            if i == deneme - 1:
                raise
            sure = bekleme * carpan ** i
            if log:
                log.warning("Deneme %d/%d başarısız (%s), %.0f sn sonra tekrar", i + 1, deneme, e, sure)
            uyku(sure)
```

- [ ] **Step 4: `core/bildirim.py`**

```python
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

    def mesaj(self, metin: str) -> None:
        if not self._aktif():
            return
        try:
            self.oturum.post(API.format(token=self.token, metot="sendMessage"),
                             data={"chat_id": self.chat_id, "text": metin[:4000]}, timeout=15)
        except Exception as e:  # bildirim asla işi durdurmaz
            self.log.warning("Telegram mesajı gönderilemedi: %s", e)

    def foto(self, yol, aciklama: str) -> None:
        if not self._aktif():
            return
        try:
            with open(yol, "rb") as f:
                self.oturum.post(API.format(token=self.token, metot="sendPhoto"),
                                 data={"chat_id": self.chat_id, "caption": aciklama[:1000]},
                                 files={"photo": f}, timeout=30)
        except Exception as e:
            self.log.warning("Telegram fotoğrafı gönderilemedi: %s", e)
            self.mesaj(aciklama)
```

- [ ] **Step 5: `core/gunluk.py`**

```python
from __future__ import annotations

import logging
import sys
from pathlib import Path

from core.ayar import KOK


def kur(kanal: str, kok: Path = KOK) -> logging.Logger:
    log = logging.getLogger(f"fabrika.{kanal}")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    bicim = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    klasor = kok / "veri" / "log"
    klasor.mkdir(parents=True, exist_ok=True)
    dosya = logging.FileHandler(klasor / f"{kanal}.log", encoding="utf-8")
    dosya.setFormatter(bicim)
    konsol = logging.StreamHandler(sys.stdout)
    konsol.setFormatter(bicim)
    log.addHandler(dosya)
    log.addHandler(konsol)
    return log
```

- [ ] **Step 6: Testler geçsin** — `PY -m pytest -q` → PASS

- [ ] **Step 7: Commit**

```bash
git add core/tekrar.py core/bildirim.py core/gunluk.py tests/test_tekrar.py tests/test_bildirim.py
git commit -m "feat: tekrar deneme, Telegram bildirimi ve log"
```

---

### Task 4: Modeller, Gemini istemcisi ve senaryo üretimi

**Files:**
- Create: `core/modeller.py`, `core/llm.py`, `core/senaryo.py`, `tests/test_llm.py`, `tests/test_senaryo.py`

**Interfaces:**
- Consumes: `core.tekrar.tekrar_dene`
- Produces:
  - `core.modeller`: `Hikaye(kimlik, baslik, govde)`, `TiktokSenaryo(hook, part1, part2, aciklama, etiketler: list[str])`, `YoutubePaketi(baslik, aciklama, etiketler: list[str], hikaye)` — hepsi `@dataclass`, `asdict` ile DB'ye yazılır, `Sinif(**sozluk)` ile geri okunur.
  - `core.llm`: `LLMHatasi`, `Gemini(api_key, model="gemini-2.5-flash", istemci=None, log=None, uyku=time.sleep)` → `.json_uret(prompt: str, sema: dict, sicaklik=0.8) -> dict`
  - `core.senaryo`: `PART1_SON`, `etiket_temizle(e) -> str`, `etiketleri_birlestir(sabit, llm, llm_ekle) -> list[str]`, `tiktok_aciklama(parca: int, aciklama: str) -> str`, `tiktok_senaryo(llm, hikaye, etiket_sayisi) -> TiktokSenaryo`, `serbest_hikaye(llm, prompt_metni) -> Hikaye`, `youtube_paketi(llm, prompt_metni, kelime, log=None) -> YoutubePaketi`

- [ ] **Step 1: Başarısız testler**

`tests/test_llm.py`:
```python
import pytest

from core.llm import Gemini, LLMHatasi


class Yanit:
    def __init__(self, text):
        self.text = text


class SahteModeller:
    def __init__(self, cevaplar):
        self.cevaplar = list(cevaplar)
        self.cagrilar = []

    def generate_content(self, model, contents, config):
        self.cagrilar.append((model, contents, config))
        return Yanit(self.cevaplar.pop(0))


class SahteIstemci:
    def __init__(self, cevaplar):
        self.models = SahteModeller(cevaplar)


SEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def test_json_doner_ve_sema_iletilir():
    ist = SahteIstemci(['{"a": "b"}'])
    g = Gemini("k", model="m1", istemci=ist)
    assert g.json_uret("p", SEMA) == {"a": "b"}
    model, contents, config = ist.models.cagrilar[0]
    assert model == "m1" and contents == "p"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == SEMA


def test_gecersiz_json_tekrar_denenir():
    ist = SahteIstemci(["bozuk", '{"a": "b"}'])
    g = Gemini("k", istemci=ist, uyku=lambda s: None)
    assert g.json_uret("p", SEMA) == {"a": "b"}


def test_eksik_alan_uc_denemeden_sonra_hata():
    ist = SahteIstemci(['{"a": ""}'] * 3)
    g = Gemini("k", istemci=ist, uyku=lambda s: None)
    with pytest.raises(LLMHatasi, match="eksik"):
        g.json_uret("p", SEMA)
```

`tests/test_senaryo.py`:
```python
from core.modeller import Hikaye
from core.senaryo import (PART1_SON, etiket_temizle, etiketleri_birlestir, serbest_hikaye,
                          tiktok_aciklama, tiktok_senaryo, youtube_paketi)


class SahteLLM:
    def __init__(self, cevap):
        self.cevap = cevap
        self.promptlar = []

    def json_uret(self, prompt, sema, sicaklik=0.8):
        self.promptlar.append(prompt)
        return dict(self.cevap)


def test_etiket_temizle():
    assert etiket_temizle("#Story Time!") == "storytime"
    assert etiket_temizle("  #") == ""
    assert etiket_temizle("çocuk_hikaye") == "çocuk_hikaye"


def test_etiketleri_birlestir_sabit_once_tekrarsiz():
    sonuc = etiketleri_birlestir(["storytime", "Reddit"], ["#reddit", "drama", "aita", "family"], 2)
    assert sonuc == ["storytime", "reddit", "drama", "aita"]


def test_tiktok_aciklama_etiketleri_siler():
    assert tiktok_aciklama(1, "Crazy story #fyp #x") == "PART 1 | Crazy story"
    assert tiktok_aciklama(2, "Crazy story").startswith("PART 2 (Final) | ")


def test_tiktok_senaryo_hook_ve_son_cumleyi_garantiler():
    llm = SahteLLM({"hook": "You won't believe this.", "part1": "It started on Monday.",
                    "part2": "In the end he left.", "aciklama": "desc", "etiketler": ["#Drama", "aita"]})
    s = tiktok_senaryo(llm, Hikaye("reddit:1", "Baslik", "Govde {x}"), etiket_sayisi=3)
    assert s.part1.startswith("You won't believe this.")
    assert s.part1.endswith(PART1_SON)
    assert s.etiketler == ["drama", "aita"]
    assert "Govde {x}" in llm.promptlar[0]
    assert "3" in llm.promptlar[0]


def test_tiktok_senaryo_zaten_dogruysa_ekleme_yapmaz():
    p1 = f"You won't believe this. It started. {PART1_SON}"
    llm = SahteLLM({"hook": "You won't believe this.", "part1": p1, "part2": "x",
                    "aciklama": "d", "etiketler": []})
    assert tiktok_senaryo(llm, Hikaye("a", "b", "c"), 0).part1 == p1


def test_serbest_hikaye_kimligi_icerige_bagli():
    llm = SahteLLM({"baslik": "The Door", "govde": "Once upon a time."})
    h1 = serbest_hikaye(llm, "Write horror")
    h2 = serbest_hikaye(llm, "Write horror")
    assert h1.kimlik == h2.kimlik and h1.kimlik.startswith("uretim:")
    assert h1.baslik == "The Door"


def test_youtube_paketi_kelime_sayisini_prompta_koyar():
    llm = SahteLLM({"baslik": "Rainy Cabin", "aciklama": "d", "etiketler": ["#sleep", "rain"],
                    "hikaye": "word " * 100})
    p = youtube_paketi(llm, "Write a {kelime} word sleep story", 2500)
    assert "2500" in llm.promptlar[0]
    assert p.etiketler == ["sleep", "rain"]
    assert p.baslik == "Rainy Cabin"
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_llm.py tests/test_senaryo.py -q` → FAIL

- [ ] **Step 3: `core/modeller.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Hikaye:
    kimlik: str
    baslik: str
    govde: str


@dataclass
class TiktokSenaryo:
    hook: str
    part1: str
    part2: str
    aciklama: str
    etiketler: list[str] = field(default_factory=list)


@dataclass
class YoutubePaketi:
    baslik: str
    aciklama: str
    etiketler: list[str]
    hikaye: str
```

- [ ] **Step 4: `core/llm.py`**

```python
"""Gemini ile şemaya uygun JSON üretimi."""
from __future__ import annotations

import json
import logging
import time

from google import genai
from google.genai import types

from core.tekrar import tekrar_dene


class LLMHatasi(Exception):
    pass


class Gemini:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", istemci=None,
                 log: logging.Logger | None = None, uyku=time.sleep):
        self.model = model
        self.istemci = istemci or genai.Client(api_key=api_key)
        self.log = log or logging.getLogger(__name__)
        self.uyku = uyku

    def json_uret(self, prompt: str, sema: dict, sicaklik: float = 0.8) -> dict:
        def bir_deneme() -> dict:
            yanit = self.istemci.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=sema,
                    temperature=sicaklik,
                ),
            )
            metin = (yanit.text or "").strip()
            try:
                veri = json.loads(metin)
            except json.JSONDecodeError as e:
                raise LLMHatasi(f"geçersiz JSON: {metin[:200]}") from e
            eksik = [k for k in sema.get("required", []) if not veri.get(k)]
            if eksik:
                raise LLMHatasi(f"eksik alanlar: {eksik}")
            return veri

        return tekrar_dene(bir_deneme, deneme=3, bekleme=10, uyku=self.uyku, log=self.log)
```

- [ ] **Step 5: `core/senaryo.py`**

```python
"""LLM prompt'ları, JSON şemaları ve etiket yardımcıları."""
from __future__ import annotations

import hashlib
import logging
import re

from core.modeller import Hikaye, TiktokSenaryo, YoutubePaketi

PART1_SON = "Follow for Part 2, it's already on my profile!"

_METIN = {"type": "string"}
_LISTE = {"type": "array", "items": {"type": "string"}}

TIKTOK_SEMA = {
    "type": "object",
    "properties": {"hook": _METIN, "part1": _METIN, "part2": _METIN, "aciklama": _METIN, "etiketler": _LISTE},
    "required": ["hook", "part1", "part2", "aciklama", "etiketler"],
}
SERBEST_SEMA = {
    "type": "object",
    "properties": {"baslik": _METIN, "govde": _METIN},
    "required": ["baslik", "govde"],
}
YOUTUBE_SEMA = {
    "type": "object",
    "properties": {"baslik": _METIN, "aciklama": _METIN, "etiketler": _LISTE, "hikaye": _METIN},
    "required": ["baslik", "aciklama", "etiketler", "hikaye"],
}

TIKTOK_PROMPT = """Prepare this story for a high-quality, long-form TikTok video split into two parts.

STRICT INSTRUCTIONS:
1. DO NOT SUMMARIZE: keep the emotional depth, the crucial dialogue and the specific details.
2. "hook": one viral opening sentence (3-5 seconds when spoken) that grabs attention immediately.
3. "part1": starts with the hook sentence, tells the first half, and stops on a cliffhanger. It MUST end exactly with: "{part1_son}"
4. "part2": starts with a one-sentence recap, then the second half, the resolution and a short closing thought.
5. Tone: immersive, dramatic, first-person storytelling. Plain spoken English, no emojis, no hashtags, no stage directions.
6. "aciklama": an engaging one or two sentence TikTok caption WITHOUT hashtags.
7. "etiketler": exactly {etiket_sayisi} relevant TikTok hashtags for this specific story, without the # sign.

TITLE: {baslik}
STORY:
{govde}
"""

SERBEST_EK = """

Respond as JSON: "baslik" is a short title, "govde" is the complete story text in plain English with paragraphs separated by blank lines. No emojis, no hashtags."""

YOUTUBE_EK = """

Respond as JSON:
- "baslik": a calm, catchy YouTube title (max 70 characters, no quotes, no emojis)
- "aciklama": a 3-paragraph SEO description
- "etiketler": 10-15 relevant tags without the # sign
- "hikaye": the full story text, paragraphs separated by blank lines, no headings, no markdown"""


def etiket_temizle(e: str) -> str:
    return re.sub(r"[^\w]", "", e.strip().lstrip("#")).lower()


def etiketleri_birlestir(sabit: list[str], llm: list[str], llm_ekle: int) -> list[str]:
    sonuc: list[str] = []
    for e in sabit:
        t = etiket_temizle(e)
        if t and t not in sonuc:
            sonuc.append(t)
    eklenen = 0
    for e in llm:
        if eklenen >= llm_ekle:
            break
        t = etiket_temizle(e)
        if t and t not in sonuc:
            sonuc.append(t)
            eklenen += 1
    return sonuc


def tiktok_aciklama(parca: int, aciklama: str) -> str:
    temiz = re.sub(r"\s+", " ", re.sub(r"#\w+", "", aciklama)).strip()
    on_ek = "PART 1 | " if parca == 1 else "PART 2 (Final) | "
    return (on_ek + temiz)[:2000]


def tiktok_senaryo(llm, hikaye: Hikaye, etiket_sayisi: int) -> TiktokSenaryo:
    prompt = TIKTOK_PROMPT.format(part1_son=PART1_SON, etiket_sayisi=etiket_sayisi,
                                  baslik=hikaye.baslik, govde=hikaye.govde)
    v = llm.json_uret(prompt, TIKTOK_SEMA, sicaklik=0.7)
    hook = v["hook"].strip()
    part1 = v["part1"].strip()
    if not part1.lower().startswith(hook.lower()[:30]):
        part1 = f"{hook} {part1}"
    if not part1.endswith(PART1_SON):
        part1 = f"{part1} {PART1_SON}"
    etiketler = [t for t in (etiket_temizle(e) for e in v["etiketler"]) if t]
    return TiktokSenaryo(hook, part1, v["part2"].strip(), v["aciklama"].strip(), etiketler)


def serbest_hikaye(llm, prompt_metni: str) -> Hikaye:
    v = llm.json_uret(prompt_metni + SERBEST_EK, SERBEST_SEMA, sicaklik=0.9)
    govde = v["govde"].strip()
    kimlik = "uretim:" + hashlib.sha1(govde.encode("utf-8")).hexdigest()[:12]
    return Hikaye(kimlik, v["baslik"].strip(), govde)


def youtube_paketi(llm, prompt_metni: str, kelime: int, log: logging.Logger | None = None) -> YoutubePaketi:
    prompt = prompt_metni.replace("{kelime}", str(kelime)) + YOUTUBE_EK
    v = llm.json_uret(prompt, YOUTUBE_SEMA, sicaklik=0.9)
    hikaye = v["hikaye"].replace("**", "").strip()
    sayi = len(hikaye.split())
    if log and sayi < kelime * 0.6:
        log.warning("Hikâye kısa geldi: %d kelime (hedef %d)", sayi, kelime)
    baslik = re.sub(r'["*]', "", v["baslik"]).strip()
    etiketler = [t for t in (etiket_temizle(e) for e in v["etiketler"]) if t]
    return YoutubePaketi(baslik, v["aciklama"].strip(), etiketler, hikaye)
```

- [ ] **Step 6: Testler geçsin** — `PY -m pytest -q` → PASS

- [ ] **Step 7: Gerçek Gemini duman testi (tek sefer, test dosyasına eklenmez)**

Run:
```bash
.venv/Scripts/python.exe -c "from core.ayar import ortami_yukle, ortam; ortami_yukle(); from core.llm import Gemini; print(Gemini(ortam('GEMINI_API_KEY')).json_uret('Say hi as JSON with key a', {'type':'object','properties':{'a':{'type':'string'}},'required':['a']}))"
```
Expected: `{'a': ...}` yazdırır. Hata alırsan (model adı/kota) sonucu rapora yaz; `GEMINI_MODEL` env ile değiştirilebilir olduğundan kod değişikliği gerekmez.

- [ ] **Step 8: Commit**

```bash
git add core/modeller.py core/llm.py core/senaryo.py tests/test_llm.py tests/test_senaryo.py
git commit -m "feat: Gemini JSON istemcisi ve senaryo uretimi"
```

---

### Task 5: İçerik kaynakları (Reddit RSS, LLM üretimi)

**Files:**
- Create: `core/kaynak/__init__.py`, `core/kaynak/reddit.py`, `core/kaynak/uretim.py`, `tests/test_kaynak.py`

**Interfaces:**
- Consumes: `core.modeller.Hikaye`, `core.db.DB.hikaye_kullanildi_mi`, `core.senaryo.serbest_hikaye`, `core.ayar.Kanal`
- Produces:
  - `core.kaynak.reddit`: `html_to_metin(h) -> str`, `metni_temizle(t) -> str`, `rss_ayristir(xml) -> list[Hikaye]`, `RedditKaynak(subredditler, min_k, max_k, db, oturum=None, uyku=time.sleep, bekleme=25, log=None)` → `.sec() -> Hikaye|None`
  - `core.kaynak.uretim.UretimKaynak(llm, prompt_yolu, db, log=None)` → `.sec() -> Hikaye|None`
  - `core.kaynak.kaynak_olustur(kanal, llm, db, log) -> RedditKaynak|UretimKaynak`

- [ ] **Step 1: Başarısız testler**

`tests/test_kaynak.py`:
```python
import html

from core.db import DB
from core.kaynak.reddit import RedditKaynak, html_to_metin, metni_temizle, rss_ayristir
from core.kaynak.uretim import UretimKaynak


def govde_html(paragraflar):
    """paragraflar: ham HTML parçaları (Reddit'in div.md içeriği gibi)."""
    ic = "".join(f"<p>{p}</p>" for p in paragraflar)
    return f'<!-- SC_OFF --><div class="md">{ic}</div><!-- SC_ON --> &#32; submitted by <a href="x">/u/a</a>'


def feed(girdiler):
    parcalar = []
    for kimlik, baslik, paragraflar in girdiler:
        parcalar.append(
            f"<entry><id>t3_{kimlik}</id><title>{html.escape(baslik)}</title>"
            f'<content type="html">{html.escape(govde_html(paragraflar))}</content></entry>'
        )
    return '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">' + "".join(parcalar) + "</feed>"


def test_html_to_metin_paragraflari_korur():
    h = govde_html(["First &amp; line.", "Second<br/>line."])
    assert html_to_metin(h) == "First & line.\n\nSecond\nline."


def test_govdesiz_gonderi_bos_doner():
    assert html_to_metin('<a href="x">[link]</a>') == ""


def test_metni_temizle_edit_ve_linkleri_atar():
    t = "Story here https://x.com/a ok.\n\nMore story.\n\nEDIT: thanks all\n\nlater"
    assert metni_temizle(t) == "Story here  ok.\n\nMore story."


def test_rss_ayristir():
    hs = rss_ayristir(feed([("abc", "AITA &amp; me?", ["Hello."])]))
    assert hs[0].kimlik == "reddit:abc"
    assert hs[0].govde == "Hello."


class Yanit:
    def __init__(self, kod, metin):
        self.status_code = kod
        self.text = metin


class SahteOturum:
    def __init__(self, cevaplar):
        self.cevaplar = cevaplar  # url parcasi -> [Yanit, ...]
        self.urller = []

    def get(self, url, headers=None, timeout=None):
        self.urller.append(url)
        assert "Mozilla" in headers["User-Agent"]
        for anahtar, liste in self.cevaplar.items():
            if anahtar in url:
                return liste.pop(0) if len(liste) > 1 else liste[0]
        return Yanit(404, "")


def test_uzunluk_ve_kullanilmis_filtresi(tmp_path):
    db = DB(tmp_path / "f.db")
    db.hikaye_isaretle("reddit:uygun1", "k")
    uzun = "a" * 3500
    o = SahteOturum({
        "r/A/top/.rss?t=week": [Yanit(200, feed([("kisa", "t", ["a" * 100]), ("uygun1", "t", [uzun]), ("uygun2", "t", [uzun])]))],
    })
    beklemeler = []
    h = RedditKaynak(["A"], 3000, 4000, db, oturum=o, uyku=beklemeler.append).sec()
    assert h.kimlik == "reddit:uygun2"
    assert beklemeler == []


def test_subredditler_arasi_bekler_ve_aya_gecer(tmp_path):
    db = DB(tmp_path / "f.db")
    bos = feed([("k", "t", ["kisa"])])
    o = SahteOturum({
        "r/A/top/.rss?t=week": [Yanit(200, bos)],
        "r/B/top/.rss?t=week": [Yanit(200, bos)],
        "r/A/top/.rss?t=month": [Yanit(200, feed([("ay", "t", ["b" * 3200])]))],
    })
    beklemeler = []
    h = RedditKaynak(["A", "B"], 3000, 4000, db, oturum=o, uyku=beklemeler.append, bekleme=25).sec()
    assert h.kimlik == "reddit:ay"
    assert beklemeler == [25, 25]


def test_429_da_bekleyip_bir_kez_tekrar_dener(tmp_path):
    db = DB(tmp_path / "f.db")
    o = SahteOturum({"r/A/top/.rss?t=week": [Yanit(429, ""), Yanit(200, feed([("x", "t", ["c" * 3100])]))]})
    beklemeler = []
    h = RedditKaynak(["A"], 3000, 4000, db, oturum=o, uyku=beklemeler.append).sec()
    assert h.kimlik == "reddit:x"
    assert beklemeler == [60]


def test_hic_uygun_yoksa_none(tmp_path):
    db = DB(tmp_path / "f.db")
    o = SahteOturum({"rss": [Yanit(200, feed([]))]})
    assert RedditKaynak(["A"], 3000, 4000, db, oturum=o, uyku=lambda s: None).sec() is None


class SahteLLM:
    def __init__(self, govdeler):
        self.govdeler = list(govdeler)

    def json_uret(self, prompt, sema, sicaklik=0.8):
        return {"baslik": "B", "govde": self.govdeler.pop(0)}


def test_uretim_kullanilmis_icerigi_tekrar_uretir(tmp_path):
    db = DB(tmp_path / "f.db")
    p = tmp_path / "p.txt"
    p.write_text("Write horror", encoding="utf-8")
    ilk = UretimKaynak(SahteLLM(["aynı"]), p, db).sec()
    db.hikaye_isaretle(ilk.kimlik, "k")
    ikinci = UretimKaynak(SahteLLM(["aynı", "farklı"]), p, db).sec()
    assert ikinci.govde == "farklı"
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_kaynak.py -q` → FAIL

- [ ] **Step 3: `core/kaynak/reddit.py`**

```python
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
    paragraflar = [re.sub(r"[ \t\u00a0]+", " ", p).strip() for p in re.split(r"\n\s*\n", h)]
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
```

- [ ] **Step 4: `core/kaynak/uretim.py`**

```python
from __future__ import annotations

import logging
from pathlib import Path

from core.modeller import Hikaye
from core.senaryo import serbest_hikaye


class UretimKaynak:
    def __init__(self, llm, prompt_yolu: Path, db, log: logging.Logger | None = None):
        self.llm = llm
        self.prompt_yolu = Path(prompt_yolu)
        self.db = db
        self.log = log or logging.getLogger(__name__)

    def sec(self) -> Hikaye | None:
        prompt = self.prompt_yolu.read_text(encoding="utf-8")
        for _ in range(2):
            h = serbest_hikaye(self.llm, prompt)
            if not self.db.hikaye_kullanildi_mi(h.kimlik):
                return h
            self.log.warning("Üretilen hikâye daha önce kullanılmış, yeniden üretiliyor")
        return None
```

- [ ] **Step 5: `core/kaynak/__init__.py`**

```python
from __future__ import annotations

from core.kaynak.reddit import RedditKaynak
from core.kaynak.uretim import UretimKaynak


def kaynak_olustur(kanal, llm, db, log):
    k = kanal.kaynak
    if k.tip == "reddit":
        return RedditKaynak(k.subredditler, k.min, k.max, db, log=log)
    return UretimKaynak(llm, k.prompt, db, log=log)
```

- [ ] **Step 6: Testler geçsin** — `PY -m pytest -q` → PASS

- [ ] **Step 7: Gerçek RSS duman testi**

Run:
```bash
.venv/Scripts/python.exe -c "import tempfile,pathlib; from core.db import DB; from core.kaynak.reddit import RedditKaynak; d=DB(pathlib.Path(tempfile.mkdtemp())/'t.db'); h=RedditKaynak(['TrueOffMyChest'],3000,4000,d).sec(); print(h.kimlik, len(h.govde)) if h else print('yok')"
```
Expected: `reddit:<id> <3000-4000>` (ya da `yok` — rapora yaz, hata sayılmaz).

- [ ] **Step 8: Commit**

```bash
git add core/kaynak tests/test_kaynak.py
git commit -m "feat: Reddit RSS ve LLM icerik kaynaklari"
```

---

### Task 6: TTS motorları (Edge-TTS, Kokoro, yedekli)

**Files:**
- Create: `core/tts/__init__.py`, `core/tts/edge.py`, `core/tts/kokoro.py`, `tests/test_tts.py`

**Interfaces:**
- Consumes: `core.medya.sure`, `core.tekrar.tekrar_dene`, `core.ayar.Ses`
- Produces:
  - `core.tts`: `TTSHatasi`, `Kelime(metin, baslangic, bitis)`, `SesSonucu(yol: Path, sure: float, kelimeler: list[Kelime])` + `.sozluk() -> dict` + `SesSonucu.sozlukten(d) -> SesSonucu`, `YedekliTTS(ana, yedek, log=None)`, `motor_olustur(ses: Ses, log=None)`. Her motorun arayüzü: `.seslendir(metin: str, cikti: Path) -> SesSonucu` (dönen `yol` farklı uzantıda olabilir; her zaman dönen yolu kullan).
  - `core.tts.edge.EdgeTTS(ses, hiz="+0%", iletisim=edge_tts.Communicate, sure_fn=medya.sure, uyku=time.sleep)`
  - `core.tts.kokoro.KokoroTTS(ses="af_heart", hiz=0.85, paragraf_arasi=1.2, dil="a", pipeline=None)`

- [ ] **Step 1: Başarısız testler**

`tests/test_tts.py`:
```python
import numpy as np
import pytest
import soundfile as sf

from core.tts import Kelime, SesSonucu, TTSHatasi, YedekliTTS
from core.tts.edge import EdgeTTS
from core.tts.kokoro import KokoroTTS


class SahteIletisim:
    def __init__(self, metin, ses, rate, boundary):
        assert boundary == "WordBoundary"
        self.metin, self.ses, self.rate = metin, ses, rate

    async def stream(self):
        yield {"type": "audio", "data": b"ID3abc"}
        yield {"type": "WordBoundary", "offset": 1_000_000, "duration": 2_500_000, "text": "Hello"}
        yield {"type": "audio", "data": b"def"}
        yield {"type": "WordBoundary", "offset": 4_000_000, "duration": 3_000_000, "text": "there"}


def test_edge_ses_ve_kelime_zamanlari(tmp_path):
    t = EdgeTTS("ses1", "+10%", iletisim=SahteIletisim, sure_fn=lambda p: 1.2)
    s = t.seslendir("Hello there", tmp_path / "a.mp3")
    assert (tmp_path / "a.mp3").read_bytes() == b"ID3abcdef"
    assert s.sure == 1.2
    assert s.kelimeler == [Kelime("Hello", 0.1, 0.35), Kelime("there", 0.4, 0.7)]


class BosIletisim(SahteIletisim):
    async def stream(self):
        if False:
            yield {}


def test_edge_bos_ses_hata(tmp_path):
    t = EdgeTTS("s", iletisim=BosIletisim, sure_fn=lambda p: 0, uyku=lambda s: None)
    with pytest.raises(TTSHatasi):
        t.seslendir("x", tmp_path / "a.mp3")


def test_ses_sonucu_sozluk_gidis_donus(tmp_path):
    s = SesSonucu(tmp_path / "a.mp3", 2.0, [Kelime("a", 0.0, 0.5)])
    assert SesSonucu.sozlukten(s.sozluk()) == s


class SahtePipeline:
    def __init__(self):
        self.cagrilar = []

    def __call__(self, metin, voice, speed):
        self.cagrilar.append((metin, voice, speed))
        yield "g", "p", np.ones(2400, dtype=np.float32)


def test_kokoro_paragraflar_arasi_sessizlik(tmp_path):
    pl = SahtePipeline()
    t = KokoroTTS("af_heart", 0.85, paragraf_arasi=0.5, pipeline=pl)
    s = t.seslendir("Bir.\n\nIki.", tmp_path / "h.mp3")
    assert s.yol == tmp_path / "h.wav"
    veri, oran = sf.read(s.yol)
    assert oran == 24000
    assert len(veri) == 2 * 2400 + 2 * 12000
    assert s.sure == pytest.approx(len(veri) / 24000)
    assert pl.cagrilar[0] == ("Bir.", "af_heart", 0.85)


class Patlayan:
    def seslendir(self, metin, cikti):
        raise RuntimeError("model yok")


class Calisan:
    def seslendir(self, metin, cikti):
        return SesSonucu(cikti, 1.0, [])


def test_yedekli_tts_yedege_duser(tmp_path):
    s = YedekliTTS(Patlayan(), Calisan()).seslendir("x", tmp_path / "a.mp3")
    assert s.sure == 1.0
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_tts.py -q` → FAIL

- [ ] **Step 3: `core/tts/__init__.py`**

```python
"""Ortak TTS arayüzü: seslendir(metin, cikti) -> SesSonucu."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path


class TTSHatasi(Exception):
    pass


@dataclass
class Kelime:
    metin: str
    baslangic: float
    bitis: float


@dataclass
class SesSonucu:
    yol: Path
    sure: float
    kelimeler: list[Kelime] = field(default_factory=list)

    def sozluk(self) -> dict:
        return {"yol": str(self.yol), "sure": self.sure, "kelimeler": [asdict(k) for k in self.kelimeler]}

    @classmethod
    def sozlukten(cls, d: dict) -> "SesSonucu":
        return cls(Path(d["yol"]), float(d["sure"]), [Kelime(**k) for k in d.get("kelimeler", [])])


class YedekliTTS:
    def __init__(self, ana, yedek, log: logging.Logger | None = None):
        self.ana, self.yedek = ana, yedek
        self.log = log or logging.getLogger(__name__)

    def seslendir(self, metin: str, cikti: Path) -> SesSonucu:
        try:
            return self.ana.seslendir(metin, cikti)
        except Exception as e:
            self.log.warning("Ana TTS başarısız (%s), yedek motora geçiliyor", e)
            return self.yedek.seslendir(metin, cikti)


def motor_olustur(ses, log: logging.Logger | None = None):
    from core.tts.edge import EdgeTTS

    if ses.motor == "edge":
        return EdgeTTS(ses.ses, str(ses.hiz))
    from core.tts.kokoro import KokoroTTS

    return YedekliTTS(KokoroTTS(ses.ses, float(ses.hiz)),
                      EdgeTTS("en-US-AndrewMultilingualNeural", "-15%"), log)
```

- [ ] **Step 4: `core/tts/edge.py`**

```python
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import edge_tts

from core import medya
from core.tekrar import tekrar_dene
from core.tts import Kelime, SesSonucu, TTSHatasi


class EdgeTTS:
    def __init__(self, ses: str, hiz: str = "+0%", iletisim=edge_tts.Communicate,
                 sure_fn=medya.sure, uyku=time.sleep):
        self.ses, self.hiz = ses, hiz
        self.iletisim = iletisim
        self.sure_fn = sure_fn
        self.uyku = uyku

    async def _uret(self, metin: str, cikti: Path) -> SesSonucu:
        c = self.iletisim(metin, self.ses, rate=self.hiz, boundary="WordBoundary")
        kelimeler: list[Kelime] = []
        with open(cikti, "wb") as f:
            async for parca in c.stream():
                if parca["type"] == "audio":
                    f.write(parca["data"])
                elif parca["type"] == "WordBoundary":
                    bas = parca["offset"] / 1e7
                    kelimeler.append(Kelime(parca["text"], round(bas, 3), round(bas + parca["duration"] / 1e7, 3)))
        if not kelimeler or Path(cikti).stat().st_size == 0:
            raise TTSHatasi("Edge-TTS boş ses döndürdü")
        return SesSonucu(Path(cikti), self.sure_fn(cikti), kelimeler)

    def seslendir(self, metin: str, cikti: Path) -> SesSonucu:
        Path(cikti).parent.mkdir(parents=True, exist_ok=True)
        return tekrar_dene(lambda: asyncio.run(self._uret(metin, Path(cikti))),
                           deneme=3, bekleme=5, uyku=self.uyku)
```

- [ ] **Step 5: `core/tts/kokoro.py`**

```python
"""Kokoro-82M ile lokal, ücretsiz seslendirme (24 kHz WAV)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import soundfile as sf

from core.tts import SesSonucu, TTSHatasi

ORNEKLEME = 24000


class KokoroTTS:
    def __init__(self, ses: str = "af_heart", hiz: float = 0.85, paragraf_arasi: float = 1.2,
                 dil: str = "a", pipeline=None):
        self.ses, self.hiz = ses, hiz
        self.paragraf_arasi = paragraf_arasi
        self.dil = dil
        self._pipeline = pipeline

    def _pl(self):
        if self._pipeline is None:
            from kokoro import KPipeline

            self._pipeline = KPipeline(lang_code=self.dil, repo_id="hexgrad/Kokoro-82M")
        return self._pipeline

    def seslendir(self, metin: str, cikti: Path) -> SesSonucu:
        paragraflar = [p.strip() for p in re.split(r"\n\s*\n", metin) if p.strip()]
        sessizlik = np.zeros(int(ORNEKLEME * self.paragraf_arasi), dtype=np.float32)
        parcalar, ses_var = [], False
        for p in paragraflar:
            for _, _, ses in self._pl()(p, voice=self.ses, speed=self.hiz):
                if ses is None:
                    continue
                dizi = ses.numpy() if hasattr(ses, "numpy") else np.asarray(ses)
                parcalar.append(dizi.astype(np.float32))
                ses_var = ses_var or len(dizi) > 0
            parcalar.append(sessizlik)
        if not ses_var:
            raise TTSHatasi("Kokoro ses üretmedi")
        tum = np.concatenate(parcalar)
        wav = Path(cikti).with_suffix(".wav")
        wav.parent.mkdir(parents=True, exist_ok=True)
        sf.write(wav, tum, ORNEKLEME)
        return SesSonucu(wav, len(tum) / ORNEKLEME, [])
```

- [ ] **Step 6: Testler geçsin** — `PY -m pytest -q` → PASS

- [ ] **Step 7: Gerçek motor duman testi**

Run:
```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from core.tts.edge import EdgeTTS; s=EdgeTTS('en-US-AndrewMultilingualNeural','+10%').seslendir('Hello there, this is a test.', Path('cikti/duman/edge.mp3')); print(s.sure, len(s.kelimeler))"
.venv/Scripts/python.exe -c "from pathlib import Path; from core.tts.kokoro import KokoroTTS; s=KokoroTTS().seslendir('The rain fell softly.\n\nThe night was calm.', Path('cikti/duman/kokoro.mp3')); print(s.yol, s.sure)"
```
Expected: ilki `~2.x 6`; ikincisi `cikti\duman\kokoro.wav ~4-6` (ilk çalıştırma modeli indirir). Kokoro hata verirse (ör. spacy/espeak eksik) hatayı çöz; çözemiyorsan rapora yaz — `YedekliTTS` Edge'e düşeceği için akış bloke değildir.

- [ ] **Step 8: Commit**

```bash
git add core/tts tests/test_tts.py
git commit -m "feat: Edge-TTS ve Kokoro TTS motorlari"
```

---

### Task 7: TikTok altyazı (.ass) ve dikey video render

**Files:**
- Create: `core/render/__init__.py` (boş), `core/render/altyazi.py`, `core/render/tiktok_dikey.py`, `tests/test_altyazi.py`, `tests/test_render_tiktok.py`

**Interfaces:**
- Consumes: `core.tts.Kelime`, `core.tts.SesSonucu`, `core.medya`
- Produces:
  - `core.render.altyazi`: `satirlara_bol(kelimeler, en_fazla=4) -> list[list[Kelime]]`, `ass_olustur(kelimeler, genislik=1080, yukseklik=1920, font="Arial", boyut=88, en_fazla=4) -> str`
  - `core.render.tiktok_dikey.render_tiktok(arka_plan: Path, ses: SesSonucu, cikti: Path, rastgele=random) -> Path`

- [ ] **Step 1: Başarısız testler**

`tests/test_altyazi.py`:
```python
from core.render.altyazi import ass_olustur, satirlara_bol
from core.tts import Kelime


def k(m, b, e):
    return Kelime(m, b, e)


def test_satirlara_bol_en_fazla_ve_noktalama():
    ks = [k("a", 0, 1), k("b.", 1, 2), k("c", 2, 3), k("d", 3, 4), k("e", 4, 5), k("f", 5, 6)]
    assert [[x.metin for x in s] for s in satirlara_bol(ks, en_fazla=3)] == [["a", "b."], ["c", "d", "e"], ["f"]]


def test_ass_vurgulu_kelime_olaylari():
    ks = [k("hi", 0.0, 0.4), k("{you}", 0.5, 1.23)]
    ass = ass_olustur(ks)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    olaylar = [s for s in ass.splitlines() if s.startswith("Dialogue:")]
    assert olaylar[0] == r"Dialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,{\c&H00FFFF&}HI{\c&HFFFFFF&} (YOU)"
    assert olaylar[1] == r"Dialogue: 0,0:00:00.50,0:00:01.23,Default,,0,0,0,,HI {\c&H00FFFF&}(YOU){\c&HFFFFFF&}"


def test_ass_saat_bicimi_ve_sifir_sure():
    ass = ass_olustur([k("x", 3725.5, 3725.5)])
    assert "1:02:05.50,1:02:05.55" in ass
```

`tests/test_render_tiktok.py`:
```python
import random
import subprocess

import pytest

from core import medya
from core.render.tiktok_dikey import render_tiktok
from core.tts import Kelime, SesSonucu


@pytest.mark.ffmpeg
def test_render_tiktok_uretir(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=640x360:rate=24", "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    ses = tmp_path / "ses.mp3"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=300:duration=2", ses])
    s = SesSonucu(ses, medya.sure(ses), [Kelime("hello", 0.1, 0.6), Kelime("world", 0.7, 1.5)])
    cikti = tmp_path / "out" / "p1.mp4"
    render_tiktok(bg, s, cikti, rastgele=random.Random(1))
    assert medya.sure(cikti) == pytest.approx(2.5, abs=0.3)
    akislar = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
                              "-of", "csv=p=0", str(cikti)], capture_output=True, text=True).stdout
    assert "video,1080,1920" in akislar and "audio" in akislar


@pytest.mark.ffmpeg
def test_kisa_arka_plan_dongulenir(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=640x360:rate=24", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    ses = tmp_path / "ses.mp3"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=duration=3", ses])
    cikti = tmp_path / "p.mp4"
    render_tiktok(bg, SesSonucu(ses, medya.sure(ses), [Kelime("a", 0, 1)]), cikti)
    assert medya.sure(cikti) == pytest.approx(3.5, abs=0.3)
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_altyazi.py tests/test_render_tiktok.py -q` → FAIL

- [ ] **Step 3: `core/render/altyazi.py`**

```python
"""Kelime vurgulu TikTok altyazısı (.ass)."""
from __future__ import annotations

from core.tts import Kelime

VURGU = r"{\c&H00FFFF&}"   # sarı (BGR)
NORMAL = r"{\c&HFFFFFF&}"  # beyaz

BASLIK = """[Script Info]
ScriptType: v4.00+
PlayResX: {genislik}
PlayResY: {yukseklik}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{boyut},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _zaman(sn: float) -> str:
    cs = max(0, round(sn * 100))
    s, cs = divmod(cs, 100)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _kacis(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def satirlara_bol(kelimeler: list[Kelime], en_fazla: int = 4) -> list[list[Kelime]]:
    satirlar, mevcut = [], []
    for k in kelimeler:
        mevcut.append(k)
        if len(mevcut) >= en_fazla or k.metin[-1:] in ".!?,;:":
            satirlar.append(mevcut)
            mevcut = []
    if mevcut:
        satirlar.append(mevcut)
    return satirlar


def ass_olustur(kelimeler: list[Kelime], genislik: int = 1080, yukseklik: int = 1920,
                font: str = "Arial", boyut: int = 88, en_fazla: int = 4) -> str:
    olaylar = []
    for satir in satirlara_bol(kelimeler, en_fazla):
        metinler = [_kacis(k.metin.upper()) for k in satir]
        for i, k in enumerate(satir):
            bitis = satir[i + 1].baslangic if i + 1 < len(satir) else k.bitis
            if bitis <= k.baslangic:
                bitis = k.baslangic + 0.05
            parcalar = [f"{VURGU}{m}{NORMAL}" if j == i else m for j, m in enumerate(metinler)]
            olaylar.append(f"Dialogue: 0,{_zaman(k.baslangic)},{_zaman(bitis)},Default,,0,0,0,,{' '.join(parcalar)}")
    return BASLIK.format(genislik=genislik, yukseklik=yukseklik, font=font, boyut=boyut) + "\n".join(olaylar) + "\n"
```

- [ ] **Step 4: `core/render/tiktok_dikey.py`**

```python
"""Arka plan + ses + kelime vurgulu altyazı -> 1080x1920 MP4."""
from __future__ import annotations

import random
from pathlib import Path

from core import medya
from core.render.altyazi import ass_olustur
from core.tts import SesSonucu


def render_tiktok(arka_plan: Path, ses: SesSonucu, cikti: Path, rastgele=random) -> Path:
    cikti = Path(cikti).resolve()
    cikti.parent.mkdir(parents=True, exist_ok=True)
    ass_adi = cikti.stem + ".ass"
    (cikti.parent / ass_adi).write_text(ass_olustur(ses.kelimeler), encoding="utf-8")

    sure = ses.sure + 0.5
    bg_sure = medya.sure(arka_plan)
    if bg_sure > sure + 1:
        girdi = ["-ss", f"{rastgele.uniform(0, bg_sure - sure):.2f}", "-i", Path(arka_plan).resolve()]
    else:
        girdi = ["-stream_loop", "-1", "-i", Path(arka_plan).resolve()]

    vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,ass={ass_adi}"
    medya.ffmpeg([
        *girdi, "-i", Path(ses.yol).resolve(),
        "-map", "0:v:0", "-map", "1:a:0", "-t", f"{sure:.2f}",
        "-vf", vf, "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-af", "apad", "-movflags", "+faststart",
        cikti,
    ], cwd=cikti.parent)
    return cikti
```

(`ass=` filtresine Windows yolu vermemek için ffmpeg, `.ass` dosyasının bulunduğu klasörde (`cwd`) çalıştırılır; diğer tüm yollar mutlaktır. `apad` sesi videonun sonuna kadar sessizlikle uzatır.)

- [ ] **Step 5: Testler geçsin** — `PY -m pytest -q` → PASS

- [ ] **Step 6: Commit**

```bash
git add core/render tests/test_altyazi.py tests/test_render_tiktok.py
git commit -m "feat: kelime vurgulu altyazi ve TikTok dikey render"
```

---

### Task 8: YouTube uyku videosu render (döngülü anlatım)

**Files:**
- Create: `core/render/youtube_uyku.py`, `tests/test_render_youtube.py`

**Interfaces:**
- Consumes: `core.medya`
- Produces: `core.render.youtube_uyku`: `tekrar_sayisi(hikaye_sn, ara_sn, hedef_sn, en_fazla) -> int`, `render_youtube(arka_plan, hikaye_ses, ortam, seviye, tekrar, ara_sn, hedef_sn, cikti) -> int` (kullanılan tekrar sayısını döner)

- [ ] **Step 1: Başarısız testler**

`tests/test_render_youtube.py`:
```python
import pytest

from core import medya
from core.render.youtube_uyku import render_youtube, tekrar_sayisi


@pytest.mark.parametrize("hikaye,ara,hedef,en_fazla,beklenen", [
    (1200, 8, 5400, 5, 4),     # 20 dk hikâye: 4 tekrar sığar
    (1000, 8, 5400, 5, 5),     # 16.7 dk: 5 sığar
    (600, 8, 5400, 5, 5),      # kısa: en_fazla sınırı
    (6000, 8, 5400, 5, 1),     # hedeften uzun: en az 1
])
def test_tekrar_sayisi(hikaye, ara, hedef, en_fazla, beklenen):
    assert tekrar_sayisi(hikaye, ara, hedef, en_fazla) == beklenen


@pytest.mark.ffmpeg
def test_render_youtube_hedef_surede(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    hikaye = tmp_path / "h.wav"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=500:duration=2", hikaye])
    ortam = tmp_path / "r.mp3"
    medya.ffmpeg(["-f", "lavfi", "-i", "anoisesrc=d=1:a=0.1", ortam])
    cikti = tmp_path / "out" / "final.mp4"
    n = render_youtube(bg, hikaye, ortam, 0.3, tekrar=5, ara_sn=1, hedef_sn=10, cikti=cikti)
    assert n == 3
    assert medya.sure(cikti) == pytest.approx(10, abs=1.0)
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_render_youtube.py -q` → FAIL

- [ ] **Step 3: `core/render/youtube_uyku.py`**

```python
"""Hikâye sesi xN (aralarda sessizlik) + sürekli ortam sesi + döngülü video."""
from __future__ import annotations

import math
from pathlib import Path

from core import medya

_SES_BICIMI = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"


def tekrar_sayisi(hikaye_sn: float, ara_sn: float, hedef_sn: float, en_fazla: int) -> int:
    sigan = math.floor((hedef_sn + ara_sn) / (hikaye_sn + ara_sn))
    return max(1, min(en_fazla, sigan))


def _anlatim_filtresi(n: int, ara_sn: float) -> str:
    on = f"[1:a]{_SES_BICIMI},apad=pad_dur={ara_sn}"
    if n == 1:
        return on + "[anl]"
    etiketler = "".join(f"[h{i}]" for i in range(n))
    return f"{on},asplit={n}{etiketler};{etiketler}concat=n={n}:v=0:a=1[anl]"


def render_youtube(arka_plan: Path, hikaye_ses: Path, ortam: Path, seviye: float, tekrar: int,
                   ara_sn: float, hedef_sn: float, cikti: Path) -> int:
    cikti = Path(cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    n = tekrar_sayisi(medya.sure(hikaye_ses), ara_sn, hedef_sn, tekrar)
    fade_d = min(30.0, hedef_sn / 2)
    filtre = (
        _anlatim_filtresi(n, ara_sn) + ";"
        f"[2:a]{_SES_BICIMI},volume={seviye}[ort];"
        f"[anl][ort]amix=inputs=2:duration=longest:normalize=0,"
        f"afade=t=out:st={hedef_sn - fade_d}:d={fade_d}[a]"
    )
    medya.ffmpeg([
        "-stream_loop", "-1", "-i", arka_plan,
        "-i", hikaye_ses,
        "-stream_loop", "-1", "-i", ortam,
        "-filter_complex", filtre,
        "-map", "0:v:0", "-map", "[a]",
        "-t", f"{hedef_sn:.2f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        cikti,
    ])
    return n
```

- [ ] **Step 4: Testler geçsin** — `PY -m pytest -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add core/render/youtube_uyku.py tests/test_render_youtube.py
git commit -m "feat: YouTube uyku videosu dongulu anlatim render"
```

---

### Task 9: YouTube yükleyici

**Files:**
- Create: `core/upload/__init__.py` (boş), `core/upload/youtube.py`, `tests/test_upload_youtube.py`

**Interfaces:**
- Produces: `core.upload.youtube`: `YukleHatasi`, `SCOPES`, `kimlik_yukle(token_yol, client_secret, eski_pickle=None, etkilesimli=False)`, `govde_olustur(baslik, aciklama, etiketler, kategori, gorunurluk) -> dict`, `yukle(creds, video, baslik, aciklama, etiketler, kategori, gorunurluk, servis=None, deneme=10, uyku=time.sleep, log=None) -> str`

- [ ] **Step 1: Başarısız testler**

`tests/test_upload_youtube.py`:
```python
import pytest

from core.upload.youtube import YukleHatasi, govde_olustur, kimlik_yukle, yukle


def test_govde_sinirlari_ve_temizlik():
    g = govde_olustur("A <b> title " + "x" * 200, "desc <x>", ["t" * 60] * 20, "22", "private")
    assert len(g["snippet"]["title"]) <= 100 and "<" not in g["snippet"]["title"]
    assert "<" not in g["snippet"]["description"]
    assert sum(len(t) + 2 for t in g["snippet"]["tags"]) <= 480
    assert g["snippet"]["categoryId"] == "22"
    assert g["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}


class SahteIstek:
    def __init__(self, adimlar):
        self.adimlar = list(adimlar)

    def next_chunk(self):
        a = self.adimlar.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


class SahteServis:
    def __init__(self, istek):
        self.istek = istek
        self.govde = None

    def videos(self):
        return self

    def insert(self, part, body, media_body):
        self.govde = body
        return self.istek


def test_baglanti_hatasinda_devam_eder(tmp_path, monkeypatch):
    monkeypatch.setattr("core.upload.youtube.MediaFileUpload", lambda *a, **k: object())
    istek = SahteIstek([ConnectionError("koptu"), (None, None), (None, {"id": "vid1"})])
    beklemeler = []
    vid = yukle(None, tmp_path / "v.mp4", "t", "d", [], "22", "private",
                servis=SahteServis(istek), uyku=beklemeler.append)
    assert vid == "vid1"
    assert beklemeler == [2]


def test_cok_hata_vazgecer(tmp_path, monkeypatch):
    monkeypatch.setattr("core.upload.youtube.MediaFileUpload", lambda *a, **k: object())
    istek = SahteIstek([ConnectionError("x")] * 5)
    with pytest.raises(YukleHatasi):
        yukle(None, tmp_path / "v.mp4", "t", "d", [], "22", "private",
              servis=SahteServis(istek), deneme=3, uyku=lambda s: None)


def test_token_yoksa_etkilesimsiz_hata(tmp_path):
    with pytest.raises(YukleHatasi, match="--giris"):
        kimlik_yukle(tmp_path / "t.json", tmp_path / "cs.json", tmp_path / "eski.pickle", etkilesimli=False)
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_upload_youtube.py -q` → FAIL

- [ ] **Step 3: `core/upload/youtube.py`**

```python
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
```

- [ ] **Step 4: Testler geçsin** — `PY -m pytest -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add core/upload tests/test_upload_youtube.py
git commit -m "feat: YouTube yukleyici (JSON token, sinirli tekrar)"
```

---

### Task 10: TikTok yükleyici (Playwright)

**Files:**
- Create: `core/upload/tiktok_secici.py`, `core/upload/tiktok.py`, `tests/test_upload_tiktok.py`

**Interfaces:**
- Consumes: `core.ayar` yok (yollar parametre).
- Produces: `core.upload.tiktok`: `TikTokHatasi(mesaj, ekran=None)` (`.ekran: Path|None`), `zamani_yuvarla(dt) -> datetime` (sonraki 5 dk katına yukarı), `TikTokYukleyici(profil_dir, hata_dir, log=None, headless=False)` → `.giris()` ve `.yukle(video: Path, aciklama: str, etiketler: list[str], gorunurluk: str, zaman: datetime|None) -> None`

**Not:** TikTok Studio seçicileri canlı hesap olmadan doğrulanamaz. Bu görevde kod + saf fonksiyon testleri yazılır; seçici kalibrasyonu Task 13'te kullanıcıyla canlı yapılır. Tüm seçiciler `tiktok_secici.py`'dedir; arayüz İngilizce'ye sabitlenir (`lang=en`, `locale="en-US"`).

- [ ] **Step 1: Başarısız testler**

`tests/test_upload_tiktok.py`:
```python
from datetime import datetime

import pytest

from core.upload.tiktok import TikTokHatasi, zamani_yuvarla


@pytest.mark.parametrize("girdi,beklenen", [
    (datetime(2026, 9, 29, 14, 0, 0), datetime(2026, 9, 29, 14, 0)),
    (datetime(2026, 9, 29, 14, 0, 1), datetime(2026, 9, 29, 14, 5)),
    (datetime(2026, 9, 29, 14, 7, 30), datetime(2026, 9, 29, 14, 10)),
    (datetime(2026, 9, 29, 23, 58), datetime(2026, 9, 30, 0, 0)),
])
def test_zamani_yuvarla(girdi, beklenen):
    assert zamani_yuvarla(girdi) == beklenen


def test_hata_ekran_goruntusu_tasir(tmp_path):
    h = TikTokHatasi("x", ekran=tmp_path / "a.png")
    assert h.ekran == tmp_path / "a.png" and str(h) == "x"
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_upload_tiktok.py -q` → FAIL

- [ ] **Step 3: `core/upload/tiktok_secici.py`**

```python
"""TikTok Studio DOM seçicileri. Arayüz değişince SADECE burası güncellenir.
Arayüz dili İngilizce'ye sabitlenir (URL'de lang=en)."""

YUKLEME_URL = "https://www.tiktok.com/tiktokstudio/upload?from=upload&lang=en"
GIRIS_URL = "https://www.tiktok.com/login?lang=en"
ICERIK_URL_DESENI = "**/tiktokstudio/content**"

DOSYA_INPUT = 'input[type="file"]'
ACIKLAMA_EDITOR = 'div.public-DraftEditor-content[contenteditable="true"], div[contenteditable="true"]'
ETIKET_ONERI_OGE = ('div.mention-list-popover-item, div[class*="hashtag-suggestion"] div[class*="item"], '
                    'div[class*="mention-list"] div[class*="item"]')
PAYLAS_BUTON = 'button[data-e2e="post_video_button"]'

# Yükleme bitti göstergesi (herhangi biri görününce)
YUKLEME_TAMAM = ['text="Uploaded"', '[data-e2e="upload_status_container"] >> text=/uploaded/i']

# Kapatılacak popup/banner düğmeleri (görünenler tıklanır)
KAPAT_BUTONLARI = [
    'button:has-text("Decline optional cookies")',
    'button:has-text("Got it")',
    'button:has-text("Not now")',
    'button:has-text("Cancel")',
    'div[role="dialog"] button[aria-label="Close"]',
]

# Görünürlük
GORUNURLUK_ACICI = 'div[data-e2e="video_visibility_container"] button, div:has(> span:text("Who can watch this video")) button'
GORUNURLUK_METIN = {"herkes": "Everyone", "arkadaslar": "Friends", "sadece_ben": "Only you"}

# Zamanlama
ZAMANLA_SECENEK = 'label:has-text("Schedule"), input[value="schedule"]'
ZAMANLA_IZIN = 'button:has-text("Allow")'
ZAMAN_GIRDILERI = 'div[class*="scheduled-picker"] input, div[class*="schedule"] input'  # [0]=saat, [1]=tarih
TAKVIM_SONRAKI_AY = 'div[class*="calendar"] span[class*="arrow"]:last-child'
TAKVIM_GUN = 'div[class*="calendar"] span[class*="day"][class*="valid"]'
SAAT_SECENEK = 'span[class*="tiktok-timepicker-left"]'
DAKIKA_SECENEK = 'span[class*="tiktok-timepicker-right"]'

# Paylaşım sonrası
SIMDI_PAYLAS = 'button:has-text("Post now")'
BASARI_METINLERI = ['text=/your video (has been|is being) (uploaded|posted|published)/i',
                    'text=/video (scheduled|published)/i', 'text=/Manage your posts/i']
```

- [ ] **Step 4: `core/upload/tiktok.py`**

```python
"""TikTok Studio'ya Playwright ile yükleme (hesap başına kalıcı Chrome profili)."""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from core.upload import tiktok_secici as s


class TikTokHatasi(Exception):
    def __init__(self, mesaj: str, ekran: Path | None = None):
        super().__init__(mesaj)
        self.ekran = ekran


def zamani_yuvarla(dt: datetime) -> datetime:
    temel = dt.replace(second=0, microsecond=0)
    if temel == dt and dt.minute % 5 == 0:
        return temel
    eksik = 5 - (temel.minute % 5)
    return temel + timedelta(minutes=eksik)


class TikTokYukleyici:
    def __init__(self, profil_dir: Path, hata_dir: Path, log: logging.Logger | None = None, headless: bool = False):
        self.profil_dir = Path(profil_dir)
        self.hata_dir = Path(hata_dir)
        self.log = log or logging.getLogger(__name__)
        self.headless = headless

    # --- tarayıcı ---
    def _baslat(self, p):
        self.profil_dir.mkdir(parents=True, exist_ok=True)
        ayar = dict(headless=self.headless, viewport={"width": 1366, "height": 900}, locale="en-US",
                    args=["--disable-blink-features=AutomationControlled"])
        try:
            ctx = p.chromium.launch_persistent_context(str(self.profil_dir), channel="chrome", **ayar)
        except Exception as e:
            self.log.warning("Sistem Chrome'u açılamadı (%s), Playwright Chromium kullanılıyor", e)
            ctx = p.chromium.launch_persistent_context(str(self.profil_dir), **ayar)
        sayfa = ctx.pages[0] if ctx.pages else ctx.new_page()
        sayfa.set_default_timeout(30_000)
        return ctx, sayfa

    def giris(self) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx, sayfa = self._baslat(p)
            sayfa.goto(s.GIRIS_URL)
            input("Açılan pencerede TikTok'a giriş yap, bitince bu pencereye dönüp Enter'a bas... ")
            ctx.close()

    # --- yardımcılar ---
    def _bekle(self, a: float = 0.6, b: float = 1.8) -> None:
        time.sleep(random.uniform(a, b))

    def _yaz(self, sayfa, metin: str) -> None:
        for harf in metin:
            sayfa.keyboard.type(harf)
            time.sleep(random.uniform(0.03, 0.11))

    def _popuplari_kapat(self, sayfa) -> None:
        for secici in s.KAPAT_BUTONLARI:
            try:
                b = sayfa.locator(secici).first
                if b.is_visible(timeout=500):
                    b.click()
                    self._bekle(0.3, 0.8)
            except Exception:
                pass

    def _ekran_kaydet(self, sayfa, ad: str) -> Path | None:
        try:
            self.hata_dir.mkdir(parents=True, exist_ok=True)
            yol = self.hata_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{ad}.png"
            sayfa.screenshot(path=str(yol), full_page=True)
            yol.with_suffix(".html").write_text(sayfa.content(), encoding="utf-8")
            return yol
        except Exception:
            return None

    # --- adımlar ---
    def _dosya_sec(self, sayfa, video: Path) -> None:
        sayfa.locator(s.DOSYA_INPUT).first.set_input_files(str(video))
        paylas = sayfa.locator(s.PAYLAS_BUTON)
        bitis = time.time() + 600
        while time.time() < bitis:
            tamam = any(sayfa.locator(x).count() for x in s.YUKLEME_TAMAM)
            aktif = (paylas.count() > 0 and paylas.first.is_enabled()
                     and paylas.first.get_attribute("aria-disabled") != "true")
            if tamam and aktif:
                return
            time.sleep(2)
        raise TikTokHatasi("Video 10 dakikada yüklenmedi")

    def _aciklama_ve_etiketler(self, sayfa, aciklama: str, etiketler: list[str]) -> None:
        editor = sayfa.locator(s.ACIKLAMA_EDITOR).first
        editor.click()
        sayfa.keyboard.press("Control+A")
        sayfa.keyboard.press("Delete")
        self._yaz(sayfa, aciklama)
        for etiket in etiketler:
            self._yaz(sayfa, f" #{etiket}")
            oneriler = sayfa.locator(s.ETIKET_ONERI_OGE)
            try:
                oneriler.first.wait_for(state="visible", timeout=5000)
                self._bekle(0.4, 0.9)
                eslesen = oneriler.filter(has_text=re.compile(rf"^#?{re.escape(etiket)}\b", re.IGNORECASE))
                if eslesen.count():
                    eslesen.first.click()
                    self._bekle()
                    continue
            except Exception:
                pass
            self.log.warning("Etiket önerisi bulunamadı, düz metin kaldı: #%s", etiket)
            sayfa.keyboard.type(" ")

    def _gorunurluk(self, sayfa, gorunurluk: str) -> None:
        metin = s.GORUNURLUK_METIN[gorunurluk]
        sayfa.locator(s.GORUNURLUK_ACICI).first.click()
        self._bekle(0.4, 0.9)
        sayfa.get_by_role("option", name=metin).or_(sayfa.get_by_text(metin, exact=True)).first.click()
        self._bekle()

    def _zamanla(self, sayfa, zaman: datetime) -> None:
        zaman = zamani_yuvarla(zaman)
        sayfa.locator(s.ZAMANLA_SECENEK).first.click()
        self._bekle()
        izin = sayfa.locator(s.ZAMANLA_IZIN).first
        if izin.is_visible(timeout=1500):
            izin.click()
            self._bekle()
        girdiler = sayfa.locator(s.ZAMAN_GIRDILERI)
        # tarih
        girdiler.nth(1).click()
        bugun = datetime.now()
        for _ in range((zaman.year * 12 + zaman.month) - (bugun.year * 12 + bugun.month)):
            sayfa.locator(s.TAKVIM_SONRAKI_AY).first.click()
            self._bekle(0.3, 0.6)
        sayfa.locator(s.TAKVIM_GUN).filter(has_text=re.compile(rf"^{zaman.day}$")).first.click()
        self._bekle()
        # saat ve dakika
        girdiler.nth(0).click()
        sayfa.locator(s.SAAT_SECENEK).filter(has_text=re.compile(rf"^{zaman.hour:02d}$")).first.click()
        self._bekle(0.3, 0.6)
        sayfa.locator(s.DAKIKA_SECENEK).filter(has_text=re.compile(rf"^{zaman.minute:02d}$")).first.click()
        self._bekle()
        beklenen = f"{zaman.hour:02d}:{zaman.minute:02d}"
        if girdiler.nth(0).input_value() != beklenen:
            raise TikTokHatasi(f"Zamanlama saati ayarlanamadı: {girdiler.nth(0).input_value()} != {beklenen}")

    def _paylas_ve_dogrula(self, sayfa) -> None:
        sayfa.locator(s.PAYLAS_BUTON).first.click()
        simdi = sayfa.locator(s.SIMDI_PAYLAS).first
        try:
            if simdi.is_visible(timeout=5000):
                simdi.click()
        except Exception:
            pass
        bitis = time.time() + 180
        while time.time() < bitis:
            if re.search(r"/tiktokstudio/content", sayfa.url):
                return
            if any(sayfa.locator(x).count() for x in s.BASARI_METINLERI):
                return
            time.sleep(2)
        raise TikTokHatasi("Paylaşım 3 dakika içinde doğrulanamadı")

    def yukle(self, video: Path, aciklama: str, etiketler: list[str], gorunurluk: str,
              zaman: datetime | None = None) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx, sayfa = self._baslat(p)
            try:
                sayfa.goto(s.YUKLEME_URL)
                self._bekle(2, 4)
                if "/login" in sayfa.url:
                    raise TikTokHatasi("TikTok oturumu kapalı; 'calistir.py <kanal> --giris' ile giriş yap")
                self._popuplari_kapat(sayfa)
                self.log.info("Video seçiliyor: %s", Path(video).name)
                self._dosya_sec(sayfa, Path(video))
                self._popuplari_kapat(sayfa)
                self._aciklama_ve_etiketler(sayfa, aciklama, etiketler)
                self._gorunurluk(sayfa, gorunurluk)
                if zaman:
                    self._zamanla(sayfa, zaman)
                self._popuplari_kapat(sayfa)
                self._paylas_ve_dogrula(sayfa)
                self.log.info("TikTok paylaşımı doğrulandı")
                self._bekle(3, 5)
            except TikTokHatasi as e:
                e.ekran = e.ekran or self._ekran_kaydet(sayfa, "tiktok")
                raise
            except Exception as e:
                raise TikTokHatasi(f"TikTok yükleme hatası: {e}", self._ekran_kaydet(sayfa, "tiktok")) from e
            finally:
                ctx.close()
```

- [ ] **Step 5: Testler geçsin ve import kontrolü** — `PY -m pytest -q` → PASS; `PY -m playwright --version` bir sürüm yazdırmalı.

- [ ] **Step 6: Commit**

```bash
git add core/upload/tiktok.py core/upload/tiktok_secici.py tests/test_upload_tiktok.py
git commit -m "feat: Playwright ile TikTok yukleyici (secici dosyasi ayri)"
```

---

### Task 11: İş akışı, ön kontrol ve CLI

**Files:**
- Create: `core/onkontrol.py`, `core/is_akisi.py`, `core/ses_ornekleri.py`, `calistir.py`, `tests/test_onkontrol.py`, `tests/test_is_akisi.py`

**Interfaces:**
- Consumes: Task 1-10'daki tüm arayüzler.
- Produces:
  - `core.onkontrol.onkontrol(kanal, kok=KOK, kuru=False) -> list[str]` (boş liste = sorun yok)
  - `core.is_akisi`: `IsHatasi`, `Baglam` dataclass (alanlar aşağıda), `calistir(b: Baglam) -> Is`
  - `calistir.py`: `main(argv=None) -> int`

- [ ] **Step 1: Başarısız testler**

`tests/test_onkontrol.py`:
```python
from core.ayar import Etiketler, Kanal, Kaynak, Ses
from core.onkontrol import onkontrol


def tiktok(tmp_path):
    return Kanal(ad="t", platform="tiktok", kaynak=Kaynak("reddit", ["A"]), ses=Ses("edge", "v", "+0%"),
                 arka_plan=tmp_path / "bg.mp4", gorunurluk="herkes", etiketler=Etiketler(), profil="p1")


def test_eksikler_listelenir(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    hatalar = onkontrol(tiktok(tmp_path), kok=tmp_path)
    metin = "\n".join(hatalar)
    assert "GEMINI_API_KEY" in metin and "bg.mp4" in metin and "--giris" in metin


def test_kuru_modda_oturum_istenmez(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    (tmp_path / "bg.mp4").write_bytes(b"x")
    assert onkontrol(tiktok(tmp_path), kok=tmp_path, kuru=True) == []
```

`tests/test_is_akisi.py`:
```python
import logging
from datetime import datetime
from pathlib import Path

import pytest

from core.ayar import Etiketler, Kanal, Kaynak, Ses
from core.db import DB
from core.is_akisi import Baglam, calistir
from core.modeller import Hikaye
from core.tts import Kelime, SesSonucu

LOG = logging.getLogger("test")


class SahteLLM:
    def json_uret(self, prompt, sema, sicaklik=0.8):
        if "hook" in sema["properties"]:
            return {"hook": "Hook.", "part1": "Hook. One.", "part2": "Two.", "aciklama": "Desc #x",
                    "etiketler": ["drama", "family", "aita"]}
        return {"baslik": "Rain", "aciklama": "d", "etiketler": ["sleep"], "hikaye": "Calm words."}


class SahteKaynak:
    def __init__(self):
        self.cagri = 0

    def sec(self):
        self.cagri += 1
        return Hikaye("reddit:abc", "T", "Body")


class SahteTTS:
    def seslendir(self, metin, cikti):
        Path(cikti).parent.mkdir(parents=True, exist_ok=True)
        Path(cikti).write_bytes(b"a")
        return SesSonucu(Path(cikti), 3.0, [Kelime("x", 0, 1)])


class SahteTikTok:
    def __init__(self, patla=0):
        self.yuklemeler = []
        self.patla = patla

    def yukle(self, video, aciklama, etiketler, gorunurluk, zaman=None):
        if self.patla:
            self.patla -= 1
            raise RuntimeError("tiktok coktu")
        self.yuklemeler.append((Path(video).name, aciklama, etiketler, gorunurluk, zaman))


class SahteBildirim:
    def __init__(self):
        self.mesajlar = []

    def mesaj(self, m):
        self.mesajlar.append(m)

    def foto(self, y, m):
        self.mesajlar.append(m)


def sahte_render_tiktok(arka_plan, ses, cikti, rastgele=None):
    Path(cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(cikti).write_bytes(b"v")
    return Path(cikti)


def tiktok_kanal(**kw):
    k = Kanal(ad="t1", platform="tiktok", kaynak=Kaynak("reddit", ["A"]), ses=Ses("edge", "v", "+0%"),
              arka_plan=Path("bg.mp4"), gorunurluk="herkes",
              etiketler=Etiketler(["storytime"], 2), profil="p1")
    for a, d in kw.items():
        setattr(k, a, d)
    return k


def baglam(tmp_path, kanal, tiktok, kaynak=None, **kw):
    return Baglam(
        kanal=kanal, db=DB(tmp_path / "f.db"), llm=SahteLLM(), bildirim=SahteBildirim(), log=LOG,
        kok=tmp_path, tts_fabrika=lambda ses, log=None: SahteTTS(),
        kaynak_fabrika=lambda kanal, llm, db, log: kaynak or SahteKaynak(),
        tiktok_fabrika=lambda kanal: tiktok, render_tiktok=sahte_render_tiktok,
        simdi=lambda: datetime(2026, 9, 29, 12, 0), **kw)


def test_tiktok_mutlu_yol(tmp_path):
    tt = SahteTikTok()
    b = baglam(tmp_path, tiktok_kanal(), tt)
    is_ = calistir(b)
    assert is_.durum == "yuklendi"
    (v1, a1, e1, g1, z1), (v2, a2, e2, g2, z2) = tt.yuklemeler
    assert v1 == "part1.mp4" and a1 == "PART 1 | Desc" and z1 is None
    assert e1 == ["storytime", "drama", "family"] and g1 == "herkes"
    assert v2 == "part2.mp4" and a2.startswith("PART 2 (Final)")
    assert z2 == datetime(2026, 9, 29, 14, 0)
    assert b.db.hikaye_kullanildi_mi("reddit:abc")
    assert not (tmp_path / "cikti" / "t1" / f"is_{is_.id}").exists()  # temizlendi


def test_yukleme_hatasinda_kaldigi_yerden_devam(tmp_path):
    tt = SahteTikTok(patla=1)
    kaynak = SahteKaynak()
    b = baglam(tmp_path, tiktok_kanal(), tt, kaynak=kaynak)
    with pytest.raises(RuntimeError):
        calistir(b)
    yarim = b.db.yarim_is("t1")
    assert yarim.durum == "video_hazir" and yarim.deneme == 1
    assert "tiktok coktu" in b.bildirim.mesajlar[-1]
    is_ = calistir(b)
    assert is_.id == yarim.id and is_.durum == "yuklendi"
    assert kaynak.cagri == 1  # hikâye yeniden seçilmedi


def test_kuru_mod_yuklemez(tmp_path):
    tt = SahteTikTok()
    is_ = calistir(baglam(tmp_path, tiktok_kanal(), tt, kuru=True))
    assert is_.durum == "video_hazir" and tt.yuklemeler == []


def test_bekle_yontemi_uyur_ve_hemen_yukler(tmp_path):
    tt = SahteTikTok()
    beklemeler = []
    b = baglam(tmp_path, tiktok_kanal(parca2_yontem="bekle"), tt, uyku=beklemeler.append)
    calistir(b)
    assert beklemeler == [7200.0]
    assert tt.yuklemeler[1][4] is None


def test_uygun_hikaye_yoksa_hata(tmp_path):
    class Bos:
        def sec(self):
            return None

    b = baglam(tmp_path, tiktok_kanal(), SahteTikTok(), kaynak=Bos())
    with pytest.raises(Exception, match="hikâye"):
        calistir(b)


def test_youtube_mutlu_yol(tmp_path):
    kanal = Kanal(ad="y1", platform="youtube", kaynak=Kaynak("uretim", prompt=tmp_path / "p.txt", kelime=100),
                  ses=Ses("kokoro", "af_heart", 0.85), arka_plan=Path("bg.mp4"), gorunurluk="private",
                  token="tok", ortam_sesi=Path("r.mp3"))
    (tmp_path / "p.txt").write_text("Write {kelime} words", encoding="utf-8")
    yuklenen = {}

    def render_youtube(arka_plan, hikaye_ses, ortam, seviye, tekrar, ara_sn, hedef_sn, cikti):
        Path(cikti).parent.mkdir(parents=True, exist_ok=True)
        Path(cikti).write_bytes(b"v")
        yuklenen["hedef"] = hedef_sn
        return 4

    def youtube_yukleyici(kanal, video, baslik, aciklama, etiketler):
        yuklenen.update(baslik=baslik, aciklama=aciklama, etiketler=etiketler)
        return "vid1"

    b = Baglam(kanal=kanal, db=DB(tmp_path / "f.db"), llm=SahteLLM(), bildirim=SahteBildirim(), log=LOG,
               kok=tmp_path, tts_fabrika=lambda ses, log=None: SahteTTS(),
               render_youtube=render_youtube, youtube_yukleyici=youtube_yukleyici)
    is_ = calistir(b)
    assert is_.durum == "yuklendi" and is_.veri["video_id"] == "vid1"
    assert yuklenen["hedef"] == 5400
    assert yuklenen["baslik"] == "Rain - Deep Sleep Story (1.5 Hours)"
    assert yuklenen["aciklama"].endswith("#sleep")
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_onkontrol.py tests/test_is_akisi.py -q` → FAIL

- [ ] **Step 3: `core/onkontrol.py`**

```python
from __future__ import annotations

import os
from pathlib import Path

from core import medya
from core.ayar import KOK, client_secret_yolu, eski_token_yolu, profil_yolu, token_yolu


def onkontrol(kanal, kok: Path = KOK, kuru: bool = False) -> list[str]:
    hatalar = []
    if not medya.araclar_var_mi():
        hatalar.append("ffmpeg/ffprobe PATH'te bulunamadı")
    if not os.getenv("GEMINI_API_KEY"):
        hatalar.append(".env içinde GEMINI_API_KEY boş")
    if not Path(kanal.arka_plan).exists():
        hatalar.append(f"Arka plan videosu yok: {kanal.arka_plan}")
    if kanal.kaynak.prompt and not Path(kanal.kaynak.prompt).exists():
        hatalar.append(f"Prompt dosyası yok: {kanal.kaynak.prompt}")
    if kanal.platform == "youtube" and not Path(kanal.ortam_sesi).exists():
        hatalar.append(f"Ortam sesi yok: {kanal.ortam_sesi}")
    if kuru:
        return hatalar
    if kanal.platform == "tiktok":
        if not profil_yolu(kanal, kok).exists():
            hatalar.append(f"TikTok profili yok; önce 'calistir.py {kanal.ad} --giris' çalıştır")
    else:
        if not (token_yolu(kanal, kok).exists() or eski_token_yolu(kanal, kok).exists()):
            if not client_secret_yolu(kok).exists():
                hatalar.append(f"client_secret.json yok: {client_secret_yolu(kok)}")
            hatalar.append(f"YouTube yetkisi yok; önce 'calistir.py {kanal.ad} --giris' çalıştır")
    return hatalar
```

- [ ] **Step 4: `core/is_akisi.py`**

```python
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
```

- [ ] **Step 5: `core/ses_ornekleri.py`**

```python
"""Ses seçimi için örnek dosyalar üretir: cikti/ses_ornekleri/."""
from __future__ import annotations

from pathlib import Path

from core.ayar import KOK

ORNEK = ("The rain tapped gently against the old wooden window, and the cabin was warm and quiet.\n\n"
         "Somewhere far away, a river whispered to the stones, slow and patient, as the night settled in.")
KOKORO_SESLER = ["af_heart", "af_bella", "af_nicole", "am_michael", "bf_emma", "bm_george"]
EDGE_SESLER = ["en-US-AndrewMultilingualNeural", "en-US-AvaMultilingualNeural", "en-GB-RyanNeural"]


def uret(kok: Path = KOK) -> list[Path]:
    from core.tts.edge import EdgeTTS
    from core.tts.kokoro import KokoroTTS

    klasor = kok / "cikti" / "ses_ornekleri"
    klasor.mkdir(parents=True, exist_ok=True)
    yollar = []
    for s in KOKORO_SESLER:
        try:
            yollar.append(KokoroTTS(s, 0.85).seslendir(ORNEK, klasor / f"kokoro_{s}.wav").yol)
        except Exception as e:
            print(f"Kokoro {s} başarısız: {e}")
    for s in EDGE_SESLER:
        yollar.append(EdgeTTS(s, "-10%").seslendir(ORNEK, klasor / f"edge_{s}.mp3").yol)
    return yollar
```

- [ ] **Step 6: `calistir.py`**

```python
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
```

- [ ] **Step 7: Testler geçsin** — `PY -m pytest -q` → PASS. Ayrıca `PY calistir.py --help` yardım metnini yazdırmalı.

- [ ] **Step 8: Commit**

```bash
git add core/onkontrol.py core/is_akisi.py core/ses_ornekleri.py calistir.py tests/test_onkontrol.py tests/test_is_akisi.py
git commit -m "feat: yeniden baslatilabilir is akisi, on kontrol ve CLI"
```

---

### Task 12: Kanallar, prompt'lar, zamanlama, taşıma ve README

**Files:**
- Create: `kanallar/tiktok_hikaye1.yaml`, `kanallar/ornek_tiktok_korku.yaml`, `kanallar/youtube_slumberlab.yaml`, `prompts/korku.txt`, `prompts/uyku_hikayesi.txt`, `zamanla.py`, `tasima.py`, `README.md`, `tests/test_kanallar.py`, `tests/test_zamanla.py`

**Interfaces:**
- Consumes: `core.ayar.kanal_yukle`, `core.db.DB`
- Produces: `zamanla.gorev_adi(kanal, saat)`, `zamanla.olustur_komutu(kanal, saat, python, kok)`, `zamanla.sil_komutu(kanal, saat)`

- [ ] **Step 1: Başarısız testler**

`tests/test_kanallar.py`:
```python
from core.ayar import KOK, kanal_yukle


def test_repodaki_tum_kanallar_gecerli():
    adlar = [p.stem for p in (KOK / "kanallar").glob("*.yaml")]
    assert {"tiktok_hikaye1", "ornek_tiktok_korku", "youtube_slumberlab"} <= set(adlar)
    for ad in adlar:
        kanal_yukle(ad)
```

`tests/test_zamanla.py`:
```python
from pathlib import Path

import pytest

import zamanla


def test_olustur_komutu():
    k = zamanla.olustur_komutu("tiktok_hikaye1", "09:30", Path("C:/v/python.exe"), Path("D:/proje"))
    assert k[:3] == ["schtasks", "/Create", "/F"]
    assert k[k.index("/TN") + 1] == "IcerikFabrikasi_tiktok_hikaye1_0930"
    assert k[k.index("/ST") + 1] == "09:30"
    tr = k[k.index("/TR") + 1]
    assert tr.startswith('"C:') and "calistir.py" in tr and tr.endswith(" tiktok_hikaye1")


def test_sil_komutu():
    assert zamanla.sil_komutu("a", "18:00") == ["schtasks", "/Delete", "/F", "/TN", "IcerikFabrikasi_a_1800"]


def test_gecersiz_saat():
    with pytest.raises(ValueError):
        zamanla.olustur_komutu("a", "25:00", Path("p"), Path("k"))
```

- [ ] **Step 2: Başarısız olduğunu gör** — `PY -m pytest tests/test_kanallar.py tests/test_zamanla.py -q` → FAIL

- [ ] **Step 3: Kanal dosyaları**

`kanallar/tiktok_hikaye1.yaml`:
```yaml
# Reddit hikâyeleri — ana TikTok hesabı
platform: tiktok
profil: hikaye1
kaynak:
  tip: reddit
  subredditler: [AmItheAsshole, TrueOffMyChest, relationship_advice, confessions]
  min: 3000
  max: 4000
ses: {motor: edge, ses: en-US-AndrewMultilingualNeural, hiz: "+10%"}
arka_plan: assets/arka_plan/orbital.mp4
etiketler:
  sabit: [storytime, reddit, redditstories]
  llm_ekle: 3
parca2_gecikme_dk: 120
parca2_yontem: tiktok_zamanla   # TikTok zamanlayıcısı çalışmazsa: bekle
gorunurluk: herkes
```

`kanallar/ornek_tiktok_korku.yaml`:
```yaml
# ÖRNEK: ikinci hesap (korku hikâyeleri). Kullanmak için profil adını değiştir,
# 'python calistir.py ornek_tiktok_korku --giris' ile giriş yap.
platform: tiktok
profil: korku1
kaynak: {tip: uretim, prompt: prompts/korku.txt}
ses: {motor: edge, ses: en-US-ChristopherNeural, hiz: "+5%"}
arka_plan: assets/arka_plan/orbital.mp4
etiketler:
  sabit: [horrorstory, scarystories, creepy]
  llm_ekle: 3
parca2_gecikme_dk: 120
gorunurluk: herkes
```

`kanallar/youtube_slumberlab.yaml`:
```yaml
platform: youtube
token: slumberlab
kaynak: {tip: uretim, prompt: prompts/uyku_hikayesi.txt, kelime: 2500}
ses: {motor: kokoro, ses: af_heart, hiz: 0.85}
tekrar: 5
tekrar_arasi_sn: 8
hedef_sure_dk: 90
arka_plan: assets/arka_plan/gece.mp4
ortam_sesi: {dosya: assets/yagmur.mp3, seviye: 0.25}
gorunurluk: private   # ilk hafta kontrol için; sonra public
kategori: "22"
```

- [ ] **Step 4: Prompt dosyaları**

`prompts/korku.txt`:
```
Write an original first-person horror story for a TikTok storytelling channel, 450-600 words.
It must feel like a true personal experience: an ordinary setting, slowly rising dread, specific sensory details,
realistic dialogue and an unsettling ending that leaves one question unanswered.
No gore, no supernatural clichés like Ouija boards, no emojis.
```

`prompts/uyku_hikayesi.txt`:
```
Write an original, very calm bedtime story for adults who want to fall asleep, about {kelime} words.
Slow pace, gentle and cozy imagery, second-person or soft third-person narration, many small sensory details
(sounds of rain, warm light, textures, slow breathing). No conflict, no suspense, no sudden events, no dialogue-heavy scenes.
Each paragraph 3-5 sentences. Vary the setting every time (cabins, lighthouses, gardens, trains, libraries, seasides...).
```

- [ ] **Step 5: `zamanla.py`**

```python
"""Windows Görev Zamanlayıcı'ya günlük görev ekler/siler.
  python zamanla.py <kanal> --saat 09:00 --saat 18:00
  python zamanla.py <kanal> --saat 09:00 --sil
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent


def _dogrula(saat: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", saat):
        raise ValueError(f"Saat HH:MM biçiminde olmalı: {saat}")
    return saat


def gorev_adi(kanal: str, saat: str) -> str:
    return f"IcerikFabrikasi_{kanal}_{_dogrula(saat).replace(':', '')}"


def olustur_komutu(kanal: str, saat: str, python: Path, kok: Path) -> list[str]:
    tr = f'"{python}" "{kok / "calistir.py"}" {kanal}'
    return ["schtasks", "/Create", "/F", "/TN", gorev_adi(kanal, saat), "/SC", "DAILY", "/ST", saat, "/TR", tr]


def sil_komutu(kanal: str, saat: str) -> list[str]:
    return ["schtasks", "/Delete", "/F", "/TN", gorev_adi(kanal, saat)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("kanal")
    p.add_argument("--saat", action="append", required=True)
    p.add_argument("--sil", action="store_true")
    a = p.parse_args(argv)
    python = KOK / ".venv" / "Scripts" / "python.exe"
    for saat in a.saat:
        komut = sil_komutu(a.kanal, saat) if a.sil else olustur_komutu(a.kanal, saat, python, KOK)
        r = subprocess.run(komut, capture_output=True, text=True)
        print((r.stdout or r.stderr).strip())
        if r.returncode != 0:
            return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: `tasima.py`** (tek seferlik; eski repolardan medya, sırlar ve geçmiş)

```python
"""Eski repolardan tek seferlik taşıma. Tekrar çalıştırmak güvenlidir (var olanı atlar).
Büyük medya hardlink ile bağlanır (ek disk alanı yok); sırlar kopyalanır; hiçbir şey silinmez."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from core.ayar import KOK, db_yolu
from core.db import DB

TIKTOK = KOK.parent / "Tikok-Otomasyon"
YOUTUBE = KOK.parent / "Youtube-Otomasyon-GoogleTTS"

BAGLANTILAR = [
    (TIKTOK / "assets/background_videos/orbital_full_video.mp4", KOK / "assets/arka_plan/orbital.mp4"),
    (YOUTUBE / "assets/arka_plan.mp4", KOK / "assets/arka_plan/gece.mp4"),
    (YOUTUBE / "assets/yagmur.mp3", KOK / "assets/yagmur.mp3"),
]
KOPYALAR = [
    (YOUTUBE / "client_secret.json", KOK / "client_secret.json"),
    (YOUTUBE / "token.pickle", KOK / "veri/tokenlar/slumberlab.pickle"),
]


def bagla(kaynak: Path, hedef: Path) -> None:
    if hedef.exists():
        print(f"var, atlandı: {hedef}")
        return
    hedef.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(kaynak, hedef)
        print(f"hardlink: {hedef}")
    except OSError:
        shutil.copy2(kaynak, hedef)
        print(f"kopyalandı: {hedef}")


def main() -> None:
    for k, h in BAGLANTILAR:
        bagla(k, h) if k.exists() else print(f"KAYNAK YOK: {k}")
    for k, h in KOPYALAR:
        if not k.exists():
            print(f"KAYNAK YOK: {k}")
        elif h.exists():
            print(f"var, atlandı: {h}")
        else:
            h.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(k, h)
            print(f"kopyalandı: {h}")
    gecmis = TIKTOK / "database/posted_stories.json"
    if gecmis.exists():
        db = DB(db_yolu())
        kimlikler = set(json.loads(gecmis.read_text(encoding="utf-8")))
        for pid in kimlikler:
            db.hikaye_isaretle(f"reddit:{pid}", "eski_tiktok")
        print(f"{len(kimlikler)} eski hikâye kimliği DB'ye işlendi")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: `README.md`**

````markdown
# İçerik Fabrikası

TikTok ve YouTube için ücretsiz, kanal bazlı içerik otomasyonu: Reddit/LLM hikâyesi → Gemini senaryo → Edge-TTS/Kokoro ses → ffmpeg video → otomatik yükleme.

## Kurulum
```bash
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m playwright install chromium
```
`.env`: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (isteğe bağlı `GEMINI_MODEL`).
ffmpeg/ffprobe PATH'te olmalı. Eski repolardan taşıma: `.venv/Scripts/python.exe tasima.py`.

## Kullanım
```bash
.venv/Scripts/python.exe calistir.py tiktok_hikaye1 --giris   # bir kerelik TikTok girişi
.venv/Scripts/python.exe calistir.py tiktok_hikaye1 --kuru    # yüklemeden üret
.venv/Scripts/python.exe calistir.py tiktok_hikaye1           # tam çalıştırma
.venv/Scripts/python.exe calistir.py --ses-ornekleri          # ses örnekleri
.venv/Scripts/python.exe zamanla.py tiktok_hikaye1 --saat 19:00
```

## Yeni hesap / kanal
`kanallar/` altına yeni bir yaml koy (örnek: `ornek_tiktok_korku.yaml`), `--giris` ile oturum aç, `zamanla.py` ile saat ver.

## Sorun giderme
- Loglar: `veri/log/<kanal>.log`. TikTok hataları: `cikti/hatalar/` (ekran görüntüsü + HTML).
- TikTok arayüzü değiştiyse sadece `core/upload/tiktok_secici.py` güncellenir.
- Yarım kalan iş bir sonraki çalıştırmada kaldığı yerden devam eder; 3 başarısız denemeden sonra iptal edilir.
- TikTok zamanlama arayüzü sorun çıkarırsa kanal yaml'ında `parca2_yontem: bekle` kullan.
````

- [ ] **Step 8: Testler geçsin** — `PY -m pytest -q` → PASS

- [ ] **Step 9: Taşımayı çalıştır ve doğrula**

Run: `PY tasima.py`
Expected: 3 hardlink/kopya, 2 kopya, "N eski hikâye kimliği DB'ye işlendi". Sonra `git status --short` çıktısında `assets/`, `veri/`, `client_secret.json` görünmemeli (gitignore).

- [ ] **Step 10: Commit**

```bash
git add kanallar prompts zamanla.py tasima.py README.md tests/test_kanallar.py tests/test_zamanla.py
git commit -m "feat: kanal ayarlari, promptlar, zamanlama, tasima ve README"
```

---

### Task 13: Canlı doğrulama (kullanıcıyla birlikte)

Bu görev alt ajana verilmez; ana oturum kullanıcıyla yürütür. Kod değişikliği gerekirse (özellikle `tiktok_secici.py`) ilgili modülün testleri yeniden çalıştırılıp commit edilir.

- [ ] **Step 1: Ses örnekleri** — `PY calistir.py --ses-ornekleri`; kullanıcı `cikti/ses_ornekleri/` altındaki dosyaları dinleyip YouTube sesini seçer; `kanallar/youtube_slumberlab.yaml` `ses:` alanı güncellenir.
- [ ] **Step 2: YouTube kuru çalıştırma** — `PY calistir.py youtube_slumberlab --kuru`; üretilen `final.mp4`'ün süresi ~90 dk, hikâye 4-5 kez tekrar, arada yağmur; kullanıcı başından/ortasından/sonundan dinler.
- [ ] **Step 3: TikTok kuru çalıştırma** — `PY calistir.py tiktok_hikaye1 --kuru`; `part1.mp4`/`part2.mp4` altyazı senkronu ve görüntü kalitesi kullanıcıyla kontrol edilir.
- [ ] **Step 4: TikTok girişi** — kullanıcı `PY calistir.py tiktok_hikaye1 --giris` ile elle giriş yapar.
- [ ] **Step 5: Seçici kalibrasyonu** — yaml'da geçici `gorunurluk: sadece_ben`, `parca2_gecikme_dk: 20`; `PY calistir.py tiktok_hikaye1` kullanıcı izlerken çalıştırılır. Her başarısız adımda `cikti/hatalar/*.html` incelenir, `tiktok_secici.py` düzeltilir, tekrar çalıştırılır (yarım iş yükleme adımından devam eder). Hedef: Part 1 paylaşılır, etiketler mavi hashtag olur, Part 2 20 dk sonrasına zamanlanır. Zamanlama arayüzü çözülemezse `parca2_yontem: bekle` ile devam edilir ve kullanıcıya bildirilir.
- [ ] **Step 6: YouTube yetki ve ilk yükleme** — `PY calistir.py youtube_slumberlab` (private); eski `token.pickle` çalışmazsa `--giris`. YouTube Studio'da video kontrol edilir.
- [ ] **Step 7: Zamanlama** — kullanıcının seçtiği saatlerle `PY zamanla.py <kanal> --saat HH:MM`; yaml'lar kalıcı değerlere döndürülür (`gorunurluk: herkes`, `parca2_gecikme_dk: 120`).
- [ ] **Step 8: GitHub** — kullanıcı onayıyla `gh repo create BerkeBakir/icerik-fabrikasi --private --source . --push`. Eski repoların arşivlenmesi ayrıca kullanıcıya sorulur.
