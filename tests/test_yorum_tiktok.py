import pytest

from core.yorum.tiktok_yorum import video_yolu_bul, yas_gun


@pytest.mark.parametrize("metin,gun", [("2h ago", 2 / 24), ("35m ago", 35 / 1440), ("3d ago", 3.0),
                                       ("1w ago", 7.0), ("Just now", 0.0), ("now", 0.0)])
def test_yas_gun(metin, gun):
    assert yas_gun(metin) == pytest.approx(gun)


@pytest.mark.parametrize("metin", ["10-01", "2026-09-12", ""])
def test_yas_gun_tarih_bilinmez(metin):
    assert yas_gun(metin) is None


def test_video_yolu_bul():
    satirlar = [("/@slumberlab/video/111", "PART 2 (Final) | Our financial stress is at an all-time high"),
                ("/@slumberlab/video/222", "PART 1 | Our financial stress is at an all-time high")]
    assert video_yolu_bul(satirlar, "PART 1 | Our financial stress is at an all-ti…") == "/@slumberlab/video/222"
    assert video_yolu_bul(satirlar, "PART 2 (Final) | Our financial") == "/@slumberlab/video/111"
    assert video_yolu_bul(satirlar, "PART 1 | Something else") is None
