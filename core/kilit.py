"""Dosya kilidi: aynı anda tek TikTok yüklemesi.

İşletim sistemi düzeyinde danışma (advisory) kilidi kullanır: süreç ölürse kilidi
işletim sistemi kendisi bırakır, bu yüzden bayat kilit / devralma mantığı yoktur.
Kilit dosyası asla silinmez (silmek yarış durumlarına yol açar).
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class KilitHatasi(Exception):
    pass


def _kilitle_dene(f) -> None:
    """Bloklamadan özel kilit almayı dener; doluysa OSError fırlatır."""
    if os.name == "nt":
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _birak(f) -> None:
    if os.name == "nt":
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextmanager
def dosya_kilidi(yol: Path, bekle_sn: float = 1800, uyku=time.sleep):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    baslangic = time.monotonic()
    while True:
        f = open(yol, "a+b")
        try:
            _kilitle_dene(f)
            break
        except OSError:
            f.close()
            if time.monotonic() - baslangic > bekle_sn:
                raise KilitHatasi(f"Kilit boşalmadı: {yol}")
            uyku(10)
    try:
        yield
    finally:
        try:
            _birak(f)
        finally:
            f.close()
