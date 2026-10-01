from core.modeller import Hikaye
from core.senaryo import (PART1_SON, etiket_temizle, etiketleri_birlestir, serbest_hikaye,
                          tiktok_aciklama, tiktok_senaryo, youtube_paketi)


class SahteLLM:
    def __init__(self, cevap):
        self.cevap = cevap
        self.promptlar = []

    def json_uret(self, prompt, sema, sicaklik=0.8):
        self.promptlar.append(prompt)
        return dict(self.cevap)


def test_etiket_temizle():
    assert etiket_temizle("#Story Time!") == "storytime"
    assert etiket_temizle("  #") == ""
    assert etiket_temizle("çocuk_hikaye") == "çocuk_hikaye"


def test_etiketleri_birlestir_sabit_once_tekrarsiz():
    sonuc = etiketleri_birlestir(["storytime", "Reddit"], ["#reddit", "drama", "aita", "family"], 2)
    assert sonuc == ["storytime", "reddit", "drama", "aita"]


def test_tiktok_aciklama_etiketleri_siler():
    assert tiktok_aciklama(1, "Crazy story #fyp #x") == "PART 1 | Crazy story"
    assert tiktok_aciklama(2, "Crazy story").startswith("PART 2 (Final) | ")


def test_tiktok_aciklama_kredi_satiri_ekler():
    assert tiktok_aciklama(1, "Crazy story", "Background: Orbital") == "PART 1 | Crazy story\n\nBackground: Orbital"
    assert tiktok_aciklama(1, "Crazy story", "  ") == "PART 1 | Crazy story"
    uzun = tiktok_aciklama(1, "x" * 3000, "Background: Orbital")
    assert len(uzun) == 2000 and uzun.endswith("\n\nBackground: Orbital")


def test_tiktok_senaryo_hook_ve_son_cumleyi_garantiler():
    llm = SahteLLM({"hook": "You won't believe this.", "part1": "It started on Monday.",
                    "part2": "In the end he left.", "aciklama": "desc", "etiketler": ["#Drama", "aita"]})
    s = tiktok_senaryo(llm, Hikaye("reddit:1", "Baslik", "Govde {x}"), etiket_sayisi=3)
    assert s.part1.startswith("You won't believe this.")
    assert s.part1.endswith(PART1_SON)
    assert s.etiketler == ["drama", "aita"]
    assert "Govde {x}" in llm.promptlar[0]
    assert "3" in llm.promptlar[0]


def test_tiktok_senaryo_zaten_dogruysa_ekleme_yapmaz():
    p1 = f"You won't believe this. It started. {PART1_SON}"
    llm = SahteLLM({"hook": "You won't believe this.", "part1": p1, "part2": "x",
                    "aciklama": "d", "etiketler": []})
    assert tiktok_senaryo(llm, Hikaye("a", "b", "c"), 0).part1 == p1


def test_serbest_hikaye_kimligi_icerige_bagli():
    llm = SahteLLM({"baslik": "The Door", "govde": "Once upon a time."})
    h1 = serbest_hikaye(llm, "Write horror")
    h2 = serbest_hikaye(llm, "Write horror")
    assert h1.kimlik == h2.kimlik and h1.kimlik.startswith("uretim:")
    assert h1.baslik == "The Door"


def test_youtube_paketi_kelime_sayisini_prompta_koyar():
    llm = SahteLLM({"baslik": "Rainy Cabin", "aciklama": "d", "etiketler": ["#sleep", "rain"],
                    "hikaye": "word " * 100})
    p = youtube_paketi(llm, "Write a {kelime} word sleep story", 2500)
    assert "2500" in llm.promptlar[0]
    assert p.etiketler == ["sleep", "rain"]
    assert p.baslik == "Rainy Cabin"


def test_part1_kivrik_kesme_isareti():
    # part1 with curly apostrophe ‘ instead of regular apostrophe
    llm = SahteLLM({"hook": "You won’t believe.", "part1": "Follow so you don’t miss Part 2!",
                    "part2": "x", "aciklama": "d", "etiketler": []})
    s = tiktok_senaryo(llm, Hikaye("a", "b", "c"), 0)
    assert s.part1.count(PART1_SON) == 1
    assert s.part1.endswith(PART1_SON)


def test_part1_unlemsiz_son():
    # part1 ending without "!" but matching the body of PART1_SON
    llm = SahteLLM({"hook": "You won't believe.", "part1": "Follow so you don't miss Part 2",
                    "part2": "x", "aciklama": "d", "etiketler": []})
    s = tiktok_senaryo(llm, Hikaye("a", "b", "c"), 0)
    assert s.part1.endswith(PART1_SON)
    assert s.part1.count(PART1_SON) == 1


def test_part1_son_cumlesi_part2_icin_takip_ister():
    assert PART1_SON == "Follow so you don't miss Part 2!"


def test_tiktok_promptu_part2_sonra_paylasilir_der():
    llm = SahteLLM({"hook": "H.", "part1": "H. x", "part2": "y", "aciklama": "d", "etiketler": []})
    tiktok_senaryo(llm, Hikaye("a", "b", "c"), 0)
    prompt = llm.promptlar[0]
    assert "already on my profile" not in prompt
    assert "Part 2 is posted later" in prompt
