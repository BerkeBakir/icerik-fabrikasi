"""Arka plan + ses + kelime vurgulu altyazı -> 1080x1920 MP4."""
from __future__ import annotations

import random
from pathlib import Path

from core import medya
from core.render.altyazi import ass_olustur
from core.tts import SesSonucu


def render_tiktok(arka_plan: Path, ses: SesSonucu, cikti: Path, rastgele=random) -> Path:
    cikti = Path(cikti).resolve()
    cikti.parent.mkdir(parents=True, exist_ok=True)
    ass_adi = cikti.stem + ".ass"
    (cikti.parent / ass_adi).write_text(ass_olustur(ses.kelimeler), encoding="utf-8")

    sure = ses.sure + 0.5
    bg_sure = medya.sure(arka_plan)
    if bg_sure > sure + 1:
        girdi = ["-ss", f"{rastgele.uniform(0, bg_sure - sure):.2f}", "-i", Path(arka_plan).resolve()]
    else:
        girdi = ["-stream_loop", "-1", "-i", Path(arka_plan).resolve()]

    vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,ass={ass_adi}"
    medya.ffmpeg([
        *girdi, "-i", Path(ses.yol).resolve(),
        "-map", "0:v:0", "-map", "1:a:0", "-t", f"{sure:.2f}",
        "-vf", vf, "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-af", "apad", "-movflags", "+faststart",
        cikti,
    ], cwd=cikti.parent)
    return cikti
