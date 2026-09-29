import shutil

import pytest


def pytest_collection_modifyitems(config, items):
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    atla = pytest.mark.skip(reason="ffmpeg/ffprobe PATH'te yok")
    for item in items:
        if "ffmpeg" in item.keywords:
            item.add_marker(atla)
