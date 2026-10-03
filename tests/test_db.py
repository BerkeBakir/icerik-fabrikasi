from datetime import datetime, timedelta

from core.db import DB, yorum_kimligi


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


def test_is_iptal(tmp_path):
    db = DB(tmp_path / "f.db")
    i = db.is_olustur("k")
    assert db.is_iptal(i.id).durum == "iptal"
    assert db.yarim_is("k") is None


def test_hata_sayilmadan_kaydedilir(tmp_path):
    db = DB(tmp_path / "f.db")
    a = db.is_olustur("k1")
    db.is_ilerlet(a.id, "video_hazir")
    b = db.is_hata(a.id, "oturum kapali", say=False)
    assert b.deneme == 0 and b.hata == "oturum kapali" and b.durum == "video_hazir"
    for _ in range(3):
        b = db.is_hata(a.id, "yine", say=False)
    assert b.durum == "video_hazir" and b.deneme == 0


def test_yorum_kimligi_kararli_ve_ayirt_edici():
    a = yorum_kimligi("k1", "ali", "Merhaba", "PART 1 | x")
    assert a == yorum_kimligi("k1", "ali", "Merhaba", "PART 1 | x")
    assert len(a) == 16
    assert a != yorum_kimligi("k1", "ali", "Merhaba", "PART 2 | x")
    assert a != yorum_kimligi("k2", "ali", "Merhaba", "PART 1 | x")


def test_yorum_yasam_dongusu(tmp_path):
    db = DB(tmp_path / "f.db")
    kim = yorum_kimligi("k1", "ali", "Is this real?", "PART 1 | x")
    assert not db.yorum_var_mi(kim)
    y = db.yorum_ekle(kim, "k1", "ali", "Is this real?", "PART 1 | x")
    assert y.durum == "yeni" and y.deneme == 0 and y.tur is None
    assert db.yorum_ekle(kim, "k1", "ali", "baska", "v").metin == "Is this real?"  # ikinci ekleme dokunmaz
    y = db.yorum_karar(kim, "soru", "Yes, it's from Reddit!", "", "")
    assert y.durum == "bekliyor" and y.tur == "soru" and y.cevap == "Yes, it's from Reddit!"
    assert [x.kimlik for x in db.yorum_islenecekler("k1")] == [kim]
    y = db.yorum_bitir(kim, "cevaplandi")
    assert y.durum == "cevaplandi" and db.yorum_islenecekler("k1") == []
    assert db.yorum_cevap_mi("k1", "Yes, it's from Reddit!")
    assert not db.yorum_cevap_mi("k2", "Yes, it's from Reddit!")


def test_yorum_hata_ikincide_atlanir(tmp_path):
    db = DB(tmp_path / "f.db")
    kim = yorum_kimligi("k1", "a", "b", "c")
    db.yorum_ekle(kim, "k1", "a", "b", "c")
    y = db.yorum_hata(kim, "buton yok")
    assert y.durum == "hata" and y.deneme == 1 and y.hata == "buton yok"
    assert [x.kimlik for x in db.yorum_islenecekler("k1")] == [kim]
    assert db.yorum_hata(kim, "yine yok").durum == "atlandi"


def test_yapici_yorumlar_tarihe_gore(tmp_path):
    db = DB(tmp_path / "f.db")
    for i, tur in enumerate(["yapici", "soru", "yapici"]):
        kim = yorum_kimligi("k1", f"u{i}", "m", "v")
        db.yorum_ekle(kim, "k1", f"u{i}", "m", "v")
        db.yorum_karar(kim, tur, "c", "ses" if tur == "yapici" else "", "Daha yavaş" if tur == "yapici" else "")
    simdi = datetime.now()
    assert len(db.yapici_yorumlar("k1", simdi - timedelta(days=7))) == 2
    assert db.yapici_yorumlar("k1", simdi + timedelta(days=1)) == []


def test_son_isler(tmp_path):
    db = DB(tmp_path / "f.db")
    a, b = db.is_olustur("k1"), db.is_olustur("k1")
    db.is_olustur("k2")
    assert [x.id for x in db.son_isler("k1")] == [b.id, a.id]
