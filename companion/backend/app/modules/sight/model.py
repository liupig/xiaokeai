"""识别体验里的一份规格。小可爱不读这些对象，只读交出去的结果。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Phase:
    id: str
    label: str
    frames: int = 1
    detail: bool = False
    slots: tuple[str, ...] = ()
    say: str = ""
    speak: str = ""
    company: str = ""
    ahead: tuple[str, ...] = ()
    mark: str = ""
    look: bool = False
    ask: str = ""


@dataclass(frozen=True)
class Sub:
    id: str
    label: str
    kind: str
    scene: str
    match: str
    names: tuple[str, ...] = ()
    processes: tuple[str, ...] = ()
    titles: tuple[str, ...] = ()
    process_phase: dict[str, str] = field(default_factory=dict)
    phases: tuple[Phase, ...] = ()
    custom: bool = False

    def phase(self, phase_id: str) -> Phase | None:
        for item in self.phases:
            if item.id == phase_id:
                return item
        return None


@dataclass(frozen=True)
class Kind:
    id: str
    label: str
    scene: str
    configurable: bool
    interval: float
    template: tuple[Phase, ...]
    subs: tuple[Sub, ...]

    def sub(self, sub_id: str) -> Sub | None:
        for item in self.subs:
            if item.id == sub_id:
                return item
        return None


@dataclass(frozen=True)
class Hit:
    kind: str
    sub: str
    score: int
    phase_hint: str = ""
    surface: str = ""


@dataclass(frozen=True)
class Order:
    """这一眼眼睛该用的规格。active 为假时，眼睛保持原来的看法。"""
    active: bool = False
    kind: str = ""
    sub: str = ""
    phase: str = ""
    scene: str = ""
    prompt: str = ""
    frames: int = 0
    detail: bool = False
    interval: float = 0

    def public(self) -> dict:
        return {
            "active": self.active,
            "kind": self.kind,
            "sub": self.sub,
            "phase": self.phase,
            "scene": self.scene,
            "frames": self.frames,
            "detail": self.detail,
            "interval": self.interval,
            "prompt": self.prompt,
        }


@dataclass(frozen=True)
class Brief:
    """交给小可爱的一格结果。台词不在这里写。"""
    active: bool = False
    kind: str = ""
    kind_label: str = ""
    sub: str = ""
    sub_label: str = ""
    phase: str = ""
    phase_label: str = ""
    scene: str = ""
    surface: str = ""
    slots: dict[str, str] = field(default_factory=dict)
    still: bool = False
    handoff: str = ""
    speak: str = ""
    company: str = ""

    def public(self) -> dict:
        return {
            "active": self.active,
            "kind": self.kind,
            "kind_label": self.kind_label,
            "sub": self.sub,
            "sub_label": self.sub_label,
            "phase": self.phase,
            "phase_label": self.phase_label,
            "scene": self.scene,
            "surface": self.surface,
            "slots": dict(self.slots),
            "still": self.still,
            "handoff": self.handoff,
            "speak": self.speak,
            "company": self.company,
        }
