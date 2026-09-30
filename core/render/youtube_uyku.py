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
    on = f"[1:a]{_SES_BICIMI},apad=pad_dur={ara_sn}"
    if n == 1:
        return on + "[anl]"
    etiketler = "".join(f"[h{i}]" for i in range(n))
    return f"{on},asplit={n}{etiketler};{etiketler}concat=n={n}:v=0:a=1[anl]"


def render_youtube(arka_plan: Path, hikaye_ses: Path, ortam: Path, seviye: float, tekrar: int,
                   ara_sn: float, hedef_sn: float, cikti: Path) -> int:
    cikti = Path(cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    n = tekrar_sayisi(medya.sure(hikaye_ses), ara_sn, hedef_sn, tekrar)
    fade_d = min(30.0, hedef_sn / 2)
    filtre = (
        _anlatim_filtresi(n, ara_sn) + ";"
        f"[2:a]{_SES_BICIMI},volume={seviye}[ort];"
        f"[anl][ort]amix=inputs=2:duration=longest:normalize=0,"
        f"afade=t=out:st={hedef_sn - fade_d}:d={fade_d}[a]"
    )
    medya.ffmpeg([
        "-stream_loop", "-1", "-i", arka_plan,
        "-i", hikaye_ses,
        "-stream_loop", "-1", "-i", ortam,
        "-filter_complex", filtre,
        "-map", "0:v:0", "-map", "[a]",
        "-t", f"{hedef_sn:.2f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        cikti,
    ])
    return n
