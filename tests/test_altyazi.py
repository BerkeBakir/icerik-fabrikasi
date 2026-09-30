from core.render.altyazi import ass_olustur, satirlara_bol
from core.tts import Kelime


def k(m, b, e):
    return Kelime(m, b, e)


def test_satirlara_bol_en_fazla_ve_noktalama():
    ks = [k("a", 0, 1), k("b.", 1, 2), k("c", 2, 3), k("d", 3, 4), k("e", 4, 5), k("f", 5, 6)]
    assert [[x.metin for x in s] for s in satirlara_bol(ks, en_fazla=3)] == [["a", "b."], ["c", "d", "e"], ["f"]]


def test_ass_vurgulu_kelime_olaylari():
    ks = [k("hi", 0.0, 0.4), k("{you}", 0.5, 1.23)]
    ass = ass_olustur(ks)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    olaylar = [s for s in ass.splitlines() if s.startswith("Dialogue:")]
    assert olaylar[0] == r"Dialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,{\c&H00FFFF&}HI{\c&HFFFFFF&} (YOU)"
    assert olaylar[1] == r"Dialogue: 0,0:00:00.50,0:00:01.23,Default,,0,0,0,,HI {\c&H00FFFF&}(YOU){\c&HFFFFFF&}"


def test_ass_saat_bicimi_ve_sifir_sure():
    ass = ass_olustur([k("x", 3725.5, 3725.5)])
    assert "1:02:05.50,1:02:05.55" in ass
