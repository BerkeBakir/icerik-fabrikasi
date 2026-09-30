import os

import pytest

from core.kilit import KilitHatasi, dosya_kilidi


def test_kilit_alinir_ve_birakilir(tmp_path):
    yol = tmp_path / "k" / "a.kilit"
    with dosya_kilidi(yol):
        assert yol.exists()
    assert not yol.exists()


def test_dolu_kilit_zaman_asimi(tmp_path):
    yol = tmp_path / "a.kilit"
    yol.write_text("123")
    with pytest.raises(KilitHatasi):
        with dosya_kilidi(yol, bekle_sn=-1, uyku=lambda s: None):
            pass
    assert yol.exists()  # başkasının kilidine dokunulmaz


def test_eski_kilit_temizlenir(tmp_path):
    yol = tmp_path / "a.kilit"
    yol.write_text("123")
    os.utime(yol, (0, 0))
    with dosya_kilidi(yol, eski_sn=60):
        assert yol.read_text() == str(os.getpid())
