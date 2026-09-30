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
