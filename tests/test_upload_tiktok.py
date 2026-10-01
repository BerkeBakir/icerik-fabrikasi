from datetime import datetime, timedelta

import pytest

from core.upload.tiktok import TikTokHatasi, TikTokYukleyici, zamani_tazele, zamani_yuvarla


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


from datetime import timedelta
from pathlib import Path

from core.upload import tiktok_secici as s
from core.upload.tiktok import TikTokYukleyici, zamanlama_dogrula


def test_secici_desenleri():
    assert s.etiket_oneri_deseni("story").search("#storytime") is None
    assert s.etiket_oneri_deseni("story").search("#story")
    assert s.etiket_oneri_deseni("Story").search(" story ")
    assert s.tam_metin_deseni("5").search("15") is None
    assert s.tam_metin_deseni("5").search("5")


def test_tiktok_py_secici_icermez():
    kaynak = (Path(__file__).resolve().parent.parent / "core" / "upload" / "tiktok.py").read_text(encoding="utf-8")
    for yasak in ['button:has-text', 'div[', 'span[', "tiktokstudio", 'input[']:
        assert yasak not in kaynak


def test_gecersiz_gorunurluk_tarayici_acmadan_hata(tmp_path):
    y = TikTokYukleyici(tmp_path / "p", tmp_path / "h")
    with pytest.raises(TikTokHatasi, match="görünürlük"):
        y.yukle(tmp_path / "v.mp4", "a", [], "herkese_acik")


def test_cancel_kapatilacaklar_listesinde_yok():
    assert not any("Cancel" in x for x in s.KAPAT_BUTONLARI)


def test_zamanlama_cok_yakin_hata():
    simdi = datetime(2026, 9, 30, 12, 0)
    with pytest.raises(TikTokHatasi):
        zamanlama_dogrula(simdi + timedelta(minutes=10), simdi)


def test_zamanlama_yuvarlar():
    simdi = datetime(2026, 9, 30, 12, 0)
    r = zamanlama_dogrula(simdi + timedelta(minutes=23, seconds=10), simdi)
    assert r.minute % 5 == 0 and r.second == 0


def test_zamanlama_10_gun_siniri():
    simdi = datetime(2026, 9, 30, 12, 1)
    r = zamanlama_dogrula(simdi + timedelta(days=10), simdi)
    assert r <= simdi + timedelta(days=10) and r.minute % 5 == 0


def test_zamanlama_cok_uzak_hata():
    simdi = datetime(2026, 9, 30, 12, 0)
    with pytest.raises(TikTokHatasi):
        zamanlama_dogrula(simdi + timedelta(days=11), simdi)


def test_gecersiz_zaman_tarayici_acmadan_hata(tmp_path):
    y = TikTokYukleyici(tmp_path / "p", tmp_path / "h")
    with pytest.raises(TikTokHatasi):
        y.yukle(tmp_path / "v.mp4", "a", [], "herkes", datetime.now() + timedelta(minutes=5))
    assert not (tmp_path / "p").exists()


def test_zamani_tazele():
    simdi = datetime(2026, 9, 29, 12, 0)
    assert zamani_tazele(datetime(2026, 9, 29, 12, 30), simdi) == datetime(2026, 9, 29, 12, 30)
    assert zamani_tazele(datetime(2026, 9, 29, 12, 10), simdi) == datetime(2026, 9, 29, 12, 20)


class _SahteOge:
    def __init__(self, hata=None):
        self.hata = hata

    @property
    def first(self):
        return self

    def click(self):
        if self.hata:
            raise self.hata

    def count(self):
        return 0

    def wait_for(self, state, timeout):
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        raise PlaywrightTimeout("yok")


class _SahteSayfa:
    def __init__(self, paylas_hata=None, url_hata=None):
        self.paylas_hata = paylas_hata
        self.url_hata = url_hata

    @property
    def url(self):
        if self.url_hata:
            raise self.url_hata
        return "https://example.com/upload"

    def locator(self, secici):
        return _SahteOge(self.paylas_hata if secici == s.PAYLAS_BUTON else None)


@pytest.fixture
def hizli_zaman(monkeypatch):
    import core.upload.tiktok as tt
    saat = [0.0]

    def zaman():
        saat[0] += 30
        return saat[0]
    monkeypatch.setattr(tt.time, "time", zaman)
    monkeypatch.setattr(tt.time, "sleep", lambda sn: None)


def test_hata_varsayilan_gonderilmedi():
    assert TikTokHatasi("x").gonderildi is False
    assert TikTokHatasi("x", gonderildi=True).gonderildi is True


def test_dogrulama_zaman_asimi_gonderildi_isaretler(tmp_path, hizli_zaman):
    y = TikTokYukleyici(tmp_path / "p", tmp_path / "h")
    with pytest.raises(TikTokHatasi, match="doğrulanamadı") as h:
        y._paylas_ve_dogrula(_SahteSayfa())
    assert h.value.gonderildi is True


def test_tiklama_sonrasi_beklenmeyen_hata_gonderildi_isaretler(tmp_path, hizli_zaman):
    y = TikTokYukleyici(tmp_path / "p", tmp_path / "h")
    with pytest.raises(TikTokHatasi) as h:
        y._paylas_ve_dogrula(_SahteSayfa(url_hata=RuntimeError("sayfa kapandi")))
    assert h.value.gonderildi is True and "sayfa kapandi" in str(h.value)


def test_tiklama_oncesi_hata_gonderilmedi(tmp_path, hizli_zaman):
    y = TikTokYukleyici(tmp_path / "p", tmp_path / "h")
    with pytest.raises(Exception) as h:
        y._paylas_ve_dogrula(_SahteSayfa(paylas_hata=RuntimeError("buton yok")))
    assert getattr(h.value, "gonderildi", False) is False


def test_oturum_kapaliysa_yetki_hatasi(tmp_path, monkeypatch):
    import playwright.sync_api
    from contextlib import contextmanager

    class Sayfa:
        url = "https://www.tiktok.com/login?redirect=x"

        def goto(self, url):
            pass

    class Ctx:
        def close(self):
            pass

    @contextmanager
    def sahte_playwright():
        yield object()
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", sahte_playwright)
    y = TikTokYukleyici(tmp_path / "p", tmp_path / "h")
    monkeypatch.setattr(y, "_baslat_sarmali", lambda p: (Ctx(), Sayfa()))
    monkeypatch.setattr(y, "_bekle", lambda *a: None)
    monkeypatch.setattr(y, "_ekran_kaydet", lambda sayfa, ad: None)
    with pytest.raises(TikTokHatasi, match="--giris") as h:
        y.yukle(tmp_path / "v.mp4", "a", [], "herkes")
    assert h.value.yetki is True and h.value.gonderildi is False
    assert TikTokHatasi("x").yetki is False


class _SahteYuklemeSayfasi:
    url = "https://www.tiktok.com/tiktokstudio/upload"

    def goto(self, url):
        pass


class _SahteCtx:
    def close(self):
        raise RuntimeError("ctx kapanmadı")


class _SahtePw:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        raise RuntimeError("playwright durdurulamadı")


def _yukleyici(tmp_path, monkeypatch, paylas):
    import core.upload.tiktok as t

    monkeypatch.setattr(t, "sync_playwright", lambda: _SahtePw())
    y = TikTokYukleyici(tmp_path / "p", tmp_path / "h")
    monkeypatch.setattr(y, "_baslat", lambda p: (_SahteCtx(), _SahteYuklemeSayfasi()))
    for ad in ("_dosya_sec", "_aciklama_ve_etiketler", "_gorunurluk", "_popuplari_kapat", "_bekle"):
        monkeypatch.setattr(y, ad, lambda *a, **kw: None)
    monkeypatch.setattr(y, "_ekran_kaydet", lambda *a, **kw: None)
    monkeypatch.setattr(y, "_paylas_ve_dogrula", lambda sayfa: paylas(y))
    return y


def test_kapanis_hatasi_tiklama_sonrasi_gonderildi_isaretini_korur(tmp_path, monkeypatch):
    def paylas(y):
        y._tiklandi = True
        raise TikTokHatasi("dogrulanamadi")

    y = _yukleyici(tmp_path, monkeypatch, paylas)
    with pytest.raises(TikTokHatasi) as e:
        y.yukle(tmp_path / "v.mp4", "a", [], "herkes")
    assert e.value.gonderildi is True


def test_kapanis_hatasi_basarili_yuklemeyi_bozmaz(tmp_path, monkeypatch):
    def paylas(y):
        y._tiklandi = True

    y = _yukleyici(tmp_path, monkeypatch, paylas)
    assert y.yukle(tmp_path / "v.mp4", "a", [], "herkes") is None


def test_tiklama_oncesi_hata_gonderildi_degil(tmp_path, monkeypatch):
    y = _yukleyici(tmp_path, monkeypatch, lambda y: None)

    def patla(*a, **kw):
        raise RuntimeError("yüklenemedi")
    monkeypatch.setattr(y, "_dosya_sec", patla)
    with pytest.raises(TikTokHatasi) as e:
        y.yukle(tmp_path / "v.mp4", "a", [], "herkes")
    assert e.value.gonderildi is False


def test_tiklama_sonrasi_sade_istisna_gonderildi_olur(tmp_path, monkeypatch):
    def paylas(y):
        y._tiklandi = True
        raise ValueError("click sonrası")

    y = _yukleyici(tmp_path, monkeypatch, paylas)
    with pytest.raises(TikTokHatasi) as e:
        y.yukle(tmp_path / "v.mp4", "a", [], "herkes")
    assert e.value.gonderildi is True
