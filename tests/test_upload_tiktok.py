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
    assert s.etiket_oneri_deseni("story").search("#story 1.2M views")
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
