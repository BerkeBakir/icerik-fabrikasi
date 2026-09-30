import logging
from datetime import datetime
from pathlib import Path

import pytest

from core.ayar import Etiketler, Kanal, Kaynak, Ses, calisma_kilidi_yolu
from core.db import DB
from core.is_akisi import Baglam, OnayGerekli, calistir, onayla, yeniden_dene
from core.kilit import dosya_kilidi
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
    def __init__(self, patla=0, hatalar=None):
        self.yuklemeler = []
        self.patla = patla
        self.hatalar = list(hatalar or [])

    def yukle(self, video, aciklama, etiketler, gorunurluk, zaman=None):
        if self.hatalar:
            hata = self.hatalar.pop(0)
            if hata is not None:
                raise hata
        if self.patla:
            self.patla -= 1
            raise RuntimeError("tiktok coktu")
        self.yuklemeler.append((Path(video).name, aciklama, etiketler, gorunurluk, zaman))
        return zaman


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


def test_ayni_kanal_ikinci_calistirma_cikar(tmp_path):
    tt = SahteTikTok()
    b = baglam(tmp_path, tiktok_kanal(), tt)
    with dosya_kilidi(calisma_kilidi_yolu(b.kanal, tmp_path)):
        assert calistir(b) is None
    assert b.db.yarim_is("t1") is None
    assert tt.yuklemeler == []
    assert b.bildirim.mesajlar == ["⏭ [t1] Kanal zaten çalışıyor, bu çalıştırma atlandı"]


def test_kuru_calistirma_kilitliyse_bildirim_yok(tmp_path):
    b = baglam(tmp_path, tiktok_kanal(), SahteTikTok(), kuru=True)
    with dosya_kilidi(calisma_kilidi_yolu("t1", tmp_path)):
        assert calistir(b) is None
    assert b.bildirim.mesajlar == []


def test_baslangic_mesaji_kilitten_sonra_gonderilir(tmp_path):
    b = baglam(tmp_path, tiktok_kanal(), SahteTikTok())
    calistir(b)
    assert b.bildirim.mesajlar[0] == "🚀 [t1] Çalışma başladı"
    kuru = baglam(tmp_path / "k", tiktok_kanal(), SahteTikTok(), kuru=True)
    calistir(kuru)
    assert not any(m.startswith("🚀") for m in kuru.bildirim.mesajlar)


def test_bildirilen_hata_isaretlenir(tmp_path):
    b = baglam(tmp_path, tiktok_kanal(), SahteTikTok(patla=1))
    with pytest.raises(RuntimeError) as h:
        calistir(b)
    assert h.value.bildirildi is True


def test_kuru_mod_hikayeyi_tuketmez_ve_her_seferinde_yeniden_uretir(tmp_path):
    tt = SahteTikTok()
    kaynak = SahteKaynak()
    b = baglam(tmp_path, tiktok_kanal(), tt, kaynak=kaynak, kuru=True)
    k1 = calistir(b)
    k2 = calistir(b)
    assert kaynak.cagri == 2 and k1.id != k2.id
    assert not b.db.hikaye_kullanildi_mi("reddit:abc")
    assert b.db.yarim_is("t1") is None
    assert b.db.is_getir(k1.id).durum == "iptal"
    b.kuru = False
    gercek = calistir(b)
    assert gercek.id not in (k1.id, k2.id) and gercek.durum == "yuklendi"
    assert len(tt.yuklemeler) == 2


def test_part2_bildirimi_etkin_zamani_kullanir(tmp_path):
    class Tazeleyen(SahteTikTok):
        def yukle(self, video, aciklama, etiketler, gorunurluk, zaman=None):
            super().yukle(video, aciklama, etiketler, gorunurluk, zaman)
            return datetime(2026, 9, 29, 14, 5) if zaman else None

    b = baglam(tmp_path, tiktok_kanal(), Tazeleyen())
    is_ = calistir(b)
    assert is_.veri["parca2_zaman"].startswith("2026-09-29T14:05")
    assert "29.09 14:05" in b.bildirim.mesajlar[-1]


def test_render_oncesi_iptal_edilen_isin_klasoru_silinir(tmp_path):
    def bozuk_render(arka_plan, ses, cikti, rastgele=None):
        raise RuntimeError("render coktu")

    b = baglam(tmp_path, tiktok_kanal(), SahteTikTok())
    b.render_tiktok = bozuk_render
    for _ in range(3):
        with pytest.raises(RuntimeError):
            calistir(b)
    is_ = b.db.is_getir(1)
    assert is_.durum == "iptal"
    assert not (tmp_path / "cikti" / "t1" / f"is_{is_.id}").exists()
    assert "iptal edildi" in b.bildirim.mesajlar[-1]


def test_render_sonrasi_iptal_edilen_isin_klasoru_korunur(tmp_path):
    b = baglam(tmp_path, tiktok_kanal(), SahteTikTok(patla=99))
    for _ in range(3):
        with pytest.raises(RuntimeError):
            calistir(b)
    is_ = b.db.is_getir(1)
    klasor = tmp_path / "cikti" / "t1" / f"is_{is_.id}"
    assert is_.durum == "iptal"
    assert (klasor / "part1.mp4").exists()
    assert "iptal edildi" in b.bildirim.mesajlar[-1] and str(klasor) in b.bildirim.mesajlar[-1]


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


class SahteYuklemeHatasi(Exception):
    def __init__(self, mesaj="dogrulanamadi", gonderildi=False, ekran=None):
        super().__init__(mesaj)
        self.gonderildi = gonderildi
        self.ekran = ekran


def _uyarilar(b):
    return [m for m in b.bildirim.mesajlar if "doğrulanamadı" in m]


def test_dogrulanamayan_part1_onay_bekler_ve_tekrar_yuklenmez(tmp_path):
    tt = SahteTikTok(hatalar=[SahteYuklemeHatasi(gonderildi=True)])
    b = baglam(tmp_path, tiktok_kanal(), tt)
    with pytest.raises(OnayGerekli):
        calistir(b)
    is_ = b.db.yarim_is("t1")
    assert is_.durum == "video_hazir" and is_.veri["bekleyen_onay"] == "part1" and is_.deneme == 0
    uyarilar = _uyarilar(b)
    assert len(uyarilar) == 1 and "Part 1" in uyarilar[0] and "--onayla" in uyarilar[0]
    assert not any("🚨" in m for m in b.bildirim.mesajlar)
    onceki = list(b.bildirim.mesajlar)

    with pytest.raises(OnayGerekli):
        calistir(b)
    assert tt.yuklemeler == []
    assert not any("doğrulanamadı" in m or "🚨" in m for m in b.bildirim.mesajlar[len(onceki):])
    assert b.db.is_getir(is_.id).deneme == 0

    onaylanan = onayla(b.db, "t1", tmp_path, datetime(2026, 9, 29, 12, 30))
    assert onaylanan.durum == "parca1_yuklendi" and onaylanan.veri["bekleyen_onay"] is None
    assert onaylanan.veri["parca1_zaman"] == "2026-09-29T12:30:00"
    son = calistir(b)
    assert son.durum == "yuklendi"
    assert [y[0] for y in tt.yuklemeler] == ["part2.mp4"]


def test_dogrulanamayan_part2_onaylaninca_biter_ve_klasor_silinir(tmp_path):
    tt = SahteTikTok(hatalar=[None, SahteYuklemeHatasi(gonderildi=True)])
    b = baglam(tmp_path, tiktok_kanal(), tt)
    with pytest.raises(OnayGerekli):
        calistir(b)
    is_ = b.db.yarim_is("t1")
    assert is_.durum == "parca1_yuklendi" and is_.veri["bekleyen_onay"] == "part2"
    assert "Part 2" in _uyarilar(b)[0]
    klasor = tmp_path / "cikti" / "t1" / f"is_{is_.id}"
    assert klasor.exists()
    bitti = onayla(b.db, "t1", tmp_path, datetime(2026, 9, 29, 12, 30))
    assert bitti.durum == "yuklendi" and bitti.veri["bekleyen_onay"] is None
    assert not klasor.exists()
    assert b.db.yarim_is("t1") is None


def test_yeniden_dene_bayragi_temizler_ve_part1_tekrar_yuklenir(tmp_path):
    tt = SahteTikTok(hatalar=[SahteYuklemeHatasi(gonderildi=True)])
    b = baglam(tmp_path, tiktok_kanal(), tt)
    with pytest.raises(OnayGerekli):
        calistir(b)
    temiz = yeniden_dene(b.db, "t1")
    assert temiz.durum == "video_hazir" and temiz.veri["bekleyen_onay"] is None
    assert calistir(b).durum == "yuklendi"
    assert [y[0] for y in tt.yuklemeler] == ["part1.mp4", "part2.mp4"]


def test_onay_bekleyen_is_yoksa_none(tmp_path):
    db = DB(tmp_path / "f.db")
    assert onayla(db, "t1", tmp_path, datetime(2026, 9, 29)) is None
    assert yeniden_dene(db, "t1") is None
    db.is_olustur("t1")
    assert onayla(db, "t1", tmp_path, datetime(2026, 9, 29)) is None
    assert yeniden_dene(db, "t1") is None


def test_tiklama_oncesi_hata_normal_deneme_sayilir(tmp_path):
    tt = SahteTikTok(hatalar=[SahteYuklemeHatasi("buton yok", gonderildi=False)])
    b = baglam(tmp_path, tiktok_kanal(), tt)
    with pytest.raises(SahteYuklemeHatasi):
        calistir(b)
    is_ = b.db.yarim_is("t1")
    assert is_.deneme == 1 and "bekleyen_onay" not in is_.veri
    assert "buton yok" in b.bildirim.mesajlar[-1]


def test_yetki_hatasi_deneme_yakmaz_ve_klasoru_korur(tmp_path):
    hata = SahteYuklemeHatasi("TikTok oturumu kapalı")
    hata.yetki = True
    tt = SahteTikTok(hatalar=[hata, hata, hata, hata])
    b = baglam(tmp_path, tiktok_kanal(), tt)
    for _ in range(4):
        with pytest.raises(SahteYuklemeHatasi):
            calistir(b)
    is_ = b.db.yarim_is("t1")
    assert is_ is not None and is_.durum == "video_hazir" and is_.deneme == 0
    assert "oturumu kapalı" in is_.hata
    assert (tmp_path / "cikti" / "t1" / f"is_{is_.id}" / "part1.mp4").exists()
    anahtar = [m for m in b.bildirim.mesajlar if m.startswith("🔑")]
    assert len(anahtar) == 4 and "calistir.py t1 --giris" in anahtar[0]
    assert not any("🚨" in m for m in b.bildirim.mesajlar)
    assert calistir(b).durum == "yuklendi"


def test_youtube_yetki_hatasi_deneme_yakmaz(tmp_path):
    kanal = Kanal(ad="y1", platform="youtube", kaynak=Kaynak("uretim", prompt=tmp_path / "p.txt", kelime=100),
                  ses=Ses("kokoro", "af_heart", 0.85), arka_plan=Path("bg.mp4"), gorunurluk="private",
                  token="tok", ortam_sesi=Path("r.mp3"))
    (tmp_path / "p.txt").write_text("Write {kelime} words", encoding="utf-8")

    def render_youtube(arka_plan, hikaye_ses, ortam, seviye, tekrar, ara_sn, hedef_sn, cikti):
        Path(cikti).parent.mkdir(parents=True, exist_ok=True)
        Path(cikti).write_bytes(b"v")
        return 4

    def youtube_yukleyici(kanal, video, baslik, aciklama, etiketler):
        from core.upload.youtube import YukleHatasi
        raise YukleHatasi("YouTube yetkisi yok ya da geçersiz", yetki=True)

    b = Baglam(kanal=kanal, db=DB(tmp_path / "f.db"), llm=SahteLLM(), bildirim=SahteBildirim(), log=LOG,
               kok=tmp_path, tts_fabrika=lambda ses, log=None: SahteTTS(),
               render_youtube=render_youtube, youtube_yukleyici=youtube_yukleyici)
    with pytest.raises(Exception, match="yetkisi"):
        calistir(b)
    is_ = b.db.yarim_is("y1")
    assert is_.deneme == 0 and is_.durum == "video_hazir"
    assert b.bildirim.mesajlar[-1].startswith("🔑 [y1] Oturum/yetki gerekli")


def test_ayni_calistirmada_render_edilip_iptal_edilen_is_klasoru_korunur(tmp_path):
    sayac = {"n": 0}

    def iki_kez_bozuk(arka_plan, ses, cikti, rastgele=None):
        sayac["n"] += 1
        if sayac["n"] <= 2:
            raise RuntimeError("render coktu")
        return sahte_render_tiktok(arka_plan, ses, cikti)

    b = baglam(tmp_path, tiktok_kanal(), SahteTikTok(patla=99))
    b.render_tiktok = iki_kez_bozuk
    for _ in range(3):
        with pytest.raises(RuntimeError):
            calistir(b)
    is_ = b.db.is_getir(1)
    assert is_.durum == "iptal" and is_.deneme == 3
    assert (tmp_path / "cikti" / "t1" / f"is_{is_.id}" / "part2.mp4").exists()
