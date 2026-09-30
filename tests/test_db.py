from core.db import DB


def test_hikaye_isaretleme(tmp_path):
    db = DB(tmp_path / "v" / "f.db")
    assert not db.hikaye_kullanildi_mi("reddit:abc")
    db.hikaye_isaretle("reddit:abc", "k1")
    db.hikaye_isaretle("reddit:abc", "k2")  # ikinci kez hata vermez
    assert db.hikaye_kullanildi_mi("reddit:abc")


def test_is_ilerler_ve_veri_birlesir(tmp_path):
    db = DB(tmp_path / "f.db")
    is_ = db.is_olustur("k1")
    assert is_.durum == "yeni" and is_.veri == {}
    db.is_ilerlet(is_.id, "hikaye_secildi", hikaye={"kimlik": "x"})
    is_ = db.is_ilerlet(is_.id, "senaryo_hazir", senaryo={"part1": "a"})
    assert is_.durum == "senaryo_hazir"
    assert is_.veri == {"hikaye": {"kimlik": "x"}, "senaryo": {"part1": "a"}}
    assert is_.gecti_mi("hikaye_secildi") and is_.gecti_mi("senaryo_hazir")
    assert not is_.gecti_mi("ses_hazir")


def test_yarim_is_bulunur_bitmis_is_bulunmaz(tmp_path):
    db = DB(tmp_path / "f.db")
    a = db.is_olustur("k1")
    assert db.yarim_is("k1").id == a.id
    assert db.yarim_is("k2") is None
    db.is_ilerlet(a.id, "yuklendi")
    assert db.yarim_is("k1") is None


def test_uc_hatadan_sonra_is_iptal(tmp_path):
    db = DB(tmp_path / "f.db")
    a = db.is_olustur("k1")
    db.is_hata(a.id, "bir")
    b = db.is_hata(a.id, "iki")
    assert b.durum == "yeni" and b.deneme == 2 and b.hata == "iki"
    c = db.is_hata(a.id, "uc")
    assert c.durum == "iptal"
    assert db.yarim_is("k1") is None


def test_basarili_ilerleme_hatayi_temizler(tmp_path):
    db = DB(tmp_path / "f.db")
    a = db.is_olustur("k1")
    db.is_hata(a.id, "gecici")
    b = db.is_ilerlet(a.id, "hikaye_secildi")
    assert b.hata is None and b.deneme == 1
