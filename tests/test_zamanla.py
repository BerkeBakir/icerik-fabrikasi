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
