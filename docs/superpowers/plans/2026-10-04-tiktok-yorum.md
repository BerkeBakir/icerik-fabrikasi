# TikTok Yorum Yöneticisi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TikTok yorumlarını otomatik işlemek: soru/yapıcı → cevap, sıradan yorum → beğeni, hakaret/spam → şikayet; yapıcıları kaydedip haftalık Telegram raporu.

**Architecture:** `core/yorum/` paketi üç katmana ayrılır: `siniflandir.py` (Gemini + küfür listesi, saf mantık), `yonetici.py` (akış, sınırlar, bildirim; tarayıcıyı bir arayüz üzerinden kullanır), `tiktok_yorum.py` (Playwright; seçiciler `core/upload/tiktok_secici.py`'de). Kalıcı durum SQLite `yorumlar` tablosunda. CLI `calistir.py <kanal> --yorumlar [--kuru]` ve `--yorum-raporu`; zamanlama `zamanla.py --ek ... [--haftalik GUN]`.

**Tech Stack:** Python 3.11, google-genai (mevcut `core.llm.Gemini`), Playwright (mevcut kalıcı Chrome profili), sqlite3, pytest.

Spec: `docs/superpowers/specs/2026-10-04-tiktok-yorum-design.md`

## Global Constraints

- Python yorumlayıcısı: `.venv/Scripts/python.exe` (planda `PY`). Testler: `PY -m pytest -q`, çıktı uyarısız olmalı.
- Tamamen ücretsiz: yeni ücretli servis/anahtar yok; LLM = mevcut `core.llm.Gemini.json_uret(prompt, sema, sicaklik)`.
- Türler tam olarak: `soru`, `yapici`, `yorum`, `hakaret`, `spam`. Konular tam olarak: `ses`, `altyazi`, `video`, `hikaye`, `uzunluk`, `diger`.
- Eylemler: `soru`→cevap, `yapici`→kayıt+cevap, `yorum`→beğeni, `hakaret`/`spam`→şikayet.
- Cevap ≤ 150 karakter (TikTok kutusu `maxlength=150`), link ve `#etiket` yok.
- Sınırlar (çalıştırma başına): cevap `en_fazla` (varsayılan 10), şikayet 5, beğeni 30, sınıflandırma 40. Beklemeler: cevap/şikayet 20-60 sn, beğeni 3-8 sn.
- Durumlar: `yeni`, `bekliyor`, `cevaplandi`, `begenildi`, `sikayet_edildi`, `atlandi`, `hata`. İkinci hata → `atlandi`.
- Üst üste 3 eylem hatası → çalıştırma durur, Telegram'a ekran görüntüsüyle bildirilir.
- TikTok tarayıcısı yalnız küresel kilit `core.kilit.dosya_kilidi(core.ayar.kilit_yolu())` altında açılır.
- Bildirim metinleri Türkçe, emoji önekleri: `💬` cevap, `🚩` şikayet, `🧾` özet, `📊` rapor, `⏭` atlandı, `🚨` hata.
- Tüm DOM seçicileri yalnız `core/upload/tiktok_secici.py`'de (mevcut `test_tiktok_py_secici_icermez` kuralı yeni Playwright dosyası için de geçerli).
- Kod/isimlendirme Türkçe, mevcut dosyaların üslubunda.

---

## Dosya Yapısı

| Dosya | Durum | Sorumluluk |
|---|---|---|
| `core/db.py` | değiştir | `Yorum` dataclass, `yorumlar` tablosu, `yorum_kimligi()`, erişim metotları, `son_isler()` |
| `core/ayar.py` | değiştir | `Kanal.yorum_aktif / yorum_en_fazla / yorum_hesap`, `yorum:` doğrulaması |
| `core/yorum/__init__.py` | yeni | `HamYorum`, `YorumIslemHatasi` |
| `core/yorum/siniflandir.py` | yeni | `Karar`, `kufurlu()`, `istem()`, `siniflandir()` |
| `core/yorum/yonetici.py` | yeni | `Ozet`, `yorumlari_isle()`, `rapor()` |
| `core/yorum/tiktok_yorum.py` | yeni | `TikTokYorumcu` (Playwright) |
| `core/upload/tiktok_secici.py` | değiştir | yorum sayfası seçicileri |
| `calistir.py` | değiştir | `--yorumlar`, `--yorum-raporu` |
| `zamanla.py` | değiştir | `--ek`, `--haftalik` |
| `kanallar/tiktok_hikaye1.yaml` | değiştir | `yorum: {aktif: true, en_fazla: 10, hesap: slumberlab}` |
| `tests/test_db.py`, `tests/test_ayar.py`, `tests/test_yorum_siniflandir.py`, `tests/test_yorum_yonetici.py`, `tests/test_yorum_tiktok.py`, `tests/test_calistir.py`, `tests/test_zamanla.py` | değiştir/yeni | testler |

---

### Task 1: Veri katmanı — `yorumlar` tablosu ve `yorum:` ayarı

**Files:**
- Modify: `core/db.py`
- Modify: `core/ayar.py` (Kanal dataclass ~satır 46-66, `kanal_yukle` TikTok dalı ~satır 139-150)
- Modify: `kanallar/tiktok_hikaye1.yaml`
- Test: `tests/test_db.py`, `tests/test_ayar.py`

**Interfaces:**
- Produces:
  - `core.db.yorum_kimligi(kanal: str, kullanici: str, metin: str, video: str) -> str` (16 hex karakter)
  - `core.db.Yorum` dataclass: `kimlik, kanal, kullanici, metin, video, tur, cevap, konu, oneri, durum, hata, deneme, tarih` (`tur/cevap/konu/oneri/hata` `str | None`, `deneme: int`, `tarih: str` ISO)
  - `DB.yorum_var_mi(kimlik) -> bool`
  - `DB.yorum_ekle(kimlik, kanal, kullanici, metin, video) -> Yorum` (durum `yeni`; varsa dokunmaz, mevcut kaydı döner)
  - `DB.yorum_getir(kimlik) -> Yorum`
  - `DB.yorum_karar(kimlik, tur, cevap, konu, oneri) -> Yorum` (durum `bekliyor`)
  - `DB.yorum_bitir(kimlik, durum) -> Yorum`
  - `DB.yorum_hata(kimlik, mesaj) -> Yorum` (deneme+1; deneme ≥ 2 → `atlandi`, değilse `hata`)
  - `DB.yorum_islenecekler(kanal) -> list[Yorum]` (durum ∈ yeni/bekliyor/hata, ekleme sırasıyla)
  - `DB.yorum_cevap_mi(kanal, metin) -> bool` (bu metin daha önce bizim gönderdiğimiz bir cevap mı)
  - `DB.yapici_yorumlar(kanal, baslangic: datetime) -> list[Yorum]` (tur=`yapici` ya da `oneri` dolu, tarih ≥ başlangıç)
  - `DB.son_isler(kanal, adet=60) -> list[Is]` (id azalan)
  - `Kanal.yorum_aktif: bool = False`, `Kanal.yorum_en_fazla: int = 10`, `Kanal.yorum_hesap: str | None = None`

- [ ] **Step 1: Write the failing tests** — `tests/test_db.py` sonuna ekle:

```python
from datetime import datetime, timedelta

from core.db import yorum_kimligi


def test_yorum_kimligi_kararli_ve_ayirt_edici():
    a = yorum_kimligi("k1", "ali", "Merhaba", "PART 1 | x")
    assert a == yorum_kimligi("k1", "ali", "Merhaba", "PART 1 | x")
    assert len(a) == 16
    assert a != yorum_kimligi("k1", "ali", "Merhaba", "PART 2 | x")
    assert a != yorum_kimligi("k2", "ali", "Merhaba", "PART 1 | x")


def test_yorum_yasam_dongusu(tmp_path):
    db = DB(tmp_path / "f.db")
    kim = yorum_kimligi("k1", "ali", "Is this real?", "PART 1 | x")
    assert not db.yorum_var_mi(kim)
    y = db.yorum_ekle(kim, "k1", "ali", "Is this real?", "PART 1 | x")
    assert y.durum == "yeni" and y.deneme == 0 and y.tur is None
    assert db.yorum_ekle(kim, "k1", "ali", "baska", "v").metin == "Is this real?"  # ikinci ekleme dokunmaz
    y = db.yorum_karar(kim, "soru", "Yes, it's from Reddit!", "", "")
    assert y.durum == "bekliyor" and y.tur == "soru" and y.cevap == "Yes, it's from Reddit!"
    assert [x.kimlik for x in db.yorum_islenecekler("k1")] == [kim]
    y = db.yorum_bitir(kim, "cevaplandi")
    assert y.durum == "cevaplandi" and db.yorum_islenecekler("k1") == []
    assert db.yorum_cevap_mi("k1", "Yes, it's from Reddit!")
    assert not db.yorum_cevap_mi("k2", "Yes, it's from Reddit!")


def test_yorum_hata_ikincide_atlanir(tmp_path):
    db = DB(tmp_path / "f.db")
    kim = yorum_kimligi("k1", "a", "b", "c")
    db.yorum_ekle(kim, "k1", "a", "b", "c")
    y = db.yorum_hata(kim, "buton yok")
    assert y.durum == "hata" and y.deneme == 1 and y.hata == "buton yok"
    assert [x.kimlik for x in db.yorum_islenecekler("k1")] == [kim]
    assert db.yorum_hata(kim, "yine yok").durum == "atlandi"


def test_yapici_yorumlar_tarihe_gore(tmp_path):
    db = DB(tmp_path / "f.db")
    for i, tur in enumerate(["yapici", "soru", "yapici"]):
        kim = yorum_kimligi("k1", f"u{i}", "m", "v")
        db.yorum_ekle(kim, "k1", f"u{i}", "m", "v")
        db.yorum_karar(kim, tur, "c", "ses" if tur == "yapici" else "", "Daha yavaş" if tur == "yapici" else "")
    simdi = datetime.now()
    assert len(db.yapici_yorumlar("k1", simdi - timedelta(days=7))) == 2
    assert db.yapici_yorumlar("k1", simdi + timedelta(days=1)) == []


def test_son_isler(tmp_path):
    db = DB(tmp_path / "f.db")
    a, b = db.is_olustur("k1"), db.is_olustur("k1")
    db.is_olustur("k2")
    assert [x.id for x in db.son_isler("k1")] == [b.id, a.id]
```

`tests/test_ayar.py` sonuna ekle:

```python
def test_yorum_ayari_varsayilan_kapali(tmp_path):
    yaz(tmp_path, "t1", TIKTOK)
    k = kanal_yukle("t1", kok=tmp_path)
    assert k.yorum_aktif is False and k.yorum_en_fazla == 10 and k.yorum_hesap is None


def test_yorum_ayari_okunur(tmp_path):
    yaz(tmp_path, "t1", TIKTOK + "yorum: {aktif: true, en_fazla: 7, hesap: '@SlumberLab'}\n")
    k = kanal_yukle("t1", kok=tmp_path)
    assert k.yorum_aktif is True and k.yorum_en_fazla == 7 and k.yorum_hesap == "slumberlab"


@pytest.mark.parametrize("ek,mesaj", [
    ("yorum: {aktif: true, en_fazla: 10}\n", "hesap"),
    ("yorum: {aktif: true, en_fazla: 0, hesap: x}\n", "en_fazla"),
    ("yorum: {aktif: true, en_fazla: 51, hesap: x}\n", "en_fazla"),
])
def test_yorum_ayari_dogrulanir(tmp_path, ek, mesaj):
    yaz(tmp_path, "t1", TIKTOK + ek)
    with pytest.raises(AyarHatasi, match=mesaj):
        kanal_yukle("t1", kok=tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PY -m pytest tests/test_db.py tests/test_ayar.py -q`
Expected: FAIL — `ImportError: cannot import name 'yorum_kimligi'` ve `AttributeError: ... 'yorum_aktif'`.

- [ ] **Step 3: Implement `core/db.py`**

Dosyanın başındaki importlara `import hashlib` ekle. `Is` dataclass'ından sonra ekle:

```python
YORUM_ISLENECEK = ("yeni", "bekliyor", "hata")


def yorum_kimligi(kanal: str, kullanici: str, metin: str, video: str) -> str:
    """Studio yorum kimliği vermediği için içerikten türetilen kararlı kimlik."""
    ham = "\x1f".join([kanal, kullanici.strip().lower(), metin.strip(), video.strip()])
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


@dataclass
class Yorum:
    kimlik: str
    kanal: str
    kullanici: str
    metin: str
    video: str
    tur: str | None
    cevap: str | None
    konu: str | None
    oneri: str | None
    durum: str
    hata: str | None
    deneme: int
    tarih: str
```

`DB.__init__` içindeki `executescript` metnine (isler tablosundan sonra) ekle:

```sql
            CREATE TABLE IF NOT EXISTS yorumlar (
                kimlik TEXT PRIMARY KEY, kanal TEXT NOT NULL, kullanici TEXT NOT NULL, metin TEXT NOT NULL,
                video TEXT NOT NULL, tur TEXT, cevap TEXT, konu TEXT, oneri TEXT,
                durum TEXT NOT NULL, hata TEXT, deneme INTEGER NOT NULL DEFAULT 0,
                tarih TEXT NOT NULL, guncelleme TEXT NOT NULL);
```

`DB` sınıfının sonuna ekle:

```python
    def son_isler(self, kanal: str, adet: int = 60) -> list[Is]:
        satirlar = self.bag.execute("SELECT * FROM isler WHERE kanal=? ORDER BY id DESC LIMIT ?", (kanal, adet))
        return [self._satir(r) for r in satirlar]

    # --- yorumlar ---
    def _yorum(self, r) -> Yorum:
        return Yorum(r["kimlik"], r["kanal"], r["kullanici"], r["metin"], r["video"], r["tur"], r["cevap"],
                     r["konu"], r["oneri"], r["durum"], r["hata"], r["deneme"], r["tarih"])

    def yorum_var_mi(self, kimlik: str) -> bool:
        return self.bag.execute("SELECT 1 FROM yorumlar WHERE kimlik=?", (kimlik,)).fetchone() is not None

    def yorum_getir(self, kimlik: str) -> Yorum:
        return self._yorum(self.bag.execute("SELECT * FROM yorumlar WHERE kimlik=?", (kimlik,)).fetchone())

    def yorum_ekle(self, kimlik: str, kanal: str, kullanici: str, metin: str, video: str) -> Yorum:
        self.bag.execute(
            "INSERT OR IGNORE INTO yorumlar (kimlik, kanal, kullanici, metin, video, durum, tarih, guncelleme) "
            "VALUES (?,?,?,?,?,'yeni',?,?)", (kimlik, kanal, kullanici, metin, video, _simdi(), _simdi()))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_karar(self, kimlik: str, tur: str, cevap: str, konu: str, oneri: str) -> Yorum:
        self.bag.execute(
            "UPDATE yorumlar SET tur=?, cevap=?, konu=?, oneri=?, durum='bekliyor', guncelleme=? WHERE kimlik=?",
            (tur, cevap, konu, oneri, _simdi(), kimlik))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_bitir(self, kimlik: str, durum: str) -> Yorum:
        self.bag.execute("UPDATE yorumlar SET durum=?, hata=NULL, guncelleme=? WHERE kimlik=?",
                         (durum, _simdi(), kimlik))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_hata(self, kimlik: str, mesaj: str) -> Yorum:
        mevcut = self.yorum_getir(kimlik)
        deneme = mevcut.deneme + 1
        durum = "atlandi" if deneme >= 2 else "hata"
        self.bag.execute("UPDATE yorumlar SET durum=?, hata=?, deneme=?, guncelleme=? WHERE kimlik=?",
                         (durum, mesaj[:2000], deneme, _simdi(), kimlik))
        self.bag.commit()
        return self.yorum_getir(kimlik)

    def yorum_islenecekler(self, kanal: str) -> list[Yorum]:
        satirlar = self.bag.execute(
            f"SELECT * FROM yorumlar WHERE kanal=? AND durum IN ({','.join('?' * len(YORUM_ISLENECEK))}) "
            "ORDER BY rowid", (kanal, *YORUM_ISLENECEK))
        return [self._yorum(r) for r in satirlar]

    def yorum_cevap_mi(self, kanal: str, metin: str) -> bool:
        return self.bag.execute("SELECT 1 FROM yorumlar WHERE kanal=? AND cevap=? AND durum='cevaplandi'",
                                (kanal, metin.strip())).fetchone() is not None

    def yapici_yorumlar(self, kanal: str, baslangic: datetime) -> list[Yorum]:
        satirlar = self.bag.execute(
            "SELECT * FROM yorumlar WHERE kanal=? AND (tur='yapici' OR COALESCE(oneri, '')<>'') AND tarih>=? "
            "ORDER BY rowid",
            (kanal, baslangic.isoformat(timespec="seconds")))
        return [self._yorum(r) for r in satirlar]
```

- [ ] **Step 4: Implement `core/ayar.py`**

`Kanal` dataclass'ına `arka_plan_kredi` satırından sonra ekle:

```python
    yorum_aktif: bool = False
    yorum_en_fazla: int = 10
    yorum_hesap: str | None = None
```

`kanal_yukle` içinde `kanal.arka_plan_kredi = ...` satırından hemen sonra (TikTok dalında) ekle:

```python
        yd = d.get("yorum") or {}
        kanal.yorum_aktif = bool(yd.get("aktif", False))
        kanal.yorum_en_fazla = int(yd.get("en_fazla", 10))
        kanal.yorum_hesap = (str(yd.get("hesap") or "").strip().lstrip("@").lower()) or None
        if kanal.yorum_aktif:
            if not 1 <= kanal.yorum_en_fazla <= 50:
                raise AyarHatasi(f"{yer}: yorum.en_fazla 1-50 arası olmalı")
            if not kanal.yorum_hesap:
                raise AyarHatasi(f"{yer}: yorum.hesap (kanalın TikTok kullanıcı adı) zorunlu")
```

- [ ] **Step 5: Kanal dosyası** — `kanallar/tiktok_hikaye1.yaml` sonuna ekle:

```yaml
yorum: {aktif: true, en_fazla: 10, hesap: slumberlab}   # calistir.py tiktok_hikaye1 --yorumlar
```

- [ ] **Step 6: Run tests**

Run: `PY -m pytest -q`
Expected: tümü PASS (yeni testler dahil), uyarı yok.

- [ ] **Step 7: Commit**

```bash
git add core/db.py core/ayar.py kanallar/tiktok_hikaye1.yaml tests/test_db.py tests/test_ayar.py
git commit -m "feat(yorum): yorumlar tablosu ve yorum ayarı"
```

---

### Task 2: Sınıflandırma — `core/yorum/siniflandir.py`

**Files:**
- Create: `core/yorum/__init__.py`
- Create: `core/yorum/siniflandir.py`
- Test: `tests/test_yorum_siniflandir.py`

**Interfaces:**
- Consumes: `llm.json_uret(prompt: str, sema: dict, sicaklik: float) -> dict` (mevcut `core.llm.Gemini`)
- Produces:
  - `core.yorum.HamYorum(kullanici: str, metin: str, video: str)` (frozen dataclass)
  - `core.yorum.YorumIslemHatasi(Exception)` — `__init__(mesaj, ekran: Path | None = None, yetki: bool = False)`
  - `core.yorum.siniflandir.TURLER`, `KONULAR`, `CEVAPLI = ("soru", "yapici")`
  - `Karar(tur: str, cevap: str, konu: str, oneri: str)` dataclass
  - `kufurlu(metin: str) -> bool`
  - `istem(yorum: HamYorum, baglam: str | None) -> str`
  - `siniflandir(llm, yorum: HamYorum, baglam: str | None = None) -> Karar`

- [ ] **Step 1: Write the failing tests** — `tests/test_yorum_siniflandir.py`:

```python
import pytest

from core.yorum import HamYorum, YorumIslemHatasi
from core.yorum.siniflandir import Karar, istem, kufurlu, siniflandir


class SahteLLM:
    def __init__(self, yanit):
        self.yanit = yanit
        self.cagri = []

    def json_uret(self, prompt, sema, sicaklik=0.8):
        self.cagri.append((prompt, sema, sicaklik))
        return self.yanit


Y = HamYorum("ali", "Is this story real?", "PART 1 | My first date")


def test_hata_sinifi_alanlari():
    e = YorumIslemHatasi("x")
    assert e.ekran is None and e.yetki is False


@pytest.mark.parametrize("metin", ["you stupid bitch", "kill yourself", "amk ya", "siktir git", "f u c k you",
                                   "fuck you", "Orospu çocuğu", "what a retard", "seni piç"])
def test_kufurlu_yakalar(metin):
    assert kufurlu(metin)


@pytest.mark.parametrize("metin", ["holy shit this story", "NTA, you're not the asshole", "Is this real?",
                                   "classic AITA", "amkara", "Sikinti yok", "nice pic"])
def test_kufurlu_genel_argoyu_ve_masumlari_gecer(metin):
    assert not kufurlu(metin)


def test_kufurlu_yorumda_llm_cagrilmaz():
    llm = SahteLLM({"tur": "soru", "cevap": "x"})
    k = siniflandir(llm, HamYorum("a", "fuck you", "v"))
    assert k == Karar("hakaret", "", "", "") and llm.cagri == []


def test_soru_cevabi_temizlenir_ve_kisaltilir():
    llm = SahteLLM({"tur": "soru", "cevap": "  Yes! See https://x.com #reddit " + "a" * 300})
    k = siniflandir(llm, Y)
    assert k.tur == "soru" and "http" not in k.cevap and "#" not in k.cevap
    assert k.cevap.startswith("Yes! See") and len(k.cevap) <= 150
    assert k.konu == "" and k.oneri == ""


def test_yapici_konu_ve_oneri():
    k = siniflandir(SahteLLM({"tur": "yapici", "cevap": "Thanks, noted!", "konu": "ses",
                              "oneri": "Narration should be slower."}), Y)
    assert k == Karar("yapici", "Thanks, noted!", "ses", "Narration should be slower.")


def test_yapici_gecersiz_konu_digere_duser():
    assert siniflandir(SahteLLM({"tur": "yapici", "cevap": "ok", "konu": "renk", "oneri": "x"}), Y).konu == "diger"


def test_gecersiz_tur_yoruma_duser():
    assert siniflandir(SahteLLM({"tur": "övgü"}), Y) == Karar("yorum", "", "", "")


@pytest.mark.parametrize("yanit", [{"tur": "soru", "cevap": "   "}, {"tur": "soru", "cevap": "go fuck yourself"}])
def test_bos_ya_da_kufurlu_cevap_begeniye_duser(yanit):
    assert siniflandir(SahteLLM(yanit), Y).tur == "yorum"


def test_bos_cevapli_yapici_kaydi_korunur():
    k = siniflandir(SahteLLM({"tur": "yapici", "cevap": "", "konu": "altyazi", "oneri": "Bigger subtitles"}), Y)
    assert k == Karar("yorum", "", "altyazi", "Bigger subtitles")


@pytest.mark.parametrize("tur", ["yorum", "hakaret", "spam"])
def test_cevapsiz_turlerde_cevap_bosaltilir(tur):
    assert siniflandir(SahteLLM({"tur": tur, "cevap": "lol"}), Y).cevap == ""


def test_istem_baglam_ve_kurallari_icerir():
    p = istem(Y, "Story hook: I found out on our first date.")
    assert "Is this story real?" in p and "@ali" in p and "PART 1 | My first date" in p
    assert "Story hook: I found out" in p and "150" in p
    assert "Story context: (none)" in istem(Y, None)


def test_sema_ve_sicaklik():
    llm = SahteLLM({"tur": "yorum"})
    siniflandir(llm, Y)
    _, sema, sicaklik = llm.cagri[0]
    assert sema["required"] == ["tur"] and set(sema["properties"]) == {"tur", "cevap", "konu", "oneri"}
    assert sicaklik == 0.4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PY -m pytest tests/test_yorum_siniflandir.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.yorum'`.

- [ ] **Step 3: Implement `core/yorum/__init__.py`**

```python
"""TikTok yorum yöneticisi: ortak türler."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HamYorum:
    """Studio yorum sayfasından okunan tek yorum."""
    kullanici: str
    metin: str
    video: str


class YorumIslemHatasi(Exception):
    """Tarayıcı eylemi başarısız. yetki=True: oturum kapalı ('--giris' gerekli)."""

    def __init__(self, mesaj: str, ekran: Path | None = None, yetki: bool = False):
        super().__init__(mesaj)
        self.ekran = ekran
        self.yetki = yetki
```

- [ ] **Step 4: Implement `core/yorum/siniflandir.py`**

```python
"""Yorum sınıflandırma ve cevap üretimi (Gemini) + küfür çift kontrolü."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.yorum import HamYorum

TURLER = ("soru", "yapici", "yorum", "hakaret", "spam")
KONULAR = ("ses", "altyazi", "video", "hikaye", "uzunluk", "diger")
CEVAPLI = ("soru", "yapici")
CEVAP_SINIR = 150

# Genel argo ("holy shit") değil; hakaret/aşağılama kalıpları. Kelime sınırıyla eşleşir.
_KUFUR = [
    r"f+\W*u+\W*c+\W*k+\W*(you|u|off|yourself)", r"cunts?", r"bitch(es)?", r"whores?", r"sluts?",
    r"retard(ed|s)?", r"kys", r"kill\s+your\s*self", r"n[i1]gg(a|er)s?", r"f[a@]gg?ots?", r"motherfucker",
    r"amk", r"aq", r"orospu\w*", r"siktir\w*", r"sikeyim", r"s[iı]k[iı]m", r"piç(ler)?", r"yarra[kğ]\w*",
    r"anan[iı]\s*s\w*", r"g[oö]t\s*veren", r"gerizekal[iı]\w*", r"şerefsiz\w*", r"serefsiz\w*",
]
_KUFUR_DESENI = re.compile(r"(?<!\w)(" + "|".join(_KUFUR) + r")(?!\w)", re.IGNORECASE)

SEMA = {
    "type": "object",
    "properties": {
        "tur": {"type": "string", "enum": list(TURLER)},
        "cevap": {"type": "string"},
        "konu": {"type": "string", "enum": list(KONULAR)},
        "oneri": {"type": "string"},
    },
    "required": ["tur"],
}

ISTEM = """You manage comments for a TikTok storytelling channel. The channel narrates stories adapted from Reddit
over gameplay footage, usually in two parts (Part 1 / Part 2).

Classify the comment and, when needed, write a reply.

"tur" (exactly one):
- "soru": a question about the story, the characters or the channel.
- "yapici": constructive feedback or a suggestion about the videos (voice, subtitles, video, story, length).
- "yorum": praise, an opinion, a reaction, a judgment like NTA/YTA, an emoji, anything else harmless.
- "hakaret": insults, slurs, harassment or hate aimed at anyone.
- "spam": ads, self-promotion, "follow me", links, scams, gibberish.

"cevap": ONLY for "soru" and "yapici", otherwise empty. Rules:
- Same language as the comment, friendly and natural, at most {sinir} characters, at most one emoji.
- No links, no hashtags, no @mentions.
- Never claim the story happened to you; the stories come from Reddit. Never share personal information.
- Do not argue. For "yapici" thank them and say you'll consider it.

"konu" and "oneri": ONLY for "yapici". "konu" is one of {konular}. "oneri" is the suggestion as one short
English sentence. Otherwise empty.

Video caption: {video}
Story context: {baglam}
Comment by @{kullanici}: {metin}
"""


@dataclass
class Karar:
    tur: str
    cevap: str
    konu: str
    oneri: str


def kufurlu(metin: str) -> bool:
    return bool(_KUFUR_DESENI.search(metin or ""))


def _temiz_cevap(metin: str) -> str:
    metin = re.sub(r"https?://\S+|www\.\S+", "", metin or "")
    metin = re.sub(r"[#@]\w+", "", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    if len(metin) > CEVAP_SINIR:
        metin = metin[:CEVAP_SINIR].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return metin


def istem(yorum: HamYorum, baglam: str | None) -> str:
    return ISTEM.format(sinir=CEVAP_SINIR, konular=", ".join(KONULAR), video=yorum.video,
                        baglam=baglam or "(none)", kullanici=yorum.kullanici, metin=yorum.metin)


def siniflandir(llm, yorum: HamYorum, baglam: str | None = None) -> Karar:
    if kufurlu(yorum.metin):
        return Karar("hakaret", "", "", "")
    v = llm.json_uret(istem(yorum, baglam), SEMA, sicaklik=0.4)
    tur = v.get("tur") if v.get("tur") in TURLER else "yorum"
    konu = oneri = ""
    if tur == "yapici":
        konu = v.get("konu") if v.get("konu") in KONULAR else "diger"
        oneri = (v.get("oneri") or "").strip()[:200]
    cevap = _temiz_cevap(v.get("cevap") or "") if tur in CEVAPLI else ""
    if tur in CEVAPLI and (not cevap or kufurlu(cevap)):
        tur, cevap = "yorum", ""
    return Karar(tur, cevap, konu, oneri)
```

- [ ] **Step 5: Run tests**

Run: `PY -m pytest tests/test_yorum_siniflandir.py -q`, sonra `PY -m pytest -q`
Expected: PASS, uyarı yok.

- [ ] **Step 6: Commit**

```bash
git add core/yorum/__init__.py core/yorum/siniflandir.py tests/test_yorum_siniflandir.py
git commit -m "feat(yorum): Gemini sınıflandırma ve küfür çift kontrolü"
```

---

### Task 3: Akış — `core/yorum/yonetici.py`

**Files:**
- Create: `core/yorum/yonetici.py`
- Test: `tests/test_yorum_yonetici.py`

**Interfaces:**
- Consumes: Task 1 (`DB` yorum metotları, `yorum_kimligi`, `son_isler`, `Kanal.yorum_*`), Task 2 (`HamYorum`, `YorumIslemHatasi`, `siniflandir`, `Karar`).
- Tarayıcı arayüzü (Task 5 bunu sağlar): `yorumcu.oturum()` bir context manager'dır ve şu metotları olan nesne verir:
  `oku() -> list[HamYorum]`, `cevapla(y: HamYorum, metin: str) -> None`, `begen(y: HamYorum) -> None`,
  `sikayet_et(y: HamYorum, tur: str) -> None`. Hatalarda `YorumIslemHatasi` fırlatır.
- Produces:
  - `Ozet` dataclass: `cevap=0, begeni=0, sikayet=0, hata=0, bekleyen=0` + `metin(kanal_ad) -> str`
  - `yorumlari_isle(kanal, db, llm, yorumcu, bildirim, log, kuru=False, uyku=time.sleep, rastgele=random) -> Ozet`
  - `rapor(kanal, db, bildirim, simdi: datetime) -> str`
  - `SINIRLAR` sabitleri: `SIKAYET_SINIR = 5`, `BEGENI_SINIR = 30`, `SINIFLANDIRMA_SINIR = 40`, `ARDISIK_HATA_SINIR = 3`

- [ ] **Step 1: Write the failing tests** — `tests/test_yorum_yonetici.py`:

```python
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

from core.ayar import Kanal, Kaynak, Ses
from core.db import DB, yorum_kimligi
from core.yorum import HamYorum, YorumIslemHatasi
from core.yorum import yonetici as yon

LOG = logging.getLogger("test")


def kanal(en_fazla=10):
    k = Kanal(ad="t1", platform="tiktok", kaynak=Kaynak("reddit", ["A"]), ses=Ses("edge", "v", "+0%"),
              arka_plan=Path("bg.mp4"), gorunurluk="herkes", profil="p1")
    k.yorum_aktif, k.yorum_en_fazla, k.yorum_hesap = True, en_fazla, "slumberlab"
    return k


class SahteLLM:
    """Yorum metnindeki anahtar kelimeye göre karar döner."""
    def __init__(self, patlat=()):
        self.cagri = 0
        self.patlat = patlat

    def json_uret(self, prompt, sema, sicaklik=0.8):
        self.cagri += 1
        metin = prompt.rsplit(":", 1)[-1]
        if any(p in metin for p in self.patlat):
            raise RuntimeError("503")
        if "?" in metin:
            return {"tur": "soru", "cevap": "Good question!"}
        if "slower" in metin:
            return {"tur": "yapici", "cevap": "Thanks, noted!", "konu": "ses", "oneri": "Slower narration."}
        if "follow me" in metin:
            return {"tur": "spam"}
        return {"tur": "yorum"}


class SahteSayfa:
    def __init__(self, yorumlar, bozuk=()):
        self.yorumlar = yorumlar
        self.bozuk = bozuk
        self.eylemler = []

    def oku(self):
        return list(self.yorumlar)

    def _yap(self, ad, y, *ek):
        if y.metin in self.bozuk:
            raise YorumIslemHatasi(f"{ad} başarısız", ekran=Path("e.png"))
        self.eylemler.append((ad, y.kullanici, *ek))

    def cevapla(self, y, metin):
        self._yap("cevap", y, metin)

    def begen(self, y):
        self._yap("begen", y)

    def sikayet_et(self, y, tur):
        self._yap("sikayet", y, tur)


class SahteYorumcu:
    def __init__(self, sayfa):
        self.sayfa = sayfa

    @contextmanager
    def oturum(self):
        yield self.sayfa


class SahteBildirim:
    def __init__(self):
        self.mesajlar, self.fotolar = [], []

    def mesaj(self, m):
        self.mesajlar.append(m)

    def foto(self, yol, m):
        self.fotolar.append((yol, m))


def calistir(tmp_path, yorumlar, llm=None, k=None, bozuk=(), kuru=False, db=None):
    db = db or DB(tmp_path / "f.db")
    sayfa = SahteSayfa(yorumlar, bozuk)
    b = SahteBildirim()
    uykular = []
    ozet = yon.yorumlari_isle(k or kanal(), db, llm or SahteLLM(), SahteYorumcu(sayfa), b, LOG, kuru=kuru,
                              uyku=uykular.append)
    return ozet, sayfa, b, db, uykular


def H(kullanici, metin, video="PART 1 | x"):
    return HamYorum(kullanici, metin, video)


def test_turlere_gore_eylem_ve_bildirim(tmp_path):
    yorumlar = [H("a", "Is this real?"), H("b", "please talk slower"), H("c", "love it"),
                H("d", "follow me pls"), H("e", "fuck you")]
    ozet, sayfa, b, db, uykular = calistir(tmp_path, yorumlar)
    assert sayfa.eylemler == [("cevap", "a", "Good question!"), ("cevap", "b", "Thanks, noted!"),
                              ("begen", "c"), ("sikayet", "d", "spam"), ("sikayet", "e", "hakaret")]
    assert (ozet.cevap, ozet.begeni, ozet.sikayet, ozet.hata) == (2, 1, 2, 0)
    assert sum(m.startswith("💬") for m in b.mesajlar) == 2
    assert sum(m.startswith("🚩") for m in b.mesajlar) == 2
    assert b.mesajlar[-1].startswith("🧾") and "2 cevap" in b.mesajlar[-1]
    assert '"Is this real?"' in b.mesajlar[0] and '↳ "Good question!"' in b.mesajlar[0]
    durumlar = {y.kullanici: y.durum for y in map(db.yorum_getir, [yorum_kimligi("t1", y.kullanici, y.metin,
                                                                                  y.video) for y in yorumlar])}
    assert durumlar == {"a": "cevaplandi", "b": "cevaplandi", "c": "begenildi", "d": "sikayet_edildi",
                        "e": "sikayet_edildi"}
    assert len(uykular) == 5


def test_ayni_yorum_ikinci_calistirmada_islenmez(tmp_path):
    y = [H("a", "Is this real?")]
    _, _, _, db, _ = calistir(tmp_path, y)
    llm = SahteLLM()
    ozet, sayfa, b, _, _ = calistir(tmp_path, y, llm=llm, db=db)
    assert sayfa.eylemler == [] and llm.cagri == 0 and b.mesajlar == []


def test_kendi_yorumumuz_ve_cevabimiz_atlanir(tmp_path):
    y = [H("a", "Is this real?")]
    _, _, _, db, _ = calistir(tmp_path, y)
    ozet, sayfa, _, _, _ = calistir(tmp_path, [H("SlumberLab", "anything"), H("x", "Good question!")], db=db)
    assert sayfa.eylemler == []


def test_cevap_siniri_tasanlar_bekler(tmp_path):
    y = [H(f"u{i}", f"q{i}?") for i in range(4)]
    ozet, sayfa, _, db, _ = calistir(tmp_path, y, k=kanal(en_fazla=2))
    assert ozet.cevap == 2 and ozet.bekleyen == 2
    llm = SahteLLM()
    ozet, sayfa, _, _, _ = calistir(tmp_path, y, llm=llm, k=kanal(en_fazla=2), db=db)
    assert ozet.cevap == 2 and llm.cagri == 0  # bekleyenler yeniden sınıflandırılmaz


def test_sikayet_siniri(tmp_path):
    y = [H(f"u{i}", f"follow me {i}") for i in range(7)]
    ozet, *_ = calistir(tmp_path, y)
    assert ozet.sikayet == yon.SIKAYET_SINIR and ozet.bekleyen == 2


def test_llm_hatasi_yorumu_yeni_birakir(tmp_path):
    y = [H("a", "boom?"), H("b", "Is this real?")]
    ozet, sayfa, _, db, _ = calistir(tmp_path, y, llm=SahteLLM(patlat=("boom",)))
    assert sayfa.eylemler == [("cevap", "b", "Good question!")]
    assert db.yorum_getir(yorum_kimligi("t1", "a", "boom?", "PART 1 | x")).durum == "yeni"


def test_eylem_hatasi_kaydedilir_sonra_atlanir(tmp_path):
    y = [H("a", "Is this real?")]
    ozet, _, _, db, _ = calistir(tmp_path, y, bozuk=("Is this real?",))
    kim = yorum_kimligi("t1", "a", "Is this real?", "PART 1 | x")
    assert ozet.hata == 1 and db.yorum_getir(kim).durum == "hata"
    calistir(tmp_path, y, bozuk=("Is this real?",), db=db)
    assert db.yorum_getir(kim).durum == "atlandi"


def test_ardisik_uc_hata_durdurur_ve_ekran_gonderir(tmp_path):
    y = [H(f"u{i}", f"q{i}?") for i in range(5)]
    with pytest.raises(YorumIslemHatasi):
        calistir(tmp_path, y, bozuk=tuple(f"q{i}?" for i in range(5)))


def test_ardisik_hata_bildirimi(tmp_path):
    db = DB(tmp_path / "f.db")
    b = SahteBildirim()
    sayfa = SahteSayfa([H(f"u{i}", f"q{i}?") for i in range(5)], bozuk=tuple(f"q{i}?" for i in range(5)))
    with pytest.raises(YorumIslemHatasi):
        yon.yorumlari_isle(kanal(), db, SahteLLM(), SahteYorumcu(sayfa), b, LOG, uyku=lambda s: None)
    assert len(b.fotolar) == 1 and "3" in b.fotolar[0][1]


def test_yetki_hatasi_hemen_yukselir(tmp_path):
    class YetkisizSayfa(SahteSayfa):
        def cevapla(self, y, metin):
            raise YorumIslemHatasi("oturum kapalı", yetki=True)
    db = DB(tmp_path / "f.db")
    with pytest.raises(YorumIslemHatasi) as e:
        yon.yorumlari_isle(kanal(), db, SahteLLM(), SahteYorumcu(YetkisizSayfa([H("a", "q?")])),
                           SahteBildirim(), LOG, uyku=lambda s: None)
    assert e.value.yetki


def test_kuru_mod_eylemsiz_ve_kayitsiz(tmp_path):
    y = [H("a", "Is this real?"), H("e", "fuck you")]
    ozet, sayfa, b, db, _ = calistir(tmp_path, y, kuru=True)
    assert sayfa.eylemler == [] and b.mesajlar == [] and db.yorum_islenecekler("t1") == []


def test_baglam_eslesen_isten_gelir(tmp_path):
    db = DB(tmp_path / "f.db")
    is_ = db.is_olustur("t1")
    db.is_ilerlet(is_.id, "yuklendi", senaryo={"hook": "I found out on our first date.",
                                               "aciklama": "My first date with this guy seemed a little off."})
    assert "I found out" in yon.baglam_bul(db, "t1", "PART 1 | My first date with this guy seemed a little…")
    assert yon.baglam_bul(db, "t1", "PART 1 | Something else") is None


def test_hic_eylem_yoksa_ozet_gonderilmez(tmp_path):
    ozet, _, b, _, _ = calistir(tmp_path, [])
    assert b.mesajlar == []


def test_rapor_konuya_gore_gruplar(tmp_path):
    db = DB(tmp_path / "f.db")
    for i, (konu, oneri) in enumerate([("ses", "Slower"), ("ses", "Less robotic"), ("hikaye", "Part 3")]):
        kim = yorum_kimligi("t1", f"u{i}", "m", "v")
        db.yorum_ekle(kim, "t1", f"u{i}", "m", "v")
        db.yorum_karar(kim, "yapici", "c", konu, oneri)
    b = SahteBildirim()
    m = yon.rapor(kanal(), db, b, datetime.now())
    assert m.startswith("📊") and "(3)" in m
    assert m.index("• ses (2)") < m.index("• hikaye (1)") and '"Slower"' in m
    assert b.mesajlar == [m]


def test_rapor_bos(tmp_path):
    b = SahteBildirim()
    assert "yapıcı yorum yok" in yon.rapor(kanal(), DB(tmp_path / "f.db"), b, datetime.now())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PY -m pytest tests/test_yorum_yonetici.py -q`
Expected: FAIL — `ImportError: cannot import name 'yonetici'`.

- [ ] **Step 3: Implement `core/yorum/yonetici.py`**

```python
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
from core.yorum.siniflandir import siniflandir

SIKAYET_SINIR = 5
BEGENI_SINIR = 30
SINIFLANDIRMA_SINIR = 40
ARDISIK_HATA_SINIR = 3

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
                   uyku=time.sleep, rastgele=random) -> Ozet:
    ozet = Ozet()
    with yorumcu.oturum() as sayfa:
        hamlar = sayfa.oku()
        log.info("%d yorum okundu", len(hamlar))
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
            if h is None:  # artık listede değil (7 günden eski ya da silinmiş)
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
                db.yorum_hata(y.kimlik, str(e))
                ozet.hata += 1
                ardisik_hata += 1
                log.warning("Eylem başarısız (@%s, %s): %s", h.kullanici, eylem, e)
                if ardisik_hata >= ARDISIK_HATA_SINIR:
                    mesaj = f"🚨 [{kanal.ad}] Yorum işleme durdu: üst üste {ardisik_hata} hata. Son hata: {e}"
                    if e.ekran:
                        bildirim.foto(e.ekran, mesaj)
                    else:
                        bildirim.mesaj(mesaj)
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
```

- [ ] **Step 4: Run tests**

Run: `PY -m pytest tests/test_yorum_yonetici.py -q`, sonra `PY -m pytest -q`
Expected: PASS, uyarı yok.

- [ ] **Step 5: Commit**

```bash
git add core/yorum/yonetici.py tests/test_yorum_yonetici.py
git commit -m "feat(yorum): yorum işleme akışı, sınırlar, bildirimler ve haftalık rapor"
```

---

### Task 4: CLI ve zamanlama — `--yorumlar`, `--yorum-raporu`, `zamanla --ek/--haftalik`

**Files:**
- Modify: `calistir.py`
- Modify: `zamanla.py`
- Test: `tests/test_calistir.py`, `tests/test_zamanla.py`

**Interfaces:**
- Consumes: Task 3 `yorumlari_isle`, `rapor`; Task 5'in sağlayacağı `core.yorum.tiktok_yorum.TikTokYorumcu(profil_dir, hata_dir, log, hesap)` (bu task'ta yalnız `calistir._yorumcu(kanal, log)` fabrikası içinde, tembel import ile kullanılır; testlerde fabrika sahte ile değiştirilir).
- Produces:
  - `calistir._yorumcu(kanal, log)` → yorumcu nesnesi (Task 5 sınıfı)
  - `calistir._yorumlar(kanal, log, kuru: bool) -> int` (exit kodu)
  - `calistir._yorum_raporu(kanal, log) -> int`
  - `zamanla.gorev_adi(kanal, saat, ek="", gun=None)`, `zamanla.olustur_komutu(kanal, saat, python, kok, ek="", gun=None)`, `zamanla.sil_komutu(kanal, saat, ek="", gun=None)`

- [ ] **Step 1: Write the failing tests**

`tests/test_calistir.py` sonuna ekle:

```python
class _Bildirim:
    mesajlar = []

    def __init__(self, *a, **kw):
        pass

    def mesaj(self, m):
        _Bildirim.mesajlar.append(m)


@pytest.fixture
def yorum_ortami(ortam, monkeypatch):
    k = calistir.kanal_yukle("t1")
    k.yorum_aktif, k.yorum_hesap = True, "kanal"
    _Bildirim.mesajlar = []
    monkeypatch.setattr(calistir, "Bildirim", _Bildirim)
    monkeypatch.setattr(calistir, "ortam", lambda anahtar, zorunlu=True: "x")
    monkeypatch.setattr(calistir, "kilit_yolu", lambda: calistir.KOK / "veri" / "tiktok.kilit")
    monkeypatch.setattr(calistir, "_yorumcu", lambda kanal, log: "YORUMCU")
    monkeypatch.setattr("core.llm.Gemini", lambda *a, **kw: "LLM")
    return k


def test_yorumlar_bayragi_akisi_cagirir(yorum_ortami, monkeypatch):
    cagri = {}

    def sahte(kanal, db, llm, yorumcu, bildirim, log, kuru=False):
        cagri.update(kanal=kanal.ad, llm=llm, yorumcu=yorumcu, kuru=kuru)
    monkeypatch.setattr("core.yorum.yonetici.yorumlari_isle", sahte)
    assert calistir.main(["t1", "--yorumlar"]) == 0
    assert cagri == {"kanal": "t1", "llm": "LLM", "yorumcu": "YORUMCU", "kuru": False}
    assert calistir.main(["t1", "--yorumlar", "--kuru"]) == 0 and cagri["kuru"] is True


def test_yorumlar_kapaliysa_ayar_hatasi(yorum_ortami):
    yorum_ortami.yorum_aktif = False
    assert calistir.main(["t1", "--yorumlar"]) == 2


def test_yorumlar_yetki_hatasi_bildirir(yorum_ortami, monkeypatch):
    from core.yorum import YorumIslemHatasi

    def patla(*a, **kw):
        raise YorumIslemHatasi("oturum kapalı", yetki=True)
    monkeypatch.setattr("core.yorum.yonetici.yorumlari_isle", patla)
    assert calistir.main(["t1", "--yorumlar"]) == 1
    assert any("--giris" in m for m in _Bildirim.mesajlar)


def test_yorumlar_kilit_doluysa_atlar(yorum_ortami, monkeypatch):
    from core.kilit import KilitHatasi

    def dolu(*a, **kw):
        raise KilitHatasi("dolu")
    monkeypatch.setattr(calistir, "dosya_kilidi", dolu)
    assert calistir.main(["t1", "--yorumlar"]) == 0
    assert _Bildirim.mesajlar and _Bildirim.mesajlar[0].startswith("⏭")


def test_yorum_raporu_bayragi(yorum_ortami, monkeypatch):
    monkeypatch.setattr("core.yorum.yonetici.rapor", lambda kanal, db, b, simdi: "📊 rapor")
    assert calistir.main(["t1", "--yorum-raporu"]) == 0


def test_yorumlar_diger_bayraklarla_birlesmez(yorum_ortami):
    with pytest.raises(SystemExit):
        calistir.main(["t1", "--yorumlar", "--giris"])
    with pytest.raises(SystemExit):
        calistir.main(["t1", "--yorumlar", "--yorum-raporu"])
```

`tests/test_zamanla.py` sonuna ekle:

```python
def test_ek_bayrak_komuta_ve_ada_eklenir():
    k = zamanla.olustur_komutu("t1", "10:00", Path("C:/v/python.exe"), Path("D:/p"), ek="--yorumlar")
    assert k[k.index("/TN") + 1] == "IcerikFabrikasi_t1_yorumlar_1000"
    assert k[k.index("/TR") + 1].endswith(" t1 --yorumlar")
    assert k[k.index("/SC") + 1] == "DAILY"


def test_haftalik_gorev():
    k = zamanla.olustur_komutu("t1", "12:00", Path("p"), Path("k"), ek="--yorum-raporu", gun="SUN")
    assert k[k.index("/SC") + 1] == "WEEKLY" and k[k.index("/D") + 1] == "SUN"
    assert k[k.index("/TN") + 1] == "IcerikFabrikasi_t1_yorumraporu_SUN_1200"
    assert zamanla.sil_komutu("t1", "12:00", ek="--yorum-raporu", gun="SUN")[-1] == "IcerikFabrikasi_t1_yorumraporu_SUN_1200"


def test_gecersiz_gun():
    with pytest.raises(ValueError):
        zamanla.olustur_komutu("t1", "12:00", Path("p"), Path("k"), gun="PAZ")


def test_main_ek_ve_haftalik(monkeypatch):
    cagrilar = _yakala(monkeypatch)
    assert zamanla.main(["t1", "--saat", "12:00", "--ek=--yorum-raporu", "--haftalik", "SUN"]) == 0
    assert "WEEKLY" in cagrilar[0][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PY -m pytest tests/test_calistir.py tests/test_zamanla.py -q`
Expected: FAIL — bilinmeyen bayrak `--yorumlar` (SystemExit 2) ve `unexpected keyword argument 'ek'`.

- [ ] **Step 3: Implement `zamanla.py`** — dosyanın tamamını şununla değiştir:

```python
"""Windows Görev Zamanlayıcı'ya günlük/haftalık görev ekler/siler.
  python zamanla.py <kanal> --saat 09:00 --saat 18:00
  python zamanla.py <kanal> --saat 10:00 --ek=--yorumlar
  python zamanla.py <kanal> --saat 12:00 --ek=--yorum-raporu --haftalik SUN
  python zamanla.py <kanal> --saat 09:00 --sil
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
GUNLER = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def _dogrula(saat: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", saat):
        raise ValueError(f"Saat HH:MM biçiminde olmalı: {saat}")
    return saat


def _gun(gun: str | None) -> str | None:
    if gun is not None and gun not in GUNLER:
        raise ValueError(f"Gün şunlardan biri olmalı: {', '.join(GUNLER)}")
    return gun


def gorev_adi(kanal: str, saat: str, ek: str = "", gun: str | None = None) -> str:
    parcalar = ["IcerikFabrikasi", kanal]
    if ek:
        parcalar.append(re.sub(r"[^a-z0-9]", "", ek.lower()))
    if _gun(gun):
        parcalar.append(gun)
    parcalar.append(_dogrula(saat).replace(":", ""))
    return "_".join(parcalar)


def olustur_komutu(kanal: str, saat: str, python: Path, kok: Path, ek: str = "", gun: str | None = None) -> list[str]:
    tr = f'"{python}" "{kok / "calistir.py"}" {kanal}' + (f" {ek}" if ek else "")
    siklik = ["/SC", "WEEKLY", "/D", gun] if _gun(gun) else ["/SC", "DAILY"]
    return ["schtasks", "/Create", "/F", "/TN", gorev_adi(kanal, saat, ek, gun), *siklik, "/ST", saat, "/TR", tr]


def sil_komutu(kanal: str, saat: str, ek: str = "", gun: str | None = None) -> list[str]:
    return ["schtasks", "/Delete", "/F", "/TN", gorev_adi(kanal, saat, ek, gun)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("kanal")
    p.add_argument("--saat", action="append", required=True)
    p.add_argument("--ek", default="", help="calistir.py'ye eklenecek bayrak, ör. --ek=--yorumlar")
    p.add_argument("--haftalik", choices=GUNLER, help="haftalık görev günü (yoksa günlük)")
    p.add_argument("--sil", action="store_true")
    a = p.parse_args(argv)
    python = KOK / ".venv" / "Scripts" / "python.exe"
    for saat in a.saat:
        if a.sil:
            komut = sil_komutu(a.kanal, saat, a.ek, a.haftalik)
        else:
            komut = olustur_komutu(a.kanal, saat, python, KOK, a.ek, a.haftalik)
        r = subprocess.run(komut, capture_output=True, text=True, encoding="oem", errors="replace")
        print((r.stdout or r.stderr).strip())
        if r.returncode != 0:
            return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Implement `calistir.py`**

Modül docstring'ine iki satır ekle:

```
  python calistir.py <kanal> --yorumlar [--kuru]   TikTok yorumlarını işle (--kuru: sadece oku/sınıflandır)
  python calistir.py <kanal> --yorum-raporu        son 7 günün yapıcı yorumlarını Telegram'a raporla
```

Importları güncelle:

```python
from core.ayar import (KOK, AyarHatasi, client_secret_yolu, db_yolu, eski_token_yolu, hata_klasoru,
                       kanal_yukle, kilit_yolu, ortam, ortami_yukle, profil_yolu, token_yolu)
from core.kilit import KilitHatasi, dosya_kilidi
```

`_gemini_modelleri` fonksiyonundan sonra ekle:

```python
def _yorumcu(kanal, log):
    from core.yorum.tiktok_yorum import TikTokYorumcu

    return TikTokYorumcu(profil_yolu(kanal), hata_klasoru(), log, hesap=kanal.yorum_hesap)


def _yorumlar(kanal, log, kuru: bool) -> int:
    from core.llm import Gemini
    from core.yorum import YorumIslemHatasi
    from core.yorum import yonetici

    if kanal.platform != "tiktok" or not kanal.yorum_aktif:
        print(f"[{kanal.ad}] Yorum işleme kapalı (kanal dosyasında 'yorum: {{aktif: true, ...}}' gerekli)")
        return 2
    bildirim = Bildirim(ortam("TELEGRAM_BOT_TOKEN", False), ortam("TELEGRAM_CHAT_ID", False), log)
    try:
        with dosya_kilidi(kilit_yolu(), bekle_sn=1800):
            llm = Gemini(ortam("GEMINI_API_KEY"), modeller=_gemini_modelleri(), log=log)
            yonetici.yorumlari_isle(kanal, DB(db_yolu()), llm, _yorumcu(kanal, log), bildirim, log, kuru=kuru)
    except KilitHatasi:
        log.info("TikTok tarayıcısı meşgul, yorum çalıştırması atlandı")
        if not kuru:
            bildirim.mesaj(f"⏭ [{kanal.ad}] TikTok meşgul, yorum çalıştırması atlandı")
        return 0
    except YorumIslemHatasi as e:
        log.error("Yorum işleme hatası: %s", e)
        if e.yetki and not kuru:
            bildirim.mesaj(f"🚨 [{kanal.ad}] TikTok oturumu kapalı: 'calistir.py {kanal.ad} --giris' çalıştır")
        return 1
    except Exception as e:
        log.exception("Yorum işleme beklenmeyen hata")
        if not kuru:
            bildirim.mesaj(f"🚨 [{kanal.ad}] Yorum işleme hatası: {type(e).__name__}: {e}")
        return 1
    return 0


def _yorum_raporu(kanal, log) -> int:
    from core.yorum import yonetici

    bildirim = Bildirim(ortam("TELEGRAM_BOT_TOKEN", False), ortam("TELEGRAM_CHAT_ID", False), log)
    log.info(yonetici.rapor(kanal, DB(db_yolu()), bildirim, datetime.now()))
    return 0
```

`main` içinde, `g` grubundan sonra (grubun dışında) ekle:

```python
    p.add_argument("--yorumlar", action="store_true", help="TikTok yorumlarını işle (--kuru ile birleşebilir)")
    p.add_argument("--yorum-raporu", action="store_true", help="haftalık yapıcı yorum raporu")
```

`a = p.parse_args(argv)` satırından hemen sonra ekle:

```python
    if a.yorumlar and a.yorum_raporu:
        p.error("--yorumlar ve --yorum-raporu birlikte kullanılamaz")
    if (a.yorumlar or a.yorum_raporu) and (a.giris or a.ses_ornekleri or a.onayla or a.yeniden_dene):
        p.error("--yorumlar/--yorum-raporu yalnız --kuru ile birleşebilir")
    if a.yorum_raporu and a.kuru:
        p.error("--yorum-raporu --kuru ile kullanılmaz")
```

`if a.onayla or a.yeniden_dene: return _onay(kanal, a.onayla)` satırından sonra ekle:

```python
    if a.yorumlar:
        return _yorumlar(kanal, log, a.kuru)
    if a.yorum_raporu:
        return _yorum_raporu(kanal, log)
```

- [ ] **Step 5: Run tests**

Run: `PY -m pytest tests/test_calistir.py tests/test_zamanla.py -q`, sonra `PY -m pytest -q`
Expected: PASS, uyarı yok. (`core.yorum.tiktok_yorum` henüz yok; testler `_yorumcu`'yu sahteyle değiştirdiği için import edilmez.)

- [ ] **Step 6: Commit**

```bash
git add calistir.py zamanla.py tests/test_calistir.py tests/test_zamanla.py
git commit -m "feat(yorum): --yorumlar/--yorum-raporu CLI ve zamanla --ek/--haftalik"
```

---

### Task 5: Playwright katmanı — `core/yorum/tiktok_yorum.py`

**Files:**
- Modify: `core/upload/tiktok_secici.py` (yorum seçicileri)
- Create: `core/yorum/tiktok_yorum.py`
- Test: `tests/test_yorum_tiktok.py`

**Interfaces:**
- Consumes: `core.upload.tiktok.TikTokYukleyici` yardımcıları (`_baslat_sarmali`, `_popuplari_kapat`, `_gorunurse`, `_ekran_kaydet`) — kalıtımla yeniden kullanılır; `core.upload.tiktok_secici` (`s`); `HamYorum`, `YorumIslemHatasi`.
- Produces: `TikTokYorumcu(profil_dir: Path, hata_dir: Path, log=None, hesap: str | None = None, headless=False)`;
  `oturum()` context manager → `YorumSayfasi` (`oku()`, `cevapla(y, metin)`, `begen(y)`, `sikayet_et(y, tur)`);
  saf yardımcılar `yas_gun(metin: str) -> float | None`, `video_yolu_bul(satirlar: list[tuple[str, str]], video: str) -> str | None`.

**Bilinen DOM (2026-10-04 canlı inceleme, `cikti/duman/yorum/`):**
- Yorum hücresi `div[data-tt="components_CommentCell_FlexColumn"]`; kullanıcı `a[data-tt="components_MessageCell_a"]` (href `/@kullanici`); metin `span[data-tt="components_TUXTextWithMention_TUXText"]`; zaman `span[data-tt="components_MessageCell_span_20"]` ("2h ago"); hücredeki `[data-tt="components_MessageCell_TUXText"]` öğelerinin sonuncusu video başlığı; ilk `button[data-tt="components_MessageCell_Clickable"]` kalp (beğeni), `HeartFill` ikonu beğenilmiş hâli.
- "Reply" metnine tıklayınca `textarea#comment-input` (maxlength 150, placeholder "Reply to comment") açılır.
- Studio'da Report yok. İçerik listesinde (`/tiktokstudio/content`) her gönderi `a[href^="/@<hesap>/video/<id>"]`.
- Doğrulanmamış (Step 6'da kalibre edilecek): cevabı gönderme (Enter mi, buton mu), beğeni sonrası durum, video sayfasında yorum ⋯ menüsü → Report → sebep → Submit.

- [ ] **Step 1: Seçicileri ekle** — `core/upload/tiktok_secici.py` sonuna:

```python
# --- Yorumlar (TikTok Studio /tiktokstudio/comment) ---
YORUM_URL = "https://www.tiktok.com/tiktokstudio/comment?lang=en"
ICERIK_URL = "https://www.tiktok.com/tiktokstudio/content?lang=en"
YORUM_HUCRE = 'div[data-tt="components_CommentCell_FlexColumn"]'
YORUM_KULLANICI = 'a[data-tt="components_MessageCell_a"]'
YORUM_METIN = 'span[data-tt="components_TUXTextWithMention_TUXText"]'
YORUM_ZAMAN = 'span[data-tt="components_MessageCell_span_20"]'
YORUM_VIDEO = '[data-tt="components_MessageCell_TUXText"]'  # hücredeki SONUNCUSU video başlığı
YORUM_BEGEN = 'button[data-tt="components_MessageCell_Clickable"]'  # hücredeki İLKİ kalp
YORUM_BEGENILDI = '[data-icon="HeartFill"]:visible'
YORUM_CEVAP_METNI = "Reply"
YORUM_CEVAP_KUTU = "textarea#comment-input"
YORUM_CEVAP_GONDER = 'button:has-text("Post")'  # kutu yanındaki gönder düğmesi (yoksa Enter)
ICERIK_VIDEO_LINK = 'a[href*="/video/"]'
TIKTOK_KOK = "https://www.tiktok.com"
# Video sayfası (tiktok.com/@hesap/video/<id>) — şikayet
VIDEO_YORUM_OGE = '[data-e2e="comment-level-1"]'
VIDEO_YORUM_MENU = '[data-e2e="comment-more-icon"], [aria-label*="more" i]'
VIDEO_SIKAYET_METNI = "Report"
VIDEO_SIKAYET_SEBEP = {"hakaret": ["Harassment or bullying", "Hate and harassment", "Hate speech"],
                       "spam": ["Spam", "Frauds and scams"]}
VIDEO_SIKAYET_GONDER = 'button:has-text("Submit")'
VIDEO_SIKAYET_TAMAM = ['text=/thanks for reporting/i', 'text=/report submitted/i', 'button:has-text("Done")']
```

- [ ] **Step 2: Write the failing tests** — `tests/test_yorum_tiktok.py`:

```python
import pytest

from core.yorum.tiktok_yorum import video_yolu_bul, yas_gun


@pytest.mark.parametrize("metin,gun", [("2h ago", 2 / 24), ("35m ago", 35 / 1440), ("3d ago", 3.0),
                                       ("1w ago", 7.0), ("Just now", 0.0), ("now", 0.0)])
def test_yas_gun(metin, gun):
    assert yas_gun(metin) == pytest.approx(gun)


@pytest.mark.parametrize("metin", ["10-01", "2026-09-12", ""])
def test_yas_gun_tarih_bilinmez(metin):
    assert yas_gun(metin) is None


def test_video_yolu_bul():
    satirlar = [("/@slumberlab/video/111", "PART 2 (Final) | Our financial stress is at an all-time high"),
                ("/@slumberlab/video/222", "PART 1 | Our financial stress is at an all-time high")]
    assert video_yolu_bul(satirlar, "PART 1 | Our financial stress is at an all-ti…") == "/@slumberlab/video/222"
    assert video_yolu_bul(satirlar, "PART 2 (Final) | Our financial") == "/@slumberlab/video/111"
    assert video_yolu_bul(satirlar, "PART 1 | Something else") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PY -m pytest tests/test_yorum_tiktok.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.yorum.tiktok_yorum'`.

- [ ] **Step 4: Implement `core/yorum/tiktok_yorum.py`**

```python
"""TikTok Studio yorumları: okuma, cevap, beğeni; video sayfasından şikayet. Seçiciler tiktok_secici.py'de."""
from __future__ import annotations

import random
import re
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from core.upload import tiktok_secici as s
from core.upload.tiktok import TikTokHatasi, TikTokYukleyici
from core.yorum import HamYorum, YorumIslemHatasi

AZAMI_YAS_GUN = 7
_BIRIM = {"m": 1 / 1440, "h": 1 / 24, "d": 1.0, "w": 7.0}


def yas_gun(metin: str) -> float | None:
    """'2h ago' → 0.083; 'Just now' → 0; tarih ('10-01') ya da bilinmeyen → None (eski sayılır)."""
    m = (metin or "").strip().lower()
    if m in ("just now", "now"):
        return 0.0
    r = re.fullmatch(r"(\d+)\s*([mhdw])\w*\s+ago", m)
    return int(r.group(1)) * _BIRIM[r.group(2)] if r else None


def _govde(metin: str) -> str:
    return re.sub(r"\s+", " ", metin).strip().rstrip("…").rstrip(".").strip().lower()


def video_yolu_bul(satirlar: list[tuple[str, str]], video: str) -> str | None:
    """İçerik listesindeki (href, açıklama) satırlarından yorumun videosunu bulur (kesik başlık önek eşleşir)."""
    hedef = _govde(video)
    if len(hedef) < 10:
        return None
    for href, aciklama in satirlar:
        if _govde(aciklama).startswith(hedef):
            return href
    return None


class TikTokYorumcu(TikTokYukleyici):
    """Yükleyicinin tarayıcı/profil yardımcılarını yeniden kullanır."""

    def __init__(self, profil_dir: Path, hata_dir: Path, log=None, hesap: str | None = None, headless: bool = False):
        super().__init__(profil_dir, hata_dir, log, headless)
        self.hesap = hesap

    @contextmanager
    def oturum(self):
        with sync_playwright() as p:
            try:
                ctx, sayfa = self._baslat_sarmali(p)
            except TikTokHatasi as e:
                raise YorumIslemHatasi(str(e)) from e
            try:
                sayfa.goto(s.YORUM_URL)
                time.sleep(random.uniform(4, 6))
                if s.GIRIS_YOLU in sayfa.url:
                    raise YorumIslemHatasi("TikTok oturumu kapalı", yetki=True)
                self._popuplari_kapat(sayfa)
                yield YorumSayfasi(self, ctx, sayfa)
            finally:
                self._tarayici_kapat(ctx)


class YorumSayfasi:
    def __init__(self, yorumcu: TikTokYorumcu, ctx, sayfa):
        self.y = yorumcu
        self.ctx = ctx
        self.sayfa = sayfa
        self._video_satirlari: list[tuple[str, str]] | None = None

    # --- yardımcılar ---
    def _hata(self, mesaj: str, ad: str) -> YorumIslemHatasi:
        return YorumIslemHatasi(mesaj, ekran=self.y._ekran_kaydet(self.sayfa, ad))

    def _hucre(self, y: HamYorum):
        hucreler = self.sayfa.locator(s.YORUM_HUCRE).filter(
            has=self.sayfa.locator(s.YORUM_KULLANICI).filter(has_text=re.compile(rf"^\s*{re.escape(y.kullanici)}\s*$"))
        ).filter(has=self.sayfa.locator(s.YORUM_METIN).filter(has_text=y.metin[:60]))
        if not hucreler.count():
            raise self._hata(f"Yorum sayfada bulunamadı: @{y.kullanici}", "yorum_yok")
        return hucreler.first

    # --- okuma ---
    def oku(self, en_fazla: int = 100) -> list[HamYorum]:
        hucreler = self.sayfa.locator(s.YORUM_HUCRE)
        self.y._gorunurse(hucreler.first, 10_000)
        sonuc: list[HamYorum] = []
        for i in range(min(hucreler.count(), en_fazla)):
            h = hucreler.nth(i)
            try:
                yas = yas_gun(h.locator(s.YORUM_ZAMAN).first.inner_text(timeout=2000))
                if yas is None or yas > AZAMI_YAS_GUN:
                    continue
                kullanici = h.locator(s.YORUM_KULLANICI).first.inner_text(timeout=2000).strip().lstrip("@")
                metin = h.locator(s.YORUM_METIN).first.inner_text(timeout=2000).strip()
                video = h.locator(s.YORUM_VIDEO).last.inner_text(timeout=2000).strip()
            except Exception as e:
                self.y.log.warning("Yorum satırı okunamadı (%d): %s", i, e)
                continue
            if kullanici and metin:
                sonuc.append(HamYorum(kullanici, metin, video))
        return sonuc

    # --- eylemler ---
    def cevapla(self, y: HamYorum, metin: str) -> None:
        hucre = self._hucre(y)
        try:
            hucre.get_by_text(s.YORUM_CEVAP_METNI, exact=True).first.click()
            kutu = self.sayfa.locator(s.YORUM_CEVAP_KUTU).first
            kutu.wait_for(state="visible", timeout=5000)
            kutu.click()
            self.y._yaz(self.sayfa, metin)
            time.sleep(random.uniform(0.5, 1.2))
            gonder = self.sayfa.locator(s.YORUM_CEVAP_GONDER).first
            if self.y._gorunurse(gonder, 1000):
                gonder.click()
            else:
                self.sayfa.keyboard.press("Enter")
            self.sayfa.wait_for_function(
                "s => { const k = document.querySelector(s); return !k || k.value === ''; }",
                arg=s.YORUM_CEVAP_KUTU, timeout=10_000)
        except YorumIslemHatasi:
            raise
        except Exception as e:
            raise self._hata(f"Cevap gönderilemedi (@{y.kullanici}): {e}", "yorum_cevap") from e

    def begen(self, y: HamYorum) -> None:
        hucre = self._hucre(y)
        try:
            if hucre.locator(s.YORUM_BEGENILDI).count():
                return
            hucre.locator(s.YORUM_BEGEN).first.click()
            hucre.locator(s.YORUM_BEGENILDI).first.wait_for(state="attached", timeout=5000)
        except Exception as e:
            raise self._hata(f"Beğenilemedi (@{y.kullanici}): {e}", "yorum_begen") from e

    def _video_yolu(self, video: str) -> str | None:
        if self._video_satirlari is None:
            self.sayfa.goto(s.ICERIK_URL)
            time.sleep(random.uniform(4, 6))
            linkler = self.sayfa.locator(s.ICERIK_VIDEO_LINK)
            satirlar = []
            for i in range(linkler.count()):
                a = linkler.nth(i)
                href = a.get_attribute("href") or ""
                if self.y.hesap and f"/@{self.y.hesap}/video/" not in href:
                    continue
                satirlar.append((href, a.inner_text(timeout=2000)))
            self._video_satirlari = satirlar
        return video_yolu_bul(self._video_satirlari, video)

    def sikayet_et(self, y: HamYorum, tur: str) -> None:
        yol = self._video_yolu(y.video)
        if not yol:
            raise self._hata(f"Yorumun videosu bulunamadı: {y.video[:40]}", "sikayet_video")
        vs = self.ctx.new_page()
        try:
            vs.goto(s.TIKTOK_KOK + yol)
            time.sleep(random.uniform(5, 7))
            oge = vs.locator(s.VIDEO_YORUM_OGE).filter(has_text=y.metin[:60]).first
            oge.wait_for(state="visible", timeout=15_000)
            oge.hover()
            oge.locator(s.VIDEO_YORUM_MENU).first.click()
            vs.get_by_text(s.VIDEO_SIKAYET_METNI, exact=True).first.click()
            time.sleep(random.uniform(1, 2))
            for sebep in s.VIDEO_SIKAYET_SEBEP[tur]:
                secenek = vs.get_by_text(sebep, exact=True).first
                if self.y._gorunurse(secenek, 1500):
                    secenek.click()
                    break
            else:
                raise RuntimeError(f"şikayet sebebi bulunamadı: {tur}")
            time.sleep(random.uniform(1, 2))
            vs.locator(s.VIDEO_SIKAYET_GONDER).first.click()
            if not any(self.y._gorunurse(vs.locator(x).first, 8000) for x in s.VIDEO_SIKAYET_TAMAM):
                raise RuntimeError("şikayet onayı görülmedi")
        except Exception as e:
            raise YorumIslemHatasi(f"Şikayet edilemedi (@{y.kullanici}): {e}",
                                   ekran=self.y._ekran_kaydet(vs, "yorum_sikayet")) from e
        finally:
            vs.close()
```

- [ ] **Step 5: Run tests**

Run: `PY -m pytest tests/test_yorum_tiktok.py -q`, sonra `PY -m pytest -q`
Expected: PASS, uyarı yok; `test_tiktok_py_secici_icermez` hâlâ geçer.

- [ ] **Step 6: Canlı kalibrasyon (eylemsiz)** — kontrolcü (ana oturum) çalıştırır, alt ajan değil:

Run: `PYTHONIOENCODING=utf-8 PY calistir.py tiktok_hikaye1 --yorumlar --kuru`
Expected: `N yorum okundu` ve her yorum için `[kuru] @kullanici: '…' → tur '…'` satırları; hiçbir eylem yok. Okuma başarısızsa `cikti/hatalar/` ekran görüntülerine bakıp yalnız `tiktok_secici.py`'yi düzelt.

- [ ] **Step 7: Commit**

```bash
git add core/upload/tiktok_secici.py core/yorum/tiktok_yorum.py tests/test_yorum_tiktok.py
git commit -m "feat(yorum): TikTok Studio yorum okuma, cevap, beğeni ve şikayet (Playwright)"
```

---

### Task 6: Canlı devreye alma (kontrolcü + kullanıcı)

Alt ajana verilmez; ana oturum kullanıcıyla yürütür.

- [ ] **Step 1:** Kullanıcı ekrana dokunmadan izlerken ilk gerçek tur: `PY calistir.py tiktok_hikaye1 --yorumlar`. Beklenen: mevcut yorum(lar) işlenir, Telegram'da `💬`/`🧾` mesajları. Cevap gönderme/beğeni başarısızsa ekran görüntüsünden `YORUM_CEVAP_GONDER` / `YORUM_BEGENILDI` düzeltilir, yeniden denenir.
- [ ] **Step 2:** Şikayet akışı ilk `hakaret`/`spam` yorumunda doğrulanır. Video sayfasında Report bulunamazsa kullanıcıya "şikayet yerine Studio'dan silelim mi?" diye sorulur (spec'teki yedek).
- [ ] **Step 3:** Zamanlama:

```bash
PY zamanla.py tiktok_hikaye1 --saat 10:00 --saat 14:00 --saat 17:00 --saat 23:00 --ek=--yorumlar
PY zamanla.py tiktok_hikaye1 --saat 12:00 --ek=--yorum-raporu --haftalik SUN
```

Ardından görevlerin pilde çalışması ve kaçırılanın çalışması (mevcut görevlerle aynı PowerShell ayarı):

```bash
powershell.exe -NoProfile -Command "Get-ScheduledTask -TaskName 'IcerikFabrikasi_*' | ForEach-Object { $s = $_.Settings; $s.DisallowStartIfOnBatteries = $false; $s.StopIfGoingOnBatteries = $false; $s.StartWhenAvailable = $true; $s.ExecutionTimeLimit = 'PT6H'; Set-ScheduledTask -TaskName $_.TaskName -Settings $s | Out-Null }"
```

YouTube görevleri (`IcerikFabrikasi_youtube_slumberlab_*`) devre dışı kalmalı; ayar değişikliği `Enabled` durumunu değiştirmez, `schtasks /Query` ile doğrulanır.
- [ ] **Step 4:** `README.md`'ye "Yorumlar" bölümü (komutlar, zamanlama, ayar) eklenir; commit + push (`gelistirme` ve `master`).
