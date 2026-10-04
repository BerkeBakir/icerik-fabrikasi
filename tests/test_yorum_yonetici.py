import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.ayar import Kanal, Kaynak, Ses
from core.db import DB, yorum_kimligi
from core.yorum import HamYorum, YorumIslemHatasi
from core.yorum import yonetici as yon

LOG = logging.getLogger("test")


def kanal(en_fazla=10):
    k = Kanal(ad="t1", platform="tiktok", kaynak=Kaynak("reddit", ["A"]), ses=Ses("edge", "v", "+0%"),
              arka_plan=Path("bg.mp4"), gorunurluk="herkes", profil="p1")
    k.yorum_aktif, k.yorum_en_fazla, k.yorum_hesap = True, en_fazla, "slumberlab"
    return k


class SahteLLM:
    """Yorum metnindeki anahtar kelimeye göre karar döner."""
    def __init__(self, patlat=()):
        self.cagri = 0
        self.patlat = patlat

    def json_uret(self, prompt, sema, sicaklik=0.8):
        self.cagri += 1
        metin = prompt.rsplit(":", 1)[-1]
        if any(p in metin for p in self.patlat):
            raise RuntimeError("503")
        if "?" in metin:
            return {"tur": "soru", "cevap": "Good question!"}
        if "slower" in metin:
            return {"tur": "yapici", "cevap": "Thanks, noted!", "konu": "ses", "oneri": "Slower narration."}
        if "follow me" in metin:
            return {"tur": "spam"}
        return {"tur": "yorum"}


class SahteSayfa:
    def __init__(self, yorumlar, bozuk=()):
        self.yorumlar = yorumlar
        self.bozuk = bozuk
        self.eylemler = []

    def oku(self):
        return list(self.yorumlar)

    def _yap(self, ad, y, *ek):
        if y.metin in self.bozuk:
            raise YorumIslemHatasi(f"{ad} başarısız", ekran=Path("e.png"))
        self.eylemler.append((ad, y.kullanici, *ek))

    def cevapla(self, y, metin):
        self._yap("cevap", y, metin)

    def begen(self, y):
        self._yap("begen", y)

    def sikayet_et(self, y, tur):
        self._yap("sikayet", y, tur)


class SahteYorumcu:
    def __init__(self, sayfa):
        self.sayfa = sayfa

    @contextmanager
    def oturum(self):
        yield self.sayfa


class SahteBildirim:
    def __init__(self):
        self.mesajlar, self.fotolar = [], []

    def mesaj(self, m):
        self.mesajlar.append(m)

    def foto(self, yol, m):
        self.fotolar.append((yol, m))


def calistir(tmp_path, yorumlar, llm=None, k=None, bozuk=(), kuru=False, db=None, simdi=None):
    db = db or DB(tmp_path / "f.db")
    sayfa = SahteSayfa(yorumlar, bozuk)
    b = SahteBildirim()
    uykular = []
    ozet = yon.yorumlari_isle(k or kanal(), db, llm or SahteLLM(), SahteYorumcu(sayfa), b, LOG, kuru=kuru,
                              uyku=uykular.append, simdi=simdi)
    return ozet, sayfa, b, db, uykular


def H(kullanici, metin, video="PART 1 | x"):
    return HamYorum(kullanici, metin, video)


def test_turlere_gore_eylem_ve_bildirim(tmp_path):
    yorumlar = [H("a", "Is this real?"), H("b", "please talk slower"), H("c", "love it"),
                H("d", "follow me pls"), H("e", "siktir git")]
    ozet, sayfa, b, db, uykular = calistir(tmp_path, yorumlar)
    assert sayfa.eylemler == [("cevap", "a", "Good question!"), ("cevap", "b", "Thanks, noted!"),
                              ("begen", "c"), ("sikayet", "d", "spam"), ("sikayet", "e", "hakaret")]
    assert (ozet.cevap, ozet.begeni, ozet.sikayet, ozet.hata) == (2, 1, 2, 0)
    assert sum(m.startswith("💬") for m in b.mesajlar) == 2
    assert sum(m.startswith("🚩") for m in b.mesajlar) == 2
    assert b.mesajlar[-1].startswith("🧾") and "2 cevap" in b.mesajlar[-1]
    assert '"Is this real?"' in b.mesajlar[0] and '↳ "Good question!"' in b.mesajlar[0]
    durumlar = {y.kullanici: y.durum for y in map(db.yorum_getir, [yorum_kimligi("t1", y.kullanici, y.metin,
                                                                                  y.video) for y in yorumlar])}
    assert durumlar == {"a": "cevaplandi", "b": "cevaplandi", "c": "begenildi", "d": "sikayet_edildi",
                        "e": "sikayet_edildi"}
    assert len(uykular) == 5


def test_sessiz_yorum_islem_yapmaz(tmp_path):
    y = H("a", "she is such a bitch")
    ozet, sayfa, b, db, uykular = calistir(tmp_path, [y])
    assert sayfa.eylemler == [] and b.mesajlar == [] and uykular == []
    assert (ozet.cevap, ozet.begeni, ozet.sikayet, ozet.hata, ozet.bekleyen) == (0, 0, 0, 0, 0)
    assert db.yorum_getir(yorum_kimligi("t1", "a", y.metin, y.video)).durum == "atlandi"


def test_ayni_yorum_ikinci_calistirmada_islenmez(tmp_path):
    y = [H("a", "Is this real?")]
    _, _, _, db, _ = calistir(tmp_path, y)
    llm = SahteLLM()
    ozet, sayfa, b, _, _ = calistir(tmp_path, y, llm=llm, db=db)
    assert sayfa.eylemler == [] and llm.cagri == 0 and b.mesajlar == []


def test_kendi_yorumumuz_ve_cevabimiz_atlanir(tmp_path):
    y = [H("a", "Is this real?")]
    _, _, _, db, _ = calistir(tmp_path, y)
    ozet, sayfa, _, _, _ = calistir(tmp_path, [H("SlumberLab", "anything"), H("x", "Good question!")], db=db)
    assert sayfa.eylemler == []


def test_cevap_siniri_tasanlar_bekler(tmp_path):
    y = [H(f"u{i}", f"q{i}?") for i in range(4)]
    ozet, sayfa, _, db, _ = calistir(tmp_path, y, k=kanal(en_fazla=2))
    assert ozet.cevap == 2 and ozet.bekleyen == 2
    llm = SahteLLM()
    ozet, sayfa, _, _, _ = calistir(tmp_path, y, llm=llm, k=kanal(en_fazla=2), db=db)
    assert ozet.cevap == 2 and llm.cagri == 0  # bekleyenler yeniden sınıflandırılmaz


def test_gorunmeyen_bekleyen_yorum_korunur(tmp_path):
    y = [H("u0", "q0?"), H("u1", "q1?")]
    _, _, _, db, _ = calistir(tmp_path, y, k=kanal(en_fazla=1))
    kim = yorum_kimligi("t1", "u1", "q1?", "PART 1 | x")
    assert db.yorum_getir(kim).durum == "bekliyor"
    ozet, *_ = calistir(tmp_path, [], k=kanal(en_fazla=1), db=db)
    assert db.yorum_getir(kim).durum == "bekliyor" and ozet.bekleyen == 0


def test_gorunmeyen_eski_bekleyen_yorum_atlanir(tmp_path):
    y = [H("u0", "q0?"), H("u1", "q1?")]
    _, _, _, db, _ = calistir(tmp_path, y, k=kanal(en_fazla=1))
    kim = yorum_kimligi("t1", "u1", "q1?", "PART 1 | x")
    calistir(tmp_path, [], k=kanal(en_fazla=1), db=db, simdi=datetime.now() + timedelta(days=9))
    assert db.yorum_getir(kim).durum == "atlandi"


def test_sikayet_siniri(tmp_path):
    y = [H(f"u{i}", f"follow me {i}") for i in range(7)]
    ozet, *_ = calistir(tmp_path, y)
    assert ozet.sikayet == yon.SIKAYET_SINIR and ozet.bekleyen == 2


def test_llm_hatasi_yorumu_yeni_birakir(tmp_path):
    y = [H("a", "boom?"), H("b", "Is this real?")]
    ozet, sayfa, _, db, _ = calistir(tmp_path, y, llm=SahteLLM(patlat=("boom",)))
    assert sayfa.eylemler == [("cevap", "b", "Good question!")]
    assert db.yorum_getir(yorum_kimligi("t1", "a", "boom?", "PART 1 | x")).durum == "yeni"


def test_eylem_hatasi_kaydedilir_sonra_atlanir(tmp_path):
    y = [H("a", "Is this real?")]
    ozet, _, _, db, _ = calistir(tmp_path, y, bozuk=("Is this real?",))
    kim = yorum_kimligi("t1", "a", "Is this real?", "PART 1 | x")
    assert ozet.hata == 1 and db.yorum_getir(kim).durum == "hata"
    calistir(tmp_path, y, bozuk=("Is this real?",), db=db)
    assert db.yorum_getir(kim).durum == "atlandi"


def test_ardisik_uc_hata_durdurur_ve_ekran_gonderir(tmp_path):
    y = [H(f"u{i}", f"q{i}?") for i in range(5)]
    with pytest.raises(YorumIslemHatasi):
        calistir(tmp_path, y, bozuk=tuple(f"q{i}?" for i in range(5)))


def test_ardisik_hata_bildirimi(tmp_path):
    db = DB(tmp_path / "f.db")
    b = SahteBildirim()
    sayfa = SahteSayfa([H(f"u{i}", f"q{i}?") for i in range(5)], bozuk=tuple(f"q{i}?" for i in range(5)))
    with pytest.raises(YorumIslemHatasi):
        yon.yorumlari_isle(kanal(), db, SahteLLM(), SahteYorumcu(sayfa), b, LOG, uyku=lambda s: None)
    assert len(b.fotolar) == 1 and "3" in b.fotolar[0][1]


def test_ardisik_hata_bildirildi_isaretler(tmp_path):
    with pytest.raises(YorumIslemHatasi) as e:
        calistir(tmp_path, [H(f"u{i}", f"q{i}?") for i in range(5)], bozuk=tuple(f"q{i}?" for i in range(5)))
    assert getattr(e.value, "bildirildi", False) is True


class BelirsizSayfa(SahteSayfa):
    def cevapla(self, y, metin):
        if y.metin == "q?":
            raise YorumIslemHatasi("kutu boşalmadı", ekran=Path("b.png"), gonderildi=True)
        super().cevapla(y, metin)


def test_gonderildi_hatasi_belirsiz_ve_tekrar_denenmez(tmp_path):
    db = DB(tmp_path / "f.db")
    y = [H("a", "q?"), H("b", "Is this real?")]
    b = SahteBildirim()
    sayfa = BelirsizSayfa(y)
    ozet = yon.yorumlari_isle(kanal(), db, SahteLLM(), SahteYorumcu(sayfa), b, LOG, uyku=lambda s: None)
    kim = yorum_kimligi("t1", "a", "q?", "PART 1 | x")
    assert db.yorum_getir(kim).durum == "belirsiz"
    assert ozet.hata == 1 and ozet.cevap == 1 and sayfa.eylemler == [("cevap", "b", "Good question!")]
    assert len(b.fotolar) == 1
    yol, m = b.fotolar[0]
    assert yol == Path("b.png") and m.startswith("⚠️ [t1] @a:") and "tekrar denenmeyecek" in m and '"q?"' in m
    sayfa2 = BelirsizSayfa(y)
    yon.yorumlari_isle(kanal(), db, SahteLLM(), SahteYorumcu(sayfa2), SahteBildirim(), LOG, uyku=lambda s: None)
    assert sayfa2.eylemler == []


def test_gonderildi_hatasi_ekransiz_mesaj_ve_ardisik_sayilir(tmp_path):
    class HepBelirsiz(SahteSayfa):
        def cevapla(self, y, metin):
            raise YorumIslemHatasi("belirsiz", gonderildi=True)
    db = DB(tmp_path / "f.db")
    b = SahteBildirim()
    with pytest.raises(YorumIslemHatasi):
        yon.yorumlari_isle(kanal(), db, SahteLLM(), SahteYorumcu(HepBelirsiz([H(f"u{i}", f"q{i}?") for i in range(5)])),
                           b, LOG, uyku=lambda s: None)
    assert sum(m.startswith("⚠️") for m in b.mesajlar) == 3


def test_yetki_hatasi_hemen_yukselir(tmp_path):
    class YetkisizSayfa(SahteSayfa):
        def cevapla(self, y, metin):
            raise YorumIslemHatasi("oturum kapalı", yetki=True)
    db = DB(tmp_path / "f.db")
    with pytest.raises(YorumIslemHatasi) as e:
        yon.yorumlari_isle(kanal(), db, SahteLLM(), SahteYorumcu(YetkisizSayfa([H("a", "q?")])),
                           SahteBildirim(), LOG, uyku=lambda s: None)
    assert e.value.yetki


def test_kuru_mod_eylemsiz_ve_kayitsiz(tmp_path):
    y = [H("a", "Is this real?"), H("e", "siktir git")]
    ozet, sayfa, b, db, _ = calistir(tmp_path, y, kuru=True)
    assert sayfa.eylemler == [] and b.mesajlar == [] and db.yorum_islenecekler("t1") == []


def test_baglam_eslesen_isten_gelir(tmp_path):
    db = DB(tmp_path / "f.db")
    is_ = db.is_olustur("t1")
    db.is_ilerlet(is_.id, "yuklendi", senaryo={"hook": "I found out on our first date.",
                                               "aciklama": "My first date with this guy seemed a little off."})
    assert "I found out" in yon.baglam_bul(db, "t1", "PART 1 | My first date with this guy seemed a little…")
    assert yon.baglam_bul(db, "t1", "PART 1 | Something else") is None


def test_hic_eylem_yoksa_ozet_gonderilmez(tmp_path):
    ozet, _, b, _, _ = calistir(tmp_path, [])
    assert b.mesajlar == []


def test_rapor_konuya_gore_gruplar(tmp_path):
    db = DB(tmp_path / "f.db")
    for i, (konu, oneri) in enumerate([("ses", "Slower"), ("ses", "Less robotic"), ("hikaye", "Part 3")]):
        kim = yorum_kimligi("t1", f"u{i}", "m", "v")
        db.yorum_ekle(kim, "t1", f"u{i}", "m", "v")
        db.yorum_karar(kim, "yapici", "c", konu, oneri)
    b = SahteBildirim()
    m = yon.rapor(kanal(), db, b, datetime.now())
    assert m.startswith("📊") and "(3)" in m
    assert m.index("• ses (2)") < m.index("• hikaye (1)") and '"Slower"' in m
    assert b.mesajlar == [m]


def test_rapor_bos(tmp_path):
    b = SahteBildirim()
    assert "yapıcı yorum yok" in yon.rapor(kanal(), DB(tmp_path / "f.db"), b, datetime.now())
