from contextlib import ExitStack

import pytest

from core.kilit import KilitHatasi, dosya_kilidi


def test_kilit_alinir_ve_birakilir(tmp_path):
    yol = tmp_path / "k" / "a.kilit"
    with dosya_kilidi(yol):
        assert yol.exists()
    with dosya_kilidi(yol, bekle_sn=0):
        pass
    assert yol.exists()


def test_dolu_kilit_zaman_asimi(tmp_path):
    yol = tmp_path / "a.kilit"
    with dosya_kilidi(yol):
        with pytest.raises(KilitHatasi):
            with dosya_kilidi(yol, bekle_sn=0, uyku=lambda s: None):
                pass
    assert yol.exists()


def test_sahipsiz_dosya_kilitlenebilir(tmp_path):
    yol = tmp_path / "a.kilit"
    yol.write_text("123")  # cokmus surecten kalan, sahibi olmayan dosya
    with dosya_kilidi(yol, bekle_sn=0):
        pass


def test_bekleme_sonra_basarir(tmp_path):
    yol = tmp_path / "a.kilit"
    cagrilar = []
    with ExitStack() as yigin:
        yigin.enter_context(dosya_kilidi(yol))

        def uyku(sn):
            cagrilar.append(sn)
            yigin.close()

        with dosya_kilidi(yol, bekle_sn=60, uyku=uyku):
            pass
    assert cagrilar == [10]
