import logging
import re
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from core.upload import tiktok_secici as s
from core.yorum import HamYorum, YorumIslemHatasi
from core.yorum import tiktok_yorum as ty
from core.yorum.tiktok_yorum import YorumSayfasi, video_yolu_bul, yas_gun


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


@pytest.mark.parametrize("metin,gun", [("5 minutes ago", 5 / 1440), ("2 hours ago", 2 / 24), ("1 week ago", 7.0),
                                       ("3 mins ago", 3 / 1440), ("4 hrs ago", 4 / 24), ("2 days ago", 2.0)])
def test_yas_gun_acik_birimler(metin, gun):
    assert yas_gun(metin) == pytest.approx(gun)


@pytest.mark.parametrize("metin", ["3mo ago", "1y ago", "2 months ago"])
def test_yas_gun_ay_yil_bilinmez(metin):
    assert yas_gun(metin) is None


# --- Playwright sahteleri ---

class _Konum:
    def __init__(self, metinler=None, hata=None):
        self.metinler = metinler or []
        self.hata = hata
        self.first = self
        self.last = self

    def count(self):
        if self.hata:
            raise self.hata
        return len(self.metinler)

    def nth(self, i):
        return _Konum([self.metinler[i]]) if not isinstance(self.metinler[i], _Konum) else self.metinler[i]

    def inner_text(self, timeout=0):
        return self.metinler[0]

    def locator(self, sel):
        return _Konum(["x"])


class _Hucre(_Konum):
    def __init__(self, metin):
        super().__init__([metin])
        self.sorgulanan = []

    def locator(self, sel):
        self.sorgulanan.append(sel)
        return _Konum(["2h ago"])

    def inner_text(self, timeout=0):
        return self.metinler[0]


class _Sayfa:
    def __init__(self, hucreler):
        self.hucreler = hucreler
        self.goto_cagrilari = []
        self.url = "https://x/comment"

    def locator(self, sel):
        k = _Konum(self.hucreler)
        return k

    def goto(self, url):
        self.goto_cagrilari.append(url)

    def screenshot(self, **kw):
        pass

    def content(self):
        return ""


class _Yorumcu:
    hesap = None

    def __init__(self, gorunur=True, hata=None):
        self.log = logging.getLogger("test")
        self.ekranlar = []
        self.gorunur = gorunur

    def _gorunurse(self, loc, ms):
        return self.gorunur

    def _ekran_kaydet(self, sayfa, ad):
        self.ekranlar.append(ad)
        return Path(ad)


def test_oku_gorunur_hucre_yoksa_hata_ve_ekran():
    y = _Yorumcu(gorunur=False)
    ys = YorumSayfasi(y, None, _Sayfa([]))
    with pytest.raises(YorumIslemHatasi, match="Yorum listesi görünmedi") as e:
        ys.oku()
    assert y.ekranlar == ["yorum_bos"] and e.value.ekran == Path("yorum_bos")
    assert not e.value.yetki


def test_oku_bos_durum_metni_gorunurse_bos_liste():
    class BosMetinYorumcu(_Yorumcu):
        def _gorunurse(self, loc, ms):
            return loc.sel == s.YORUM_BOS_METIN

    class SelKonum(_Konum):
        def __init__(self, sel):
            super().__init__([])
            self.sel = sel

    y = BosMetinYorumcu()
    sayfa = _Sayfa([])
    sayfa.locator = lambda sel: SelKonum(sel)
    assert YorumSayfasi(y, None, sayfa).oku() == []
    assert y.ekranlar == []


def test_oku_playwright_hatasi_yorum_islem_hatasi():
    y = _Yorumcu()
    sayfa = _Sayfa([])
    sayfa.locator = lambda sel: _Konum(hata=RuntimeError("koptu"))
    ys = YorumSayfasi(y, None, sayfa)
    with pytest.raises(YorumIslemHatasi) as e:
        ys.oku()
    assert e.value.ekran == Path("yorum_oku")


def test_oku_bos_hucre_sessizce_atlanir(caplog):
    y = _Yorumcu()
    ys = YorumSayfasi(y, None, _Sayfa([_Hucre("   ")]))
    with caplog.at_level(logging.WARNING, logger="test"):
        assert ys.oku() == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


class _Ctx:
    def __init__(self, sayfa):
        self.sayfa = sayfa
        self.acilan = 0

    def new_page(self):
        self.acilan += 1
        return self.sayfa


class _IcerikSayfasi(_Sayfa):
    def __init__(self, hata=None):
        super().__init__([])
        self.kapandi = False
        self.hata = hata

    def goto(self, url):
        if self.hata:
            raise self.hata
        super().goto(url)

    def locator(self, sel):
        return _Konum()

    def close(self):
        self.kapandi = True


def test_video_yolu_ayri_sekmede_ana_sayfa_kalir(monkeypatch):
    monkeypatch.setattr("core.yorum.tiktok_yorum.time.sleep", lambda s: None)
    ana, sekme = _Sayfa([]), _IcerikSayfasi()
    ys = YorumSayfasi(_Yorumcu(), _Ctx(sekme), ana)
    assert ys._video_yolu("bir video basligi uzun") is None
    assert ana.goto_cagrilari == [] and sekme.goto_cagrilari and sekme.kapandi
    assert ys._video_satirlari is None  # bos sonuc onbelleklenmez


def test_sikayet_video_yolu_hatasi_yorum_islem_hatasi(monkeypatch):
    monkeypatch.setattr("core.yorum.tiktok_yorum.time.sleep", lambda s: None)
    sekme = _IcerikSayfasi(hata=PlaywrightTimeout("zaman asimi"))
    y = _Yorumcu()
    ys = YorumSayfasi(y, _Ctx(sekme), _Sayfa([]))
    with pytest.raises(YorumIslemHatasi):
        ys.sikayet_et(HamYorum("u", "metin", "bir video basligi uzun"), "spam")
    assert sekme.kapandi


class _BozukKonum(_Konum):
    def inner_text(self, timeout=0):
        raise RuntimeError("arayüz değişti")


class _BozukHucre(_Hucre):
    def locator(self, sel):
        return _BozukKonum(["?"])


def test_oku_tum_dolu_satirlar_bozuksa_hata():
    y = _Yorumcu()
    ys = YorumSayfasi(y, None, _Sayfa([_BozukHucre("dolu"), _Hucre("  "), _BozukHucre("dolu")]))
    with pytest.raises(YorumIslemHatasi, match="arayüz değişmiş") as e:
        ys.oku()
    assert e.value.ekran is not None


def test_oku_bazi_satirlar_bozuksa_okunanlar_doner():
    ys = YorumSayfasi(_Yorumcu(), None, _Sayfa([_BozukHucre("dolu"), _Hucre("dolu")]))
    assert len(ys.oku()) == 1


# --- eylem sahteleri (kayıt tutan konum/sayfa) ---
class _L:
    """Sahte Playwright konumu: filtreleri kaydeder, tıklamaları ortak kayda yazar."""

    def __init__(self, ad, kayit, adet=1, degerler=("",), gorunur=None, tik_hata=None, cocuklar=None):
        self.ad, self.kayit, self.adet = ad, kayit, adet
        self.degerler = list(degerler)
        self.gorunur = (adet != 0) if gorunur is None else gorunur
        self.tik_hata = tik_hata
        self.cocuklar = cocuklar or {}
        self.filtreler = []

    first = property(lambda self: self)
    last = property(lambda self: self)

    def nth(self, i):
        return self

    def filter(self, **kw):
        self.filtreler.append(kw)
        return self

    def count(self):
        if isinstance(self.adet, Exception):
            raise self.adet
        return self.adet

    def _cocuk(self, anahtar):
        if anahtar not in self.cocuklar:
            self.cocuklar[anahtar] = _L(anahtar, self.kayit)
        return self.cocuklar[anahtar]

    def locator(self, sel):
        return self._cocuk(sel)

    def get_by_text(self, metin, exact=False):
        return self._cocuk(metin)

    def click(self):
        self.kayit.append(("tik", self.ad))
        if self.tik_hata:
            raise self.tik_hata

    def hover(self):
        pass

    def wait_for(self, state="visible", timeout=0):
        pass

    def input_value(self, timeout=0):
        return self.degerler.pop(0) if len(self.degerler) > 1 else self.degerler[0]


class _Klavye:
    def __init__(self, kayit):
        self.kayit = kayit

    def press(self, tus):
        self.kayit.append(("tus", tus))


class _ESayfa:
    def __init__(self, kayit, konumlar=None, goto_hata=None):
        self.kayit = kayit
        self.konumlar = konumlar or {}
        self.goto_cagrilari = []
        self.goto_hata = goto_hata
        self.keyboard = _Klavye(kayit)
        self.kapandi = False

    def locator(self, sel):
        if sel not in self.konumlar:
            self.konumlar[sel] = _L(sel, self.kayit)
        return self.konumlar[sel]

    def get_by_text(self, metin, exact=False):
        return self.locator(metin)

    def get_by_role(self, rol, name=None, exact=False):
        return self.locator(name)

    def goto(self, url):
        self.goto_cagrilari.append(url)
        if self.goto_hata and url == s.YORUM_URL:
            raise self.goto_hata

    def close(self):
        self.kapandi = True


class _EYorumcu(_Yorumcu):
    def __init__(self, kayit):
        super().__init__()
        self.kayit = kayit

    def _gorunurse(self, loc, ms):
        return loc.gorunur

    def _yaz(self, sayfa, metin):
        self.kayit.append(("yaz", metin))

    def _popuplari_kapat(self, sayfa):
        self.kayit.append(("popup", None))


@pytest.fixture
def uykusuz(monkeypatch):
    monkeypatch.setattr("core.yorum.tiktok_yorum.time.sleep", lambda sn: None)
    monkeypatch.setattr(ty, "CEVAP_BOSALMA_SN", 0)


def _kur(konumlar=None, goto_hata=None):
    kayit = []
    sayfa = _ESayfa(kayit, {k: v(kayit) for k, v in (konumlar or {}).items()}, goto_hata)
    return YorumSayfasi(_EYorumcu(kayit), None, sayfa), sayfa, kayit


YH = HamYorum("ali", "Is this real?", "bir video basligi uzun")


def test_hucre_birden_fazla_eslesme_hata(uykusuz):
    ys, _, _ = _kur({s.YORUM_HUCRE: lambda k: _L("hucre", k, adet=2)})
    with pytest.raises(YorumIslemHatasi, match="tek değil"):
        ys._hucre(YH)


def test_hucre_count_hatasi_sarilir(uykusuz):
    ys, _, _ = _kur({s.YORUM_HUCRE: lambda k: _L("hucre", k, adet=RuntimeError("koptu"))})
    with pytest.raises(YorumIslemHatasi) as e:
        ys._hucre(YH)
    assert e.value.ekran is not None


def test_hucre_tam_metin_bosluk_toleransli(uykusuz):
    ys, sayfa, _ = _kur()
    ys._hucre(YH)
    desen = sayfa.konumlar[s.YORUM_METIN].filtreler[-1]["has_text"]
    assert desen.search("  Is this\n real? ")
    assert not desen.search("Is this real? yes") and not desen.search("is this real?")
    assert not desen.search("Oh Is this real?")


def test_cevap_kutusu_dolu_ise_yazmaz_ve_sayfayi_sifirlar(uykusuz):
    ys, sayfa, kayit = _kur({s.YORUM_CEVAP_KUTU: lambda k: _L("kutu", k, degerler=("eski taslak",))})
    with pytest.raises(YorumIslemHatasi) as e:
        ys.cevapla(YH, "Thanks!")
    assert not e.value.gonderildi
    assert not [x for x in kayit if x[0] in ("yaz", "tus")] and ("tik", "Post") not in kayit
    assert sayfa.goto_cagrilari == [s.YORUM_URL] and ("popup", None) in kayit


def test_cevap_kutusu_tek_degilse_yazmaz(uykusuz):
    ys, sayfa, kayit = _kur({s.YORUM_CEVAP_KUTU: lambda k: _L("kutu", k, adet=2)})
    with pytest.raises(YorumIslemHatasi, match="tek değil") as e:
        ys.cevapla(YH, "Thanks!")
    assert not e.value.gonderildi and not [x for x in kayit if x[0] == "yaz"]
    assert sayfa.goto_cagrilari == [s.YORUM_URL]


def test_cevap_gonderildikten_sonra_hata_gonderildi_isaretli(uykusuz):
    ys, sayfa, kayit = _kur({s.YORUM_CEVAP_KUTU: lambda k: _L("kutu", k, degerler=("", "Thanks!"))})
    with pytest.raises(YorumIslemHatasi) as e:
        ys.cevapla(YH, "Thanks!")
    assert e.value.gonderildi
    assert ("yaz", "Thanks!") in kayit and ("tik", "Post") in kayit
    assert sayfa.goto_cagrilari == [s.YORUM_URL]


def test_cevap_basarili(uykusuz):
    ys, sayfa, kayit = _kur()
    ys.cevapla(YH, "Thanks!")
    assert ("yaz", "Thanks!") in kayit and ("tik", "Post") in kayit
    assert sayfa.goto_cagrilari == [s.YORUM_URL]  # cevap arayüzü kapansın


def test_cevap_basarili_sifirlama_hatasi_firlatmaz(uykusuz):
    ys, sayfa, kayit = _kur(goto_hata=RuntimeError("ağ yok"))
    ys.cevapla(YH, "Thanks!")
    assert ("tik", "Post") in kayit and sayfa.goto_cagrilari == [s.YORUM_URL]


def test_hucre_kullanici_basinda_at_toleransli(uykusuz):
    ys, sayfa, _ = _kur()
    ys._hucre(YH)
    desen = sayfa.konumlar[s.YORUM_KULLANICI].filtreler[-1]["has_text"]
    assert desen.search("ali") and desen.search(" @ali ")
    assert not desen.search("@@ali") and not desen.search("ali2") and not desen.search("@bali")


def test_bosaldi_kutu_arada_kopsa_bosaldi_sayilir():
    class Kutular:
        def __init__(self):
            self.adetler = [1, 0]
            self.first = self

        def count(self):
            return self.adetler.pop(0)

        def input_value(self, timeout=0):
            raise RuntimeError("detached")

    assert YorumSayfasi._bosaldi(Kutular()) is True


def test_bosaldi_kutu_hala_varsa_ve_okunamiyorsa_bosalmadi():
    class Kutular:
        first = None

        def count(self):
            return 1

        def input_value(self, timeout=0):
            raise RuntimeError("detached")

    k = Kutular()
    k.first = k
    assert YorumSayfasi._bosaldi(k) is False


def test_begen_hatasi_sayfayi_sifirlar(uykusuz):
    ys, sayfa, kayit = _kur()
    sayfa.konumlar[s.YORUM_HUCRE] = _L("hucre", kayit, cocuklar={
        s.YORUM_BEGENILDI: _L("begenildi", kayit, adet=0),
        s.YORUM_BEGEN: _L("begen", kayit, tik_hata=RuntimeError("tıklanamadı"))})
    with pytest.raises(YorumIslemHatasi, match="Beğenilemedi"):
        ys.begen(YH)
    assert sayfa.goto_cagrilari == [s.YORUM_URL]


def test_sifirlama_hatasi_asil_hatayi_ortmez(uykusuz):
    ys, sayfa, _ = _kur({s.YORUM_HUCRE: lambda k: _L("hucre", k, adet=0)}, goto_hata=RuntimeError("ağ yok"))
    with pytest.raises(YorumIslemHatasi, match="bulunamadı"):
        ys.cevapla(YH, "Thanks!")
    assert sayfa.goto_cagrilari == [s.YORUM_URL]


class _ECtx:
    def __init__(self, sayfa):
        self.sayfa = sayfa

    def new_page(self):
        return self.sayfa


def _sikayet_kur(konumlar=None):
    kayit = []
    ana = _ESayfa(kayit)
    vs = _ESayfa(kayit, {k: v(kayit) for k, v in (konumlar or {}).items()})
    ys = YorumSayfasi(_EYorumcu(kayit), _ECtx(vs), ana)
    ys._video_satirlari = [("/@slumberlab/video/1", "bir video basligi uzun ve devami")]
    return ys, vs, kayit


@pytest.mark.parametrize("adet", [0, 2])
def test_sikayet_hedef_tek_degilse_tiklamaz(uykusuz, adet):
    ys, vs, kayit = _sikayet_kur({s.VIDEO_YORUM_OGE: lambda k: _L("oge", k, adet=adet)})
    with pytest.raises(YorumIslemHatasi, match="Şikayet hedefi") as e:
        ys.sikayet_et(YH, "spam")
    assert not [x for x in kayit if x[0] == "tik"]
    assert e.value.ekran is not None and not e.value.gonderildi and vs.kapandi


def test_sikayet_hedef_yazar_ve_tam_metinle_daraltilir(uykusuz):
    ys, vs, kayit = _sikayet_kur()
    ys.sikayet_et(YH, "spam")
    sahipler = [f["has"] for f in vs.konumlar[s.VIDEO_YORUM_OGE].filtreler]
    assert vs.konumlar[s.VIDEO_YORUM_YAZAR.format(kullanici="ali")] in sahipler
    metin = vs.konumlar[s.VIDEO_YORUM_METIN]
    assert metin in sahipler
    desen = metin.filtreler[-1]["has_text"]
    assert isinstance(desen, re.Pattern) and desen.search(" Is this real? ") and not desen.search("Is this real?!")
    assert {"visible": True} in vs.konumlar[s.VIDEO_SIKAYET_MENU].filtreler
    assert ("tik", "Report") in kayit and ("tik", s.VIDEO_SIKAYET_GONDER) in kayit


def test_sikayet_menude_report_yoksa_tiklamaz(uykusuz):
    def menu(k):
        return _L("menu", k, cocuklar={s.VIDEO_SIKAYET_METNI: _L("Report", k, gorunur=False)})
    ys, vs, kayit = _sikayet_kur({s.VIDEO_SIKAYET_MENU: menu})
    with pytest.raises(YorumIslemHatasi) as e:
        ys.sikayet_et(YH, "spam")
    assert ("tik", "Report") not in kayit and not e.value.gonderildi
    assert ("tik", s.VIDEO_SIKAYET_GONDER) not in kayit


def test_sikayet_gonderildikten_sonra_onay_yoksa_gonderildi(uykusuz):
    ys, vs, kayit = _sikayet_kur({x: (lambda k, x=x: _L(x, k, gorunur=False)) for x in s.VIDEO_SIKAYET_TAMAM})
    with pytest.raises(YorumIslemHatasi) as e:
        ys.sikayet_et(YH, "spam")
    assert e.value.gonderildi and ("tik", s.VIDEO_SIKAYET_GONDER) in kayit
