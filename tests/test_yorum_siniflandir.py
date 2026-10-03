import pytest

from core.yorum import HamYorum, YorumIslemHatasi
from core.yorum.siniflandir import Karar, istem, kufurlu, siniflandir


class SahteLLM:
    def __init__(self, yanit):
        self.yanit = yanit
        self.cagri = []

    def json_uret(self, prompt, sema, sicaklik=0.8):
        self.cagri.append((prompt, sema, sicaklik))
        return self.yanit


Y = HamYorum("ali", "Is this story real?", "PART 1 | My first date")


def test_hata_sinifi_alanlari():
    e = YorumIslemHatasi("x")
    assert e.ekran is None and e.yetki is False


@pytest.mark.parametrize("metin", ["you stupid bitch", "kill yourself", "amk ya", "siktir git", "f u c k you",
                                   "fuck you", "Orospu çocuğu", "what a retard", "seni piç"])
def test_kufurlu_yakalar(metin):
    assert kufurlu(metin)


@pytest.mark.parametrize("metin", ["holy shit this story", "NTA, you're not the asshole", "Is this real?",
                                   "classic AITA", "amkara", "Sikinti yok", "nice pic"])
def test_kufurlu_genel_argoyu_ve_masumlari_gecer(metin):
    assert not kufurlu(metin)


def test_kufurlu_yorumda_llm_cagrilmaz():
    llm = SahteLLM({"tur": "soru", "cevap": "x"})
    k = siniflandir(llm, HamYorum("a", "fuck you", "v"))
    assert k == Karar("hakaret", "", "", "") and llm.cagri == []


def test_soru_cevabi_temizlenir_ve_kisaltilir():
    llm = SahteLLM({"tur": "soru", "cevap": "  Yes! See https://x.com #reddit " + "a" * 300})
    k = siniflandir(llm, Y)
    assert k.tur == "soru" and "http" not in k.cevap and "#" not in k.cevap
    assert k.cevap.startswith("Yes! See") and len(k.cevap) <= 150
    assert k.konu == "" and k.oneri == ""


def test_yapici_konu_ve_oneri():
    k = siniflandir(SahteLLM({"tur": "yapici", "cevap": "Thanks, noted!", "konu": "ses",
                              "oneri": "Narration should be slower."}), Y)
    assert k == Karar("yapici", "Thanks, noted!", "ses", "Narration should be slower.")


def test_yapici_gecersiz_konu_digere_duser():
    assert siniflandir(SahteLLM({"tur": "yapici", "cevap": "ok", "konu": "renk", "oneri": "x"}), Y).konu == "diger"


def test_gecersiz_tur_yoruma_duser():
    assert siniflandir(SahteLLM({"tur": "övgü"}), Y) == Karar("yorum", "", "", "")


@pytest.mark.parametrize("yanit", [{"tur": "soru", "cevap": "   "}, {"tur": "soru", "cevap": "go fuck yourself"}])
def test_bos_ya_da_kufurlu_cevap_begeniye_duser(yanit):
    assert siniflandir(SahteLLM(yanit), Y).tur == "yorum"


def test_bos_cevapli_yapici_kaydi_korunur():
    k = siniflandir(SahteLLM({"tur": "yapici", "cevap": "", "konu": "altyazi", "oneri": "Bigger subtitles"}), Y)
    assert k == Karar("yorum", "", "altyazi", "Bigger subtitles")


@pytest.mark.parametrize("tur", ["yorum", "hakaret", "spam"])
def test_cevapsiz_turlerde_cevap_bosaltilir(tur):
    assert siniflandir(SahteLLM({"tur": tur, "cevap": "lol"}), Y).cevap == ""


def test_istem_baglam_ve_kurallari_icerir():
    p = istem(Y, "Story hook: I found out on our first date.")
    assert "Is this story real?" in p and "@ali" in p and "PART 1 | My first date" in p
    assert "Story hook: I found out" in p and "150" in p
    assert "Story context: (none)" in istem(Y, None)


def test_sema_ve_sicaklik():
    llm = SahteLLM({"tur": "yorum"})
    siniflandir(llm, Y)
    _, sema, sicaklik = llm.cagri[0]
    assert sema["required"] == ["tur"] and set(sema["properties"]) == {"tur", "cevap", "konu", "oneri"}
    assert sicaklik == 0.4
