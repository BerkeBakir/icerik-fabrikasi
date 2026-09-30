import pytest

from core.tekrar import tekrar_dene


def test_ikinci_denemede_basarir():
    cagri = {"n": 0}
    beklemeler = []

    def fn():
        cagri["n"] += 1
        if cagri["n"] < 2:
            raise ValueError("gecici")
        return "tamam"

    assert tekrar_dene(fn, deneme=3, bekleme=5, uyku=beklemeler.append) == "tamam"
    assert beklemeler == [5]


def test_ussel_bekleme_ve_son_hata():
    beklemeler = []

    def fn():
        raise ValueError("hep")

    with pytest.raises(ValueError, match="hep"):
        tekrar_dene(fn, deneme=3, bekleme=2, carpan=3, uyku=beklemeler.append)
    assert beklemeler == [2, 6]


def test_listede_olmayan_hata_hemen_firlar():
    beklemeler = []

    def fn():
        raise KeyError("x")

    with pytest.raises(KeyError):
        tekrar_dene(fn, deneme=3, hatalar=(ValueError,), uyku=beklemeler.append)
    assert beklemeler == []
