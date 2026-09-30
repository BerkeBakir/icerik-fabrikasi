import pytest

from core.upload.youtube import YukleHatasi, govde_olustur, kimlik_yukle, yukle


def test_govde_sinirlari_ve_temizlik():
    g = govde_olustur("A <b> title " + "x" * 200, "desc <x>", ["t" * 60] * 20, "22", "private")
    assert len(g["snippet"]["title"]) <= 100 and "<" not in g["snippet"]["title"]
    assert "<" not in g["snippet"]["description"]
    assert sum(len(t) + 2 for t in g["snippet"]["tags"]) <= 480
    assert g["snippet"]["categoryId"] == "22"
    assert g["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}


class SahteIstek:
    def __init__(self, adimlar):
        self.adimlar = list(adimlar)

    def next_chunk(self):
        a = self.adimlar.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


class SahteServis:
    def __init__(self, istek):
        self.istek = istek
        self.govde = None

    def videos(self):
        return self

    def insert(self, part, body, media_body):
        self.govde = body
        return self.istek


def test_baglanti_hatasinda_devam_eder(tmp_path, monkeypatch):
    monkeypatch.setattr("core.upload.youtube.MediaFileUpload", lambda *a, **k: object())
    istek = SahteIstek([ConnectionError("koptu"), (None, None), (None, {"id": "vid1"})])
    beklemeler = []
    vid = yukle(None, tmp_path / "v.mp4", "t", "d", [], "22", "private",
                servis=SahteServis(istek), uyku=beklemeler.append)
    assert vid == "vid1"
    assert beklemeler == [2]


def test_cok_hata_vazgecer(tmp_path, monkeypatch):
    monkeypatch.setattr("core.upload.youtube.MediaFileUpload", lambda *a, **k: object())
    istek = SahteIstek([ConnectionError("x")] * 5)
    with pytest.raises(YukleHatasi):
        yukle(None, tmp_path / "v.mp4", "t", "d", [], "22", "private",
              servis=SahteServis(istek), deneme=3, uyku=lambda s: None)


def test_token_yoksa_etkilesimsiz_hata(tmp_path):
    with pytest.raises(YukleHatasi, match="--giris"):
        kimlik_yukle(tmp_path / "t.json", tmp_path / "cs.json", tmp_path / "eski.pickle", etkilesimli=False)
