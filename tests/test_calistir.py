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


def test_main_baslangic_mesaji_gondermez(calisma):
    calisma(lambda b: None)
    assert calistir.main(["t1"]) == 0
    assert SahteBildirim.mesajlar == []


def test_bildirilmemis_hata_telegrama_gider(calisma):
    def patla(b):
        raise ValueError("beklenmedik")
    calisma(patla)
    assert calistir.main(["t1"]) == 1
    assert len(SahteBildirim.mesajlar) == 1
    assert "ValueError" in SahteBildirim.mesajlar[0] and "beklenmedik" in SahteBildirim.mesajlar[0]


def test_bildirilmis_hata_tekrar_gonderilmez(calisma):
    def patla(b):
        e = RuntimeError("zaten bildirildi")
        e.bildirildi = True
        raise e
    calisma(patla)
    assert calistir.main(["t1"]) == 1
    assert SahteBildirim.mesajlar == []


def test_kuru_modda_hata_telegrama_gitmez(calisma):
    def patla(b):
        raise ValueError("beklenmedik")
    calisma(patla)
    assert calistir.main(["t1", "--kuru"]) == 1
    assert SahteBildirim.mesajlar == []


@pytest.mark.parametrize("ikinci", ["--yeniden-dene", "--giris", "--kuru", "--ses-ornekleri"])
def test_modlar_birbirini_dislar(ikinci):
    with pytest.raises(SystemExit):
        calistir.main(["k", "--onayla", ikinci])


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
