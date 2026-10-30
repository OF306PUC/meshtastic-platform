"""The receiving radio's own GPS track, sampled over USB instead of over the air.

A node's position reaches the mesh only when it broadcasts it, and a receiver
measuring a channel should not spend that channel on its own packets. Its fix,
though, is already on the serial link: the radio keeps its client's node
database current, so `getMyNodeInfo()["position"]` costs no airtime and can be
read as often as the GPS produces a fix (30 s on a receiver — see
`provision.plan.GPS_UPDATE_INTERVAL_S`). The copy that travels up the USB cable
is not a transmission; what the deployment file's `intervals.position` sets is
how often the radio also puts that position ON AIR, and that is the only part
that costs anything.

So the track has two cadences, deliberately separate:

* `intervals.position` in the deployment file — airtime, declared, measured by
  everyone who reads that file;
* `--track-secs` on the command line — a property of the laptop doing the
  recording, like `--port`, costing nothing and recorded in `session.json`.

A radio with no lock publishes `lat=0 lon=0` to its own log, so (0, 0) is
treated as the absence of a fix and counted apart: the library drops a zero
latitude from the position dictionary today (proto3 omits defaults), but Null
Island is one library change away from being recorded as a real point.

A sample with no fix is counted, and one identical to the previous fix — same
coordinates AND same GPS timestamp, so nothing new arrived — is marked
(`repeated`) rather than smoothed away. A receiver standing still with a live
GPS is not that: its timestamp keeps advancing, and those samples are real.
Telling the two apart is the whole reason the timestamp is part of the
comparison, because on a map they draw the same point.
"""
from __future__ import annotations

from dataclasses import dataclass

TRACK_FILE = "track.csv"
TRACK_COLUMNS = ["received_at", "run_id", "ref", "latitude", "longitude", "altitude",
                 "gps_time", "sats_in_view", "precision_bits", "repeated"]


def own_position(iface) -> dict:
    """The radio's own fix as its client knows it; {} when it has none.

    Raises whatever the library raises: a serial link that stopped answering is
    the receiver's problem to report, not this function's to hide.
    """
    return ((iface.getMyNodeInfo() or {}).get("position") or {})


@dataclass
class TrackStats:
    samples: int = 0        # times the local position was read
    fixes: int = 0          # reads that carried latitude and longitude
    repeated: int = 0       # fixes identical to the previous one
    no_fix: int = 0         # reads with no position at all
    discarded_zero: int = 0  # reads reporting (0, 0): no lock, not the Gulf of Guinea
    errors: int = 0         # reads that raised (counted by the caller)


class Tracker:
    """Samples the receiving radio's own position on a fixed period.

    `interval_s` of 0 disables it. The first `due()` is immediate, so a session
    records where it started even if it is stopped a minute later.
    """

    def __init__(self, *, run_id: str, ref: str, interval_s: float):
        self.run_id, self.ref = run_id, ref
        self.interval = interval_s
        self.stats = TrackStats()
        self._next: float | None = None
        self._last_key: tuple | None = None

    @property
    def enabled(self) -> bool:
        return self.interval > 0

    def due(self, mono: float) -> bool:
        return self.enabled and (self._next is None or mono >= self._next)

    def sample(self, position: dict | None, *, mono: float, wall: float) -> dict | None:
        """Record one reading; returns the row to write, or None without a fix.

        The clock moves on even when there is no fix, so a radio that never gets
        one is read once per period and no more.
        """
        self._next = mono + self.interval
        self.stats.samples += 1
        pos = position or {}
        lat, lon = pos.get("latitude"), pos.get("longitude")
        if lat is None or lon is None:
            self.stats.no_fix += 1
            return None
        if lat == 0 and lon == 0:
            # What the firmware itself publishes while it has no lock.
            self.stats.discarded_zero += 1
            self.stats.no_fix += 1
            return None
        key = (lat, lon, pos.get("time"))
        repeated = key == self._last_key
        self._last_key = key
        self.stats.fixes += 1
        if repeated:
            self.stats.repeated += 1
        return {
            "received_at": round(wall, 3),
            "run_id": self.run_id,
            "ref": self.ref,
            "latitude": lat,
            "longitude": lon,
            "altitude": pos.get("altitude"),
            "gps_time": pos.get("time"),
            "sats_in_view": pos.get("satsInView"),
            "precision_bits": pos.get("precisionBits"),
            "repeated": int(repeated),
        }

    def defer(self, mono: float) -> None:
        """Wait one more period without recording a sample.

        For a read that raised: the caller counts the error, and a serial link
        that stopped answering is retried once per period, not once per second.
        """
        self._next = mono + self.interval

    def as_dict(self) -> dict:
        return {"interval_s": self.interval, **self.stats.__dict__}

    def counters_lines(self) -> list[str]:
        """What the track is worth, in the words needed to distrust it."""
        if not self.enabled:
            return []
        s = self.stats
        line = f"own position: {s.fixes} fixes in {s.samples} samples every {self.interval:g} s"
        extra = {"no fix": s.no_fix, "of them at (0, 0)": s.discarded_zero,
                 "repeated the previous fix": s.repeated, "read errors": s.errors}
        tail = ", ".join(f"{v} {k}" for k, v in extra.items() if v)
        return [line + (f" ({tail})" if tail else "")]
