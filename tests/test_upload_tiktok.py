from datetime import datetime

import pytest

from core.upload.tiktok import TikTokHatasi, zamani_yuvarla


@pytest.mark.parametrize("girdi,beklenen", [
    (datetime(2026, 9, 29, 14, 0, 0), datetime(2026, 9, 29, 14, 0)),
    (datetime(2026, 9, 29, 14, 0, 1), datetime(2026, 9, 29, 14, 5)),
    (datetime(2026, 9, 29, 14, 7, 30), datetime(2026, 9, 29, 14, 10)),
    (datetime(2026, 9, 29, 23, 58), datetime(2026, 9, 30, 0, 0)),
])
def test_zamani_yuvarla(girdi, beklenen):
    assert zamani_yuvarla(girdi) == beklenen


def test_hata_ekran_goruntusu_tasir(tmp_path):
    h = TikTokHatasi("x", ekran=tmp_path / "a.png")
    assert h.ekran == tmp_path / "a.png" and str(h) == "x"
