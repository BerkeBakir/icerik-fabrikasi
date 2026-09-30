import json
from datetime import datetime, timedelta

import httplib2
import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from core.upload.youtube import SCOPES, YukleHatasi, govde_olustur, kimlik_yukle, yukle


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
    beklemeler = []
    with pytest.raises(YukleHatasi):
        yukle(None, tmp_path / "v.mp4", "t", "d", [], "22", "private",
              servis=SahteServis(istek), deneme=3, uyku=beklemeler.append)
    assert len(istek.adimlar) == 1  # next_chunk tam 4 kez cagrildi
    assert beklemeler == [2, 4, 8]


def _yukle(tmp_path, monkeypatch, adimlar, deneme=10, baslik="t", aciklama="d"):
    monkeypatch.setattr("core.upload.youtube.MediaFileUpload", lambda *a, **k: object())
    servis = SahteServis(SahteIstek(adimlar))
    bekle = []
    vid = yukle(None, tmp_path / "v.mp4", baslik, aciklama, [], "22", "private",
                servis=servis, deneme=deneme, uyku=bekle.append)
    return vid, bekle, servis


def _http(kod):
    return HttpError(resp=httplib2.Response({"status": kod}), content=b"x")


def test_ardisik_sayac_basarida_sifirlanir(tmp_path, monkeypatch):
    e = ConnectionError("x")
    vid, _, _ = _yukle(tmp_path, monkeypatch,
                       [e, (None, None), e, (None, None), e, (None, {"id": "v"})], deneme=1)
    assert vid == "v"


def test_tekrarlanabilir_http_hatasi(tmp_path, monkeypatch):
    vid, bekle, _ = _yukle(tmp_path, monkeypatch, [_http(503), (None, {"id": "v"})])
    assert vid == "v" and bekle == [2]


def test_kalici_http_hatasi_hemen_vazgecer(tmp_path, monkeypatch):
    with pytest.raises(YukleHatasi):
        _yukle(tmp_path, monkeypatch, [_http(403)])


def test_httplib2_hatasi_tekrarlanir(tmp_path, monkeypatch):
    vid, bekle, _ = _yukle(tmp_path, monkeypatch,
                           [httplib2.ServerNotFoundError("x"), (None, {"id": "v"})])
    assert vid == "v" and bekle == [2]


def test_aciklama_bayt_siniri():
    g = govde_olustur("t", "ş" * 3000, [], "22", "private")
    b = g["snippet"]["description"].encode("utf-8")
    assert len(b) <= 4900
    b.decode("utf-8")
    assert govde_olustur("<>", "d", [], "22", "private")["snippet"]["title"] == "Sleep Story"


def test_govde_insert_e_gecer(tmp_path, monkeypatch):
    _, _, servis = _yukle(tmp_path, monkeypatch, [(None, {"id": "v"})], baslik="A <b> baslik")
    assert servis.govde["snippet"]["title"] == "A b baslik"


def _creds(**kw):
    return Credentials(token="t", refresh_token="r", token_uri="https://oauth2.googleapis.com/token",
                       client_id="c", client_secret="s", scopes=SCOPES, **kw)


def test_eski_pickle_json_a_tasinir(tmp_path):
    import pickle
    c = _creds(expiry=datetime.utcnow() + timedelta(hours=1))
    with open(tmp_path / "eski.pickle", "wb") as f:
        pickle.dump(c, f)
    sonuc = kimlik_yukle(tmp_path / "t.json", tmp_path / "cs.json", tmp_path / "eski.pickle")
    assert sonuc.valid
    assert '"refresh_token": "r"' in (tmp_path / "t.json").read_text(encoding="utf-8")
    assert not (tmp_path / "t.json.tmp").exists()


def test_iptal_edilmis_token_giris_ister(tmp_path, monkeypatch):
    c = _creds(expiry=datetime.utcnow() - timedelta(hours=1))
    (tmp_path / "t.json").write_text(c.to_json(), encoding="utf-8")

    def boz(self, request):
        raise RefreshError("revoked")
    monkeypatch.setattr(Credentials, "refresh", boz)
    with pytest.raises(YukleHatasi, match="--giris"):
        kimlik_yukle(tmp_path / "t.json", tmp_path / "cs.json")


def test_bozuk_json_token_giris_ister(tmp_path):
    (tmp_path / "t.json").write_text("{bozuk", encoding="utf-8")
    with pytest.raises(YukleHatasi, match="--giris"):
        kimlik_yukle(tmp_path / "t.json", tmp_path / "cs.json")


def test_token_yoksa_etkilesimsiz_hata(tmp_path):
    with pytest.raises(YukleHatasi, match="--giris"):
        kimlik_yukle(tmp_path / "t.json", tmp_path / "cs.json", tmp_path / "eski.pickle", etkilesimli=False)


def test_giris_gerektiren_hata_yetki_isaretli(tmp_path):
    with pytest.raises(YukleHatasi) as h:
        kimlik_yukle(tmp_path / "t.json", tmp_path / "cs.json", etkilesimli=False)
    assert h.value.yetki is True


def test_client_secret_yoksa_yetki_isaretsiz(tmp_path):
    with pytest.raises(YukleHatasi) as h:
        kimlik_yukle(tmp_path / "t.json", tmp_path / "cs.json", etkilesimli=True)
    assert h.value.yetki is False
