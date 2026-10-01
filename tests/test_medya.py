import subprocess

import pytest

from core import medya


@pytest.mark.ffmpeg
def test_sure_okunur(tmp_path):
    yol = tmp_path / "bir.wav"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=1.5", yol])
    assert medya.sure(yol) == pytest.approx(1.5, abs=0.05)


@pytest.mark.ffmpeg
def test_ffmpeg_hatasi_mesajla_firlatir(tmp_path):
    with pytest.raises(medya.MedyaHatasi, match="ffmpeg"):
        medya.ffmpeg(["-i", tmp_path / "olmayan.mp4", tmp_path / "x.mp4"])


@pytest.mark.ffmpeg
def test_sure_bozuk_dosyada_hata(tmp_path):
    yol = tmp_path / "bozuk.mp3"
    yol.write_bytes(b"abc")
    with pytest.raises(medya.MedyaHatasi):
        medya.sure(yol)


@pytest.mark.ffmpeg
def test_video_boyutu(tmp_path):
    yol = tmp_path / "v.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", yol])
    assert medya.video_boyutu(yol) == (320, 240)
