import pytest

from core import medya
from core.render.youtube_uyku import render_youtube, tekrar_sayisi


@pytest.mark.parametrize("hikaye,ara,hedef,en_fazla,beklenen", [
    (1200, 8, 5400, 5, 4),     # 20 dk hikâye: 4 tekrar sığar
    (1000, 8, 5400, 5, 5),     # 16.7 dk: 5 sığar
    (600, 8, 5400, 5, 5),      # kısa: en_fazla sınırı
    (6000, 8, 5400, 5, 1),     # hedeften uzun: en az 1
])
def test_tekrar_sayisi(hikaye, ara, hedef, en_fazla, beklenen):
    assert tekrar_sayisi(hikaye, ara, hedef, en_fazla) == beklenen


@pytest.mark.ffmpeg
def test_render_youtube_hedef_surede(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    hikaye = tmp_path / "h.wav"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=500:duration=2", hikaye])
    ortam = tmp_path / "r.mp3"
    medya.ffmpeg(["-f", "lavfi", "-i", "anoisesrc=d=1:a=0.1", ortam])
    cikti = tmp_path / "out" / "final.mp4"
    n = render_youtube(bg, hikaye, ortam, 0.3, tekrar=5, ara_sn=1, hedef_sn=10, cikti=cikti)
    assert n == 3
    assert medya.sure(cikti) == pytest.approx(10, abs=1.0)
