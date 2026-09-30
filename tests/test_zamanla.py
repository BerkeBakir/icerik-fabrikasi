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


class _Sonuc:
    returncode = 0
    stdout = "BAŞARILI"
    stderr = ""


def _yakala(monkeypatch):
    cagrilar = []

    def sahte_run(komut, **kw):
        cagrilar.append((komut, kw))
        return _Sonuc()
    monkeypatch.setattr(zamanla.subprocess, "run", sahte_run)
    return cagrilar


def test_main_oem_kodlamasi_kullanir(monkeypatch):
    cagrilar = _yakala(monkeypatch)
    assert zamanla.main(["k1", "--saat", "09:00", "--saat", "18:00"]) == 0
    assert [c[0][1] for c in cagrilar] == ["/Create", "/Create"]
    for _, kw in cagrilar:
        assert kw["encoding"] == "oem" and kw["errors"] == "replace"
        assert kw["capture_output"] is True and kw["text"] is True


def test_main_sil_komutu_kurar(monkeypatch):
    cagrilar = _yakala(monkeypatch)
    assert zamanla.main(["k1", "--saat", "09:00", "--sil"]) == 0
    assert cagrilar[0][0] == zamanla.sil_komutu("k1", "09:00")
    assert cagrilar[0][1]["encoding"] == "oem"


def test_main_hata_kodunu_dondurur(monkeypatch):
    class Hata(_Sonuc):
        returncode = 5
        stdout = ""
        stderr = "HATA"
    cagrilar = []
    monkeypatch.setattr(zamanla.subprocess, "run", lambda komut, **kw: cagrilar.append(komut) or Hata())
    assert zamanla.main(["k1", "--saat", "09:00", "--saat", "10:00"]) == 5
    assert len(cagrilar) == 1
