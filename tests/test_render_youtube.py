import re
import subprocess

import pytest

from core import medya
from core.render.youtube_uyku import (KAPANIS_SN, YoutubeRender, _anlatim_filtresi, arka_plan_hazirla,
                                      render_youtube, tekrar_sayisi)


@pytest.mark.parametrize("hikaye,ara,hedef,en_fazla,beklenen", [
    (1385, 8, 5400, 5, 4),     # 23 dk: 4 tekrar (5564 sn) hedefe en yakın
    (1200, 8, 5400, 5, 4),     # 4 tekrar 4824 sn, 5 tekrar 6032 sn -> 4 daha yakın
    (1000, 8, 5400, 5, 5),     # 5 tekrar 5032 sn
    (600, 8, 5400, 5, 5),      # kısa: en_fazla sınırı
    (6000, 8, 5400, 5, 1),     # hedeften uzun: en az 1
    (1800, 8, 5400, 5, 3),     # 3 tekrar 5416 sn
    (1000, 0, 3000, 5, 3),     # tam isabet
])
def test_tekrar_sayisi(hikaye, ara, hedef, en_fazla, beklenen):
    assert tekrar_sayisi(hikaye, ara, hedef, en_fazla) == beklenen


def test_tekrar_sayisi_esitlikte_buyuk_n():
    # L(1)=100, L(2)=200 -> hedef 150: eşit uzaklık, büyük n seçilir
    assert tekrar_sayisi(100, 0, 150, 5) == 2


@pytest.mark.ffmpeg
def test_render_youtube_hedef_surede(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    hikaye = tmp_path / "h.wav"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=500:duration=2", hikaye])
    ortam = tmp_path / "r.mp3"
    medya.ffmpeg(["-f", "lavfi", "-i", "anoisesrc=d=1:a=0.1", ortam])
    cikti = tmp_path / "out" / "final.mp4"
    r = render_youtube(bg, hikaye, ortam, 0.3, tekrar=5, ara_sn=1, hedef_sn=10, cikti=cikti)
    assert isinstance(r, YoutubeRender)
    assert r.tekrar == 4                       # L(3)=8, L(4)=11 -> 11, hedef 10'a daha yakın
    assert r.sure_sn == pytest.approx(11 + KAPANIS_SN)
    assert medya.sure(cikti) == pytest.approx(21, abs=1.0)


def test_anlatim_filtresi_asplit_kullanmaz():
    f = _anlatim_filtresi(3, 8)
    for parca in ("[1:a]", "[2:a]", "[3:a]", "concat=n=3", "apad=pad_dur=8"):
        assert parca in f
    assert "asplit" not in f


def test_anlatim_filtresi_tek():
    f = _anlatim_filtresi(1, 8)
    assert f.endswith("[anl]")
    assert "concat" not in f


@pytest.mark.ffmpeg
def test_render_youtube_hikaye_tekrar_eder(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    hikaye = tmp_path / "h.wav"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=500:duration=2", hikaye])
    ortam = tmp_path / "r.mp3"
    medya.ffmpeg(["-f", "lavfi", "-i", "anoisesrc=d=1:a=0.1", ortam])
    cikti = tmp_path / "out" / "sessiz_ortam.mp4"
    r = render_youtube(bg, hikaye, ortam, 0.0, tekrar=5, ara_sn=1, hedef_sn=10, cikti=cikti)
    assert r.tekrar == 4
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(cikti), "-af", "silencedetect=noise=-35dB:d=0.5", "-f", "null", "-"],
        capture_output=True, text=True)
    baslangiclar = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    assert len([b for b in baslangiclar if b < 11]) >= 3


@pytest.mark.ffmpeg
def test_arka_plan_hazirla_kucuk_klip_ayni_kalir(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    assert arka_plan_hazirla(bg) == bg


@pytest.mark.ffmpeg
def test_arka_plan_hazirla_buyuk_klip_1080pye_indirir_ve_yeniden_kullanir(tmp_path):
    bg = tmp_path / "gece.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=1280x1440:rate=5", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    proxy = arka_plan_hazirla(bg)
    assert proxy == tmp_path / "gece_1080p.mp4"
    assert medya.video_boyutu(proxy)[1] == 1080
    assert not (tmp_path / "gece_1080p.tmp.mp4").exists()
    mtime = proxy.stat().st_mtime_ns
    assert arka_plan_hazirla(bg) == proxy
    assert proxy.stat().st_mtime_ns == mtime
