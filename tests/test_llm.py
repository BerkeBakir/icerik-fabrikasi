import pytest

from core.llm import Gemini, LLMHatasi


class Yanit:
    def __init__(self, text):
        self.text = text


class SahteModeller:
    def __init__(self, cevaplar):
        self.cevaplar = list(cevaplar)
        self.cagrilar = []

    def generate_content(self, model, contents, config):
        self.cagrilar.append((model, contents, config))
        return Yanit(self.cevaplar.pop(0))


class SahteIstemci:
    def __init__(self, cevaplar):
        self.models = SahteModeller(cevaplar)


SEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def test_json_doner_ve_sema_iletilir():
    ist = SahteIstemci(['{"a": "b"}'])
    g = Gemini("k", model="m1", istemci=ist)
    assert g.json_uret("p", SEMA) == {"a": "b"}
    model, contents, config = ist.models.cagrilar[0]
    assert model == "m1" and contents == "p"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == SEMA


def test_gecersiz_json_tekrar_denenir():
    ist = SahteIstemci(["bozuk", '{"a": "b"}'])
    g = Gemini("k", istemci=ist, uyku=lambda s: None)
    assert g.json_uret("p", SEMA) == {"a": "b"}


def test_eksik_alan_uc_denemeden_sonra_hata():
    ist = SahteIstemci(['{"a": ""}'] * 3)
    g = Gemini("k", istemci=ist, uyku=lambda s: None)
    with pytest.raises(LLMHatasi, match="eksik"):
        g.json_uret("p", SEMA)
