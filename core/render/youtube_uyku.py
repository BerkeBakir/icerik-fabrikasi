"""Hikâye sesi xN (aralarda sessizlik) + sürekli ortam sesi + döngülü video."""
from __future__ import annotations

import math
from pathlib import Path

from core import medya

_SES_BICIMI = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"


def tekrar_sayisi(hikaye_sn: float, ara_sn: float, hedef_sn: float, en_fazla: int) -> int:
    sigan = math.floor((hedef_sn + ara_sn) / (hikaye_sn + ara_sn))
    return max(1, min(en_fazla, sigan))


def _anlatim_filtresi(n: int, ara_sn: float) -> str:
    """Her tekrar ayrı bir girdi (1..n): concat sırayla okur, tamponlama olmaz."""
    parcalar = [f"[{i}:a]{_SES_BICIMI},apad=pad_dur={ara_sn}[h{i}]" for i in range(1, n + 1)]
    if n == 1:
        return parcalar[0].replace("[h1]", "[anl]")
    etiketler = "".join(f"[h{i}]" for i in range(1, n + 1))
    return ";".join(parcalar) + f";{etiketler}concat=n={n}:v=0:a=1[anl]"


def render_youtube(arka_plan: Path, hikaye_ses: Path, ortam: Path, seviye: float, tekrar: int,
                   ara_sn: float, hedef_sn: float, cikti: Path) -> int:
    cikti = Path(cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    n = tekrar_sayisi(medya.sure(hikaye_ses), ara_sn, hedef_sn, tekrar)
    fade_d = min(30.0, hedef_sn / 2)
    filtre = (
        _anlatim_filtresi(n, ara_sn) + ";"
        f"[{n + 1}:a]{_SES_BICIMI},volume={seviye}[ort];"
        f"[anl][ort]amix=inputs=2:duration=longest:normalize=0,"
        f"alimiter=limit=0.95,"
        f"afade=t=out:st={hedef_sn - fade_d}:d={fade_d}[a]"
    )
    medya.ffmpeg([
        "-stream_loop", "-1", "-i", arka_plan,
        *[a for _ in range(n) for a in ("-i", hikaye_ses)],
        "-stream_loop", "-1", "-i", ortam,
        "-filter_complex", filtre,
        "-map", "0:v:0", "-map", "[a]",
        "-t", f"{hedef_sn:.2f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        cikti,
    ])
    return n
