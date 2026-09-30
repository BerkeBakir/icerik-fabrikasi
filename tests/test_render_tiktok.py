import random
import subprocess

import pytest

from core import medya
from core.render.tiktok_dikey import render_tiktok
from core.tts import Kelime, SesSonucu


@pytest.mark.ffmpeg
def test_render_tiktok_uretir(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=640x360:rate=24", "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    ses = tmp_path / "ses.mp3"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=300:duration=2", ses])
    s = SesSonucu(ses, medya.sure(ses), [Kelime("hello", 0.1, 0.6), Kelime("world", 0.7, 1.5)])
    cikti = tmp_path / "out" / "p1.mp4"
    render_tiktok(bg, s, cikti, rastgele=random.Random(1))
    assert medya.sure(cikti) == pytest.approx(2.5, abs=0.3)
    akislar = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
                              "-of", "csv=p=0", str(cikti)], capture_output=True, text=True).stdout
    assert "video,1080,1920" in akislar and "audio" in akislar


@pytest.mark.ffmpeg
def test_kisa_arka_plan_dongulenir(tmp_path):
    bg = tmp_path / "bg.mp4"
    medya.ffmpeg(["-f", "lavfi", "-i", "testsrc=size=640x360:rate=24", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", bg])
    ses = tmp_path / "ses.mp3"
    medya.ffmpeg(["-f", "lavfi", "-i", "sine=duration=3", ses])
    cikti = tmp_path / "p.mp4"
    render_tiktok(bg, SesSonucu(ses, medya.sure(ses), [Kelime("a", 0, 1)]), cikti)
    assert medya.sure(cikti) == pytest.approx(3.5, abs=0.3)
