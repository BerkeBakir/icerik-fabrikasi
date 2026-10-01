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


def test_bos_liste_eksik_sayilmaz():
    sema = {"type": "object", "properties": {"a": {"type": "string"}, "l": {"type": "array", "items": {"type": "string"}}}, "required": ["a", "l"]}
    ist = SahteIstemci(['{"a": "x", "l": []}'])
    g = Gemini("k", istemci=ist, uyku=lambda s: None)
    result = g.json_uret("p", sema)
    assert result == {"a": "x", "l": []}
    assert len(ist.models.cagrilar) == 1


def test_bos_metin_eksik_sayilir():
    ist = SahteIstemci(['{"a": "  "}'] * 3)
    g = Gemini("k", istemci=ist, uyku=lambda s: None)
    with pytest.raises(LLMHatasi, match="eksik"):
        g.json_uret("p", SEMA)


def test_nesne_olmayan_json_hata():
    ist = SahteIstemci(['"[1,2]"'] * 3)
    g = Gemini("k", istemci=ist, uyku=lambda s: None)
    with pytest.raises(LLMHatasi, match="nesne"):
        g.json_uret("p", SEMA)


def test_afc_kapali():
    ist = SahteIstemci(['{"a": "b"}'])
    g = Gemini("k", istemci=ist)
    g.json_uret("p", SEMA)
    _, _, config = ist.models.cagrilar[0]
    assert config.automatic_function_calling.disable is True


# --- model yedekleme ---
from google.genai import errors as genai_hata  # noqa: E402


def _hata(sinif, kod, durum="UNAVAILABLE"):
    return sinif(kod, {"error": {"code": kod, "message": "high demand", "status": durum}}, None)


class ModelaGoreModeller:
    """model adina gore: Exception ornegi -> firlatir, str -> yanit doner."""

    def __init__(self, davranis):
        self.davranis = davranis
        self.cagrilar = []

    def generate_content(self, model, contents, config):
        self.cagrilar.append(model)
        d = self.davranis[model]
        if isinstance(d, Exception):
            raise d
        return Yanit(d)


class ModelIstemci:
    def __init__(self, davranis):
        self.models = ModelaGoreModeller(davranis)


def test_asiri_yukte_sonraki_modele_gecer():
    ist = ModelIstemci({"m1": _hata(genai_hata.ServerError, 503), "m2": '{"a": "b"}'})
    uykular = []
    g = Gemini("k", modeller=["m1", "m2"], istemci=ist, uyku=uykular.append)
    assert g.json_uret("p", SEMA) == {"a": "b"}
    assert ist.models.cagrilar == ["m1", "m1", "m2"]
    assert uykular == [10]


def test_429_asiri_yuk_sayilir():
    ist = ModelIstemci({"m1": _hata(genai_hata.ClientError, 429, "RESOURCE_EXHAUSTED"), "m2": '{"a": "b"}'})
    g = Gemini("k", modeller=["m1", "m2"], istemci=ist, uyku=lambda s: None)
    assert g.json_uret("p", SEMA) == {"a": "b"}
    assert ist.models.cagrilar == ["m1", "m1", "m2"]


def test_404_hemen_sonraki_model():
    ist = ModelIstemci({"m1": _hata(genai_hata.ClientError, 404, "NOT_FOUND"), "m2": '{"a": "b"}'})
    uykular = []
    g = Gemini("k", modeller=["m1", "m2"], istemci=ist, uyku=uykular.append)
    assert g.json_uret("p", SEMA) == {"a": "b"}
    assert ist.models.cagrilar == ["m1", "m2"]
    assert uykular == []


def test_tum_modeller_asiri_yuklu():
    ist = ModelIstemci({"m1": _hata(genai_hata.ServerError, 503), "m2": _hata(genai_hata.ServerError, 500)})
    g = Gemini("k", modeller=["m1", "m2"], istemci=ist, uyku=lambda s: None)
    with pytest.raises(LLMHatasi, match="Tüm Gemini"):
        g.json_uret("p", SEMA)
    assert ist.models.cagrilar == ["m1", "m1", "m2", "m2"]


@pytest.mark.parametrize("kod", [400, 401, 403])
def test_yetki_hatasi_hemen_firlar(kod):
    ist = ModelIstemci({"m1": _hata(genai_hata.ClientError, kod, "PERMISSION_DENIED"), "m2": '{"a": "b"}'})
    g = Gemini("k", modeller=["m1", "m2"], istemci=ist, uyku=lambda s: None)
    with pytest.raises(genai_hata.ClientError):
        g.json_uret("p", SEMA)
    assert ist.models.cagrilar == ["m1"]


def test_llm_hatasi_ayni_modelde_tekrar_sonra_firlar_yedege_gecmez():
    ist = ModelIstemci({"m1": "bozuk", "m2": '{"a": "b"}'})
    g = Gemini("k", modeller=["m1", "m2"], istemci=ist, uyku=lambda s: None)
    with pytest.raises(LLMHatasi, match="geçersiz"):
        g.json_uret("p", SEMA)
    assert ist.models.cagrilar == ["m1"] * 3


def test_eski_model_kwarg_tek_elemanli_liste():
    ist = SahteIstemci(['{"a": "b"}'])
    g = Gemini("k", model="m1", istemci=ist)
    assert g.modeller == ["m1"]
    g.json_uret("p", SEMA)
    assert ist.models.cagrilar[0][0] == "m1"


def test_varsayilan_modeller():
    from core.llm import VARSAYILAN_MODELLER
    g = Gemini("k", istemci=SahteIstemci([]))
    assert g.modeller == VARSAYILAN_MODELLER
    assert VARSAYILAN_MODELLER[0] == "gemini-2.5-flash"
