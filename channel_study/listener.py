"""The channel-study listener: decoded packets -> receptions -> sinks.

The command-line program is receiver.py at the repository root; this module is
what it wires up, kept importable so it is tested with fixtures and injected
clocks instead of a radio.

Measurement policy lives here, not in the decoder: the clock (wall time for
display and records, monotonic time for gaps), duplicate detection (a
rebroadcast heard twice is marked, never dropped), and which flows are
expected (the registry's cadences, and nothing else).
"""
from __future__ import annotations

import collections
import sys
import threading
import time
from typing import Callable

from channel_study.gaps import GapEvent, GapWatcher
from channel_study.records import Reception
from channel_study.summary import Summary
from meshtastic_platform.decode import FLOW_KINDS, DecodeStats, decode
from meshtastic_platform.registry import Node, Registry

KINDS = ("device", "environment", "position", "text", "private")
SEEN_MAX = 512


def expected_flows(reg: Registry, *, exclude_node_id: str | None,
                   nodes: set[str] | None, kinds: set[str] | None) -> dict[tuple[str, str], int]:
    """(ref, kind) -> effective cadence for every flow this session should hear."""
    out = {}
    for n in reg.nodes:
        if not n.node_id or n.node_id == exclude_node_id or n.status == "retired":
            continue
        if nodes and n.ref not in nodes:
            continue
        for kind, secs in reg.intervals(n).items():
            if kind in FLOW_KINDS and (not kinds or kind in kinds):
                out[(n.ref, kind)] = secs
    return out


class ChannelStudyReceiver:
    def __init__(self, reg: Registry, sinks: list, *, run_id: str,
                 my_id: str | None, my_num: int | None, rx_node: Node | None,
                 wall: Callable[[], float] = time.time,
                 mono: Callable[[], float] = time.monotonic,
                 nodes: set[str] | None = None, kinds: set[str] | None = None,
                 capture_content: bool = False):
        self.reg, self.sinks, self.run_id = reg, sinks, run_id
        self.my_id, self.my_num, self.rx_node = my_id, my_num, rx_node
        self.wall, self.mono = wall, mono
        self.nodes, self.kinds = nodes or None, kinds or None
        self.capture_content = capture_content
        self.known = reg.known_nodes()
        self.stats = DecodeStats()
        self.summary = Summary()
        self.errors = 0
        self._seen: collections.OrderedDict = collections.OrderedDict()
        self._lock = threading.Lock()
        self.gaps = GapWatcher(expected_flows(reg, exclude_node_id=my_id, nodes=self.nodes,
                                              kinds=self.kinds), start=mono())

    def pubsub_listener(self, packet, interface) -> None:
        """The pubsub subscriber. Both arguments required, exactly as the
        library sends them: pypubsub checks listener signatures against the
        topic spec the library's sendMessage calls define."""
        self.on_packet(packet, interface)

    def on_packet(self, packet, interface=None) -> None:
        try:
            with self._lock:
                self._handle(packet)
        except Exception as exc:                       # loud, counted, never silent
            self.errors += 1
            print(f"[ERROR] processing packet: {exc!r}", file=sys.stderr)

    def _handle(self, packet) -> None:
        d = decode(packet, known_nodes=self.known)
        own = d.from_id is not None and (d.from_id == self.my_id or
                                         (d.from_num is not None and d.from_num == self.my_num))
        self.stats.record(d, sender_known=d.known or own)
        if d.kind == "empty":
            return
        if own:
            ref = self.rx_node.ref if self.rx_node else "self"
        else:
            ref = d.node.ref if d.node is not None else (d.from_id or "?")
        if self.nodes and ref not in self.nodes:
            return
        if self.kinds and d.kind not in self.kinds:
            return

        duplicate = False
        if d.packet_id is not None and d.from_num is not None:
            key = (d.from_num, d.packet_id)
            duplicate = key in self._seen
            self._seen[key] = None
            self._seen.move_to_end(key)
            while len(self._seen) > SEEN_MAX:
                self._seen.popitem(last=False)

        rx = Reception(decoded=d, received_at=self.wall(), run_id=self.run_id,
                       deployment=self.reg.name, ref=ref, duplicate=duplicate, own=own,
                       rx_node=self.rx_node, capture_content=self.capture_content)
        if not own:
            self.summary.add(ref, d.kind, d.hops_taken, d.rx_rssi, d.rx_snr, duplicate)
        events = []
        if not duplicate and not own:
            now = self.mono()
            for kind in d.flows:
                ev = self.gaps.observe(ref, kind, now)
                if ev is not None:
                    events.append(ev)
        for sink in self.sinks:
            sink.emit(rx)
        for ev in events:
            self._note(ev)

    def _note(self, ev: GapEvent) -> None:
        for sink in self.sinks:
            note = getattr(sink, "note", None)
            if note is not None:
                note(ev)

    def tick(self) -> None:
        with self._lock:
            for ev in self.gaps.check(self.mono()):
                self._note(ev)

    def summary_rows(self) -> list[dict]:
        return self.summary.rows(self.gaps.gaps)

    def counters_lines(self) -> list[str]:
        s = self.stats
        lines = [f"packets {s.packets} · by kind {dict(s.by_kind)}"]
        silent = {
            "undecryptable (other PSK / mesh)": s.by_kind.get("encrypted", 0),
            "unhandled portnums": dict(s.unknown_portnum),
            "unhandled telemetry variants": dict(s.unhandled_telemetry),
            "senders not in the registry": dict(s.unknown_sender),
            "processing errors": self.errors,
        }
        for label, value in silent.items():
            if value:
                lines.append(f"{label}: {value}")
        return lines

    def close(self) -> None:
        for sink in self.sinks:
            sink.close()
