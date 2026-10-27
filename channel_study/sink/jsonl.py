"""JSONL sink: everything, for the analyses nobody anticipated.

    <dir>/packets.jsonl   one object per packet heard — EVERY kind, including
                          the ones the tables skip (node info, routing, unmapped
                          telemetry, undecryptable traffic): {"record": the flat
                          reception record, "packet": the full MeshPacket dict}
    <dir>/events.jsonl    gaps opening and closing, and each sample of the
                          receiving radio's own position (--track-secs)
"""
from __future__ import annotations

import json
from pathlib import Path

from channel_study.gaps import GapEvent
from channel_study.records import Reception
from channel_study.sink import jsonable


class JsonlSink:
    def __init__(self, directory: str | Path, *, run_id: str, clock=None):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._clock = clock
        self._packets = open(self.dir / "packets.jsonl", "a")
        self._events = None

    def emit(self, rx: Reception) -> None:
        obj = {"record": rx.record(),
               "packet": jsonable(rx.decoded.raw, capture_content=rx.capture_content)}
        self._packets.write(json.dumps(obj, sort_keys=True) + "\n")
        self._packets.flush()

    def note(self, event: GapEvent) -> None:
        if self._events is None:
            self._events = open(self.dir / "events.jsonl", "a")
        now = self._clock() if self._clock else None
        self._events.write(json.dumps({"received_at": now, "run_id": self.run_id,
                                       "event": f"gap_{event.state}", "ref": event.ref,
                                       "kind": event.kind, "silent_s": round(event.silent_s, 1),
                                       "interval_s": event.interval}) + "\n")
        self._events.flush()

    def track(self, row: dict) -> None:
        self._events = self._events or open(self.dir / "events.jsonl", "a")
        self._events.write(json.dumps({"event": "own_position", **row}, sort_keys=True) + "\n")
        self._events.flush()

    def close(self) -> None:
        self._packets.close()
        if self._events is not None:
            self._events.close()
