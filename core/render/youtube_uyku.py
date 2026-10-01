"""Hikâye sesi xN (aralarda sessizlik) + sürekli ortam sesi + döngülü video."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core import medya

KAPANIS_SN = 10.0   # son tekrardan sonra yalnızca yağmur sesi
_SES_BICIMI = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"


@dataclass
class YoutubeRender:
    tekrar: int
    sure_sn: float


def _anlatim_suresi(n: int, hikaye_sn: float, ara_sn: float) -> float:
    return n * hikaye_sn + (n - 1) * ara_sn


def tekrar_sayisi(hikaye_sn: float, ara_sn: float, hedef_sn: float, en_fazla: int) -> int:
    """Toplam anlatım süresi hedefe en yakın olan tekrar sayısı (eşitlikte büyük olan)."""
    return min(range(max(1, en_fazla), 0, -1),
               key=lambda n: abs(_anlatim_suresi(n, hikaye_sn, ara_sn) - hedef_sn))


def arka_plan_hazirla(arka_plan: Path) -> Path:
    """Yüksekliği 1080'den büyük arka planı bir kez 1080p'ye indirir ve yeniden kullanır."""
    arka_plan = Path(arka_plan)
    if medya.video_boyutu(arka_plan)[1] <= 1080:
        return arka_plan
    vekil = arka_plan.with_name(f"{arka_plan.stem}_1080p.mp4")
    if vekil.exists() and vekil.stat().st_mtime >= arka_plan.stat().st_mtime:
        return vekil
    gecici = arka_plan.with_name(f"{arka_plan.stem}_1080p.tmp.mp4")
    medya.ffmpeg([
        "-i", arka_plan, "-an", "-vf", "scale=-2:1080",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", gecici,
    ])
    os.replace(gecici, vekil)
    return vekil


def _anlatim_filtresi(n: int, ara_sn: float) -> str:
    """Her tekrar ayrı bir girdi (1..n): concat sırayla okur, tamponlama olmaz."""
    parcalar = [f"[{i}:a]{_SES_BICIMI},apad=pad_dur={ara_sn}[h{i}]" for i in range(1, n + 1)]
    if n == 1:
        return parcalar[0].replace("[h1]", "[anl]")
    etiketler = "".join(f"[h{i}]" for i in range(1, n + 1))
    return ";".join(parcalar) + f";{etiketler}concat=n={n}:v=0:a=1[anl]"


def render_youtube(arka_plan: Path, hikaye_ses: Path, ortam: Path, seviye: float, tekrar: int,
                   ara_sn: float, hedef_sn: float, cikti: Path) -> YoutubeRender:
    cikti = Path(cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    hikaye_sn = medya.sure(hikaye_ses)
    n = tekrar_sayisi(hikaye_sn, ara_sn, hedef_sn, tekrar)
    sure_sn = _anlatim_suresi(n, hikaye_sn, ara_sn) + KAPANIS_SN
    fade_d = min(30.0, sure_sn / 2)
    arka_plan = arka_plan_hazirla(arka_plan)
    filtre = (
        _anlatim_filtresi(n, ara_sn) + ";"
        f"[{n + 1}:a]{_SES_BICIMI},volume={seviye}[ort];"
        f"[anl][ort]amix=inputs=2:duration=longest:normalize=0,"
        f"alimiter=limit=0.95,"
        f"afade=t=out:st={sure_sn - fade_d}:d={fade_d}[a]"
    )
    medya.ffmpeg([
        "-stream_loop", "-1", "-i", arka_plan,
        *[a for _ in range(n) for a in ("-i", hikaye_ses)],
        "-stream_loop", "-1", "-i", ortam,
        "-filter_complex", filtre,
        "-map", "0:v:0", "-map", "[a]",
        "-t", f"{sure_sn:.2f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        cikti,
    ])
    return YoutubeRender(tekrar=n, sure_sn=sure_sn)
