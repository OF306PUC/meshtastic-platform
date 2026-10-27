"""Silence is evidence: make gaps visible while they happen.

Every expected flow (node, kind) has a cadence in the registry. When a flow has
been silent for more than FACTOR x its cadence, that is announced once, as it
happens — not discovered later in a plot — and again when the flow comes back,
with the total length. A flow that never arrives at all is announced too: the
clock starts at session start, not at the first reception.

Time is injected (a monotonic clock), so this is tested without waiting.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

FACTOR = 1.5


@dataclass
class _Flow:
    interval: int
    last: float
    in_gap: bool = False


@dataclass(frozen=True)
class GapEvent:
    ref: str
    kind: str
    silent_s: float
    interval: int
    state: str          # "open" (crossed the threshold) | "closed" (flow is back)

    def text(self) -> str:
        if self.state == "open":
            return f"── no reception from {self.ref}/{short(self.kind)} for {self.silent_s:.0f} s ──"
        return f"── {self.ref}/{short(self.kind)} back after {self.silent_s:.0f} s ──"


_SHORT = {"environment": "env", "position": "pos"}


def short(kind: str) -> str:
    return _SHORT.get(kind, kind)


class GapWatcher:
    def __init__(self, expected: dict[tuple[str, str], int], start: float, factor: float = FACTOR):
        self.factor = factor
        self._flows = {flow: _Flow(iv, start) for flow, iv in expected.items()}
        self.gaps: Counter = Counter()          # (ref, kind) -> gaps detected

    @property
    def flows(self) -> list[tuple[str, str]]:
        return list(self._flows)

    def observe(self, ref: str, kind: str, now: float) -> GapEvent | None:
        f = self._flows.get((ref, kind))
        if f is None:
            return None
        event = None
        if f.in_gap:
            event = GapEvent(ref, kind, now - f.last, f.interval, "closed")
            f.in_gap = False
        f.last = now
        return event

    def check(self, now: float) -> list[GapEvent]:
        out = []
        for (ref, kind), f in self._flows.items():
            silent = now - f.last
            if not f.in_gap and silent > self.factor * f.interval:
                f.in_gap = True
                self.gaps[(ref, kind)] += 1
                out.append(GapEvent(ref, kind, silent, f.interval, "open"))
        return out
