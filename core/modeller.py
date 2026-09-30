from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Hikaye:
    kimlik: str
    baslik: str
    govde: str


@dataclass
class TiktokSenaryo:
    hook: str
    part1: str
    part2: str
    aciklama: str
    etiketler: list[str] = field(default_factory=list)


@dataclass
class YoutubePaketi:
    baslik: str
    aciklama: str
    etiketler: list[str]
    hikaye: str
