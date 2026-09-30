import logging

import pytest

import calistir
from core.ayar import Kanal, Kaynak, Ses
from core.db import DB


def test_calistir_modulu_yuklenir():
    assert callable(calistir.main)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    kanal = Kanal(ad="t1", platform="tiktok", kaynak=Kaynak("reddit", ["A"]), ses=Ses("edge", "v", "+0%"),
                  arka_plan=tmp_path / "bg.mp4", gorunurluk="herkes", profil="p1")
    monkeypatch.setattr(calistir, "kanal_yukle", lambda ad: kanal)
    monkeypatch.setattr(calistir, "db_yolu", lambda: tmp_path / "f.db")
    monkeypatch.setattr(calistir, "KOK", tmp_path)
    monkeypatch.setattr(calistir, "ortami_yukle", lambda: None)
    monkeypatch.setattr(calistir.gunluk, "kur", lambda ad: logging.getLogger("test"))
    return DB(tmp_path / "f.db")


def _bekleyen(db, bayrak):
    is_ = db.is_olustur("t1")
    return db.is_ilerlet(is_.id, "video_hazir", bekleyen_onay=bayrak)


def test_onayla_bayragi_isi_ilerletir(ortam, capsys):
    is_ = _bekleyen(ortam, "part1")
    assert calistir.main(["t1", "--onayla"]) == 0
    assert ortam.is_getir(is_.id).durum == "parca1_yuklendi"
    assert f"#{is_.id}" in capsys.readouterr().out


def test_yeniden_dene_bayragi_temizler(ortam):
    is_ = _bekleyen(ortam, "part1")
    assert calistir.main(["t1", "--yeniden-dene"]) == 0
    assert ortam.is_getir(is_.id).veri["bekleyen_onay"] is None


@pytest.mark.parametrize("bayrak", ["--onayla", "--yeniden-dene"])
def test_onay_bekleyen_is_yoksa_1(ortam, capsys, bayrak):
    assert calistir.main(["t1", bayrak]) == 1
    assert "yok" in capsys.readouterr().out


class SahteBildirim:
    mesajlar = []

    def __init__(self, *a, **kw):
        SahteBildirim.mesajlar = []

    def mesaj(self, m):
        SahteBildirim.mesajlar.append(m)

    def foto(self, y, m):
        SahteBildirim.mesajlar.append(m)


@pytest.fixture
def calisma(ortam, monkeypatch):
    import core.is_akisi
    import core.llm

    monkeypatch.setattr(calistir, "onkontrol", lambda kanal, kuru=False: [])
    monkeypatch.setattr(calistir, "Bildirim", SahteBildirim)
    monkeypatch.setattr(calistir, "ortam", lambda anahtar, zorunlu=True: "x")
    monkeypatch.setattr(core.llm, "Gemini", lambda *a, **kw: object())

    def ayarla(davranis):
        monkeypatch.setattr(core.is_akisi, "calistir", davranis)
    return ayarla


def test_onay_gerekli_cikis_kodu_3(calisma):
    from core.is_akisi import OnayGerekli

    def patla(b):
        raise OnayGerekli("Part 1 onay bekliyor")
    calisma(patla)
    assert calistir.main(["t1"]) == 3
