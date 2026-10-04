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


@pytest.mark.parametrize("metin,gun", [("5 minutes ago", 5 / 1440), ("2 hours ago", 2 / 24), ("1 week ago", 7.0),
                                       ("3 mins ago", 3 / 1440), ("4 hrs ago", 4 / 24), ("2 days ago", 2.0)])
def test_yas_gun_acik_birimler(metin, gun):
    assert yas_gun(metin) == pytest.approx(gun)


@pytest.mark.parametrize("metin", ["3mo ago", "1y ago", "2 months ago"])
def test_yas_gun_ay_yil_bilinmez(metin):
    assert yas_gun(metin) is None


# --- Playwright sahteleri ---
import logging
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from core.yorum import YorumIslemHatasi
from core.yorum.tiktok_yorum import YorumSayfasi


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


def test_oku_gorunur_hucre_yoksa_bos_ve_ekran(caplog):
    y = _Yorumcu(gorunur=False)
    ys = YorumSayfasi(y, None, _Sayfa([]))
    with caplog.at_level(logging.WARNING, logger="test"):
        assert ys.oku() == []
    assert y.ekranlar == ["yorum_bos"]
    assert any(r.levelno == logging.WARNING for r in caplog.records)


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
    from core.yorum import HamYorum
    with pytest.raises(YorumIslemHatasi):
        ys.sikayet_et(HamYorum("u", "metin", "bir video basligi uzun"), "spam")
    assert sekme.kapandi
