import logging
from unittest.mock import MagicMock

import requests

from core.bildirim import Bildirim


class FakeResponse:
    def __init__(self, kod=200):
        self.kod = kod

    def raise_for_status(self):
        if self.kod >= 400:
            raise requests.HTTPError(f"{self.kod} for url https://api.telegram.org/bot...")


class SahteOturum:
    def __init__(self, patla=False, kod=200, kod_dict=None):
        self.cagrilar = []
        self.patla = patla
        self.kod = kod
        self.kod_dict = kod_dict or {}

    def post(self, url, **kw):
        self.cagrilar.append((url, kw))
        if self.patla:
            raise ConnectionError(f"baglanti hatasi: {url}")
        # Use per-method code if available
        if self.kod_dict:
            metot = url.split("/")[-1]
            kod = self.kod_dict.get(metot, self.kod)
        else:
            kod = self.kod
        return FakeResponse(kod=kod)


def test_mesaj_gonderilir():
    o = SahteOturum()
    Bildirim("TOK", "42", oturum=o).mesaj("merhaba")
    url, kw = o.cagrilar[0]
    assert url == "https://api.telegram.org/botTOK/sendMessage"
    assert kw["data"] == {"chat_id": "42", "text": "merhaba"}


def test_token_yoksa_sessiz():
    o = SahteOturum()
    Bildirim(None, "42", oturum=o).mesaj("x")
    assert o.cagrilar == []


def test_ag_hatasi_yutulur():
    Bildirim("T", "1", oturum=SahteOturum(patla=True)).mesaj("x")


def test_foto_basarisizsa_mesaja_duser(tmp_path):
    # Foto gönderimi başarısız (kod 400), mesaj gönderilir (kod 200)
    foto_yolu = tmp_path / "a.png"
    foto_yolu.write_bytes(b"PNG")
    o = SahteOturum(kod_dict={"sendPhoto": 400, "sendMessage": 200})
    Bildirim("T", "1", oturum=o).foto(str(foto_yolu), "fallback")
    # sendPhoto sonra sendMessage çağrılmalı
    assert len(o.cagrilar) == 2
    assert o.cagrilar[0][0].endswith("/sendPhoto")
    assert o.cagrilar[1][0].endswith("/sendMessage")


def test_token_loga_sizmaz(tmp_path, caplog):
    # ConnectionError mesajında token varsa, log'ta gizlenmelidir
    o = SahteOturum(patla=True)
    logger = logging.getLogger("test_bildirim")
    with caplog.at_level(logging.WARNING, logger="test_bildirim"):
        Bildirim("GIZLITOKEN", "1", log=logger, oturum=o).mesaj("x")
    assert "GIZLITOKEN" not in caplog.text
    assert "***" in caplog.text


def test_http_hatasi_loglanir(caplog):
    # HTTP 401 hatasında warning loglanmalı, exception yükseltilmemelidir
    o = SahteOturum(kod=401)
    logger = logging.getLogger("test_bildirim")
    with caplog.at_level(logging.WARNING, logger="test_bildirim"):
        Bildirim("T", "1", log=logger, oturum=o).mesaj("x")
    assert "Telegram mesajı gönderilemedi" in caplog.text
