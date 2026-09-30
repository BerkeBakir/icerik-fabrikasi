import numpy as np
import pytest
import soundfile as sf

from core.tts import Kelime, SesSonucu, TTSHatasi, YedekliTTS
from core.tts.edge import EdgeTTS
from core.tts.kokoro import KokoroTTS


class SahteIletisim:
    def __init__(self, metin, ses, rate, boundary):
        assert boundary == "WordBoundary"
        self.metin, self.ses, self.rate = metin, ses, rate

    async def stream(self):
        yield {"type": "audio", "data": b"ID3abc"}
        yield {"type": "WordBoundary", "offset": 1_000_000, "duration": 2_500_000, "text": "Hello"}
        yield {"type": "audio", "data": b"def"}
        yield {"type": "WordBoundary", "offset": 4_000_000, "duration": 3_000_000, "text": "there"}


def test_edge_ses_ve_kelime_zamanlari(tmp_path):
    t = EdgeTTS("ses1", "+10%", iletisim=SahteIletisim, sure_fn=lambda p: 1.2)
    s = t.seslendir("Hello there", tmp_path / "a.mp3")
    assert (tmp_path / "a.mp3").read_bytes() == b"ID3abcdef"
    assert s.sure == 1.2
    assert s.kelimeler == [Kelime("Hello", 0.1, 0.35), Kelime("there", 0.4, 0.7)]


class BosIletisim(SahteIletisim):
    async def stream(self):
        if False:
            yield {}


def test_edge_bos_ses_hata(tmp_path):
    t = EdgeTTS("s", iletisim=BosIletisim, sure_fn=lambda p: 0, uyku=lambda s: None)
    with pytest.raises(TTSHatasi):
        t.seslendir("x", tmp_path / "a.mp3")


def test_ses_sonucu_sozluk_gidis_donus(tmp_path):
    s = SesSonucu(tmp_path / "a.mp3", 2.0, [Kelime("a", 0.0, 0.5)])
    assert SesSonucu.sozlukten(s.sozluk()) == s


class SahtePipeline:
    def __init__(self):
        self.cagrilar = []

    def __call__(self, metin, voice, speed):
        self.cagrilar.append((metin, voice, speed))
        yield "g", "p", np.ones(2400, dtype=np.float32)


def test_kokoro_paragraflar_arasi_sessizlik(tmp_path):
    pl = SahtePipeline()
    t = KokoroTTS("af_heart", 0.85, paragraf_arasi=0.5, pipeline=pl)
    s = t.seslendir("Bir.\n\nIki.", tmp_path / "h.mp3")
    assert s.yol == tmp_path / "h.wav"
    veri, oran = sf.read(s.yol)
    assert oran == 24000
    assert len(veri) == 2 * 2400 + 2 * 12000
    assert s.sure == pytest.approx(len(veri) / 24000)
    assert pl.cagrilar[0] == ("Bir.", "af_heart", 0.85)


class Patlayan:
    def seslendir(self, metin, cikti):
        raise RuntimeError("model yok")


class Calisan:
    def seslendir(self, metin, cikti):
        return SesSonucu(cikti, 1.0, [])


def test_yedekli_tts_yedege_duser(tmp_path):
    s = YedekliTTS(Patlayan(), Calisan()).seslendir("x", tmp_path / "a.mp3")
    assert s.sure == 1.0
