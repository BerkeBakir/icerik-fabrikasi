from core.bildirim import Bildirim


class SahteOturum:
    def __init__(self, patla=False):
        self.cagrilar = []
        self.patla = patla

    def post(self, url, **kw):
        self.cagrilar.append((url, kw))
        if self.patla:
            raise ConnectionError("ag yok")


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
    o = SahteOturum(patla=True)
    Bildirim("T", "1", oturum=o).foto(tmp_path / "yok.png", "hata oldu")
    assert o.cagrilar[-1][0].endswith("/sendMessage")
