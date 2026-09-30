"""Basit dosya kilidi: aynı anda tek TikTok yüklemesi."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path


class KilitHatasi(Exception):
    pass


@contextmanager
def dosya_kilidi(yol: Path, bekle_sn: float = 1800, eski_sn: float = 7200, uyku=time.sleep):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    baslangic = time.time()
    while True:
        try:
            fd = os.open(yol, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                yas = time.time() - yol.stat().st_mtime
            except FileNotFoundError:
                continue
            if yas > eski_sn:
                yol.unlink(missing_ok=True)
                continue
            if time.time() - baslangic > bekle_sn:
                raise KilitHatasi(f"Kilit boşalmadı: {yol}")
            uyku(10)
    try:
        yield
    finally:
        yol.unlink(missing_ok=True)
