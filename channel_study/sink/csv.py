"""CSV sink: one file per (node, kind), with a stable header.

    <dir>/N4_environment.csv    every column of records.columns("environment"),
                                whatever a given packet carried
    <dir>/gaps.csv              every gap opened and closed (silence is data)
    <dir>/track.csv             the receiving radio's own position, sampled over
                                USB on --track-secs (see channel_study.track)

A stable header means a file can be concatenated with another session's and
read without guessing which columns exist; an absent value is an empty cell,
never a 0.
"""
from __future__ import annotations

import csv
from pathlib import Path

from channel_study.gaps import GapEvent
from channel_study.records import TABLE_KINDS, Reception, columns
from channel_study.track import TRACK_COLUMNS, TRACK_FILE

GAP_COLUMNS = ["received_at", "run_id", "ref", "kind", "state", "silent_s", "interval_s"]


class CsvSink:
    def __init__(self, directory: str | Path, *, run_id: str, clock=None):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._clock = clock
        self._files: dict[str, tuple] = {}

    def _writer(self, name: str, header: list[str]):
        if name not in self._files:
            path = self.dir / name
            new = not path.exists() or path.stat().st_size == 0
            fh = open(path, "a", newline="")
            w = csv.DictWriter(fh, fieldnames=header, extrasaction="raise")
            if new:
                w.writeheader()
            self._files[name] = (fh, w)
        return self._files[name][1]

    def emit(self, rx: Reception) -> None:
        if rx.kind not in TABLE_KINDS:
            return
        header = columns(rx.kind)
        rec = rx.record()
        self._writer(f"{rx.ref}_{rx.kind}.csv", header).writerow({k: rec.get(k) for k in header})

    def note(self, event: GapEvent) -> None:
        now = self._clock() if self._clock else None
        self._writer("gaps.csv", GAP_COLUMNS).writerow({
            "received_at": round(now, 3) if now is not None else None, "run_id": self.run_id,
            "ref": event.ref, "kind": event.kind, "state": event.state,
            "silent_s": round(event.silent_s, 1), "interval_s": event.interval,
        })

    def track(self, row: dict) -> None:
        self._writer(TRACK_FILE, TRACK_COLUMNS).writerow(row)

    def close(self) -> None:
        for fh, _ in self._files.values():
            fh.close()
        self._files.clear()
