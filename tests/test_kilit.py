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


def test_eski_kilit_yeniden_adlandirma_permissionerror_yayilmaz(tmp_path, monkeypatch):
    yol = tmp_path / "a.kilit"
    yol.write_text("123")
    os.utime(yol, (0, 0))

    def _hata(*a, **k):
        raise PermissionError("kullanimda")

    monkeypatch.setattr(os, "replace", _hata)
    monkeypatch.setattr(os, "rename", _hata)
    with pytest.raises(KilitHatasi):
        with dosya_kilidi(yol, eski_sn=60, bekle_sn=-1, uyku=lambda s: None):
            pass


def test_bayat_devralma_sonrasi_eski_dosya_kalmaz(tmp_path):
    yol = tmp_path / "a.kilit"
    yol.write_text("123")
    os.utime(yol, (0, 0))
    with dosya_kilidi(yol, eski_sn=60):
        pass
    assert list(tmp_path.glob("*.eski")) == []
    assert not yol.exists()
