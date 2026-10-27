"""Terminal output. The column ORDER is part of the specification.

    HH:MM:SS  ref   kind    hops  RSSI    SNR  payload
    ───────────────────────────────────────────────────────────────────
    10:42:17  N4    env        0   -78   +9.5  T=22.4C  RH=78%
    10:42:19  N2    device     0   -91   +4.0  bat=87% 4.02V chutil=2.1% airtx=0.31%
    10:42:31  N1    pos       1*  -104   -7.5  -27.16836,-109.43802  alt=80m
    10:43:02  N4    text       0   -79   +9.0  "test 012/050"
    10:43:09  N3    private    0   -82   +6.5  14 B

What you read first must be what you need first in the field: local time (to
correlate with the notebook), the node REF not its id (!0b64122b is
unreadable while walking), kind, hops — a non-zero where zero was expected
means the path changed, more urgent than the payload — then the measurement,
column-aligned so a trend reads while moving, and the payload last.

Highlighted: hops > 0, and SNR below the preset's demodulation floor. Without
colour (not a TTY, or NO_COLOR) the highlight survives as a marker: `*` after
the hop count, `!` after the SNR.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from typing import TextIO

from channel_study.gaps import GapEvent, short
from channel_study.records import Reception
from channel_study.sink import jsonable

SHOWN_KINDS = ("device", "environment", "position", "text", "private")

_BOLD_YELLOW, _RED, _DIM, _RESET = "\033[1;33m", "\033[31m", "\033[2m", "\033[0m"


def _num(v, spec: str) -> str:
    return "?" if v is None else format(v, spec)


def payload_text(rx: Reception) -> str:
    d = rx.decoded
    if d.kind == "environment" and d.environment is not None:
        e = d.environment
        return f"T={_num(e.temperature, '.1f')}C  RH={_num(e.relative_humidity, '.0f')}%"
    if d.kind == "device" and d.device is not None:
        m = d.device
        return (f"bat={_num(m.battery_level, '')}% {_num(m.voltage, '.2f')}V "
                f"chutil={_num(m.channel_utilization, '.1f')}% airtx={_num(m.air_util_tx, '.2f')}%")
    if d.kind == "position" and d.position is not None:
        p = d.position
        if p.latitude is None or p.longitude is None:
            return "(no fix)"
        return f"{p.latitude:.5f},{p.longitude:.5f}  alt={_num(p.altitude, '')}m"
    if d.kind == "text" and d.text is not None:
        return f'"{d.text.text}"' if d.text.text is not None else f"<{d.payload_len} B, not UTF-8>"
    if d.kind == "private":
        return f"{_num(d.payload_len, '')} B"
    return f"{d.portnum or d.kind}"


class TerminalSink:
    HEADER = f"{'HH:MM:SS':<8}  {'ref':<5} {'kind':<7} {'hops':>4} {'RSSI':>5} {'SNR':>6}  payload"

    def __init__(self, stream: TextIO | None = None, *, snr_floor: float,
                 color: bool | None = None, raw: bool = False):
        self.stream = stream or sys.stdout
        if color is None:
            color = self.stream.isatty() and "NO_COLOR" not in os.environ
        self.color = color
        self.snr_floor = snr_floor
        self.raw = raw
        self._header_done = False

    def _w(self, line: str) -> None:
        self.stream.write(line + "\n")
        self.stream.flush()

    def header(self) -> None:
        if not self._header_done:
            self._w(self.HEADER)
            self._w("─" * 72)
            self._header_done = True

    def line(self, rx: Reception) -> str:
        d = rx.decoded
        t = _dt.datetime.fromtimestamp(rx.received_at).strftime("%H:%M:%S")
        ref = rx.ref if len(rx.ref) <= 5 else "?" + rx.ref[-4:]
        hops = d.hops_taken
        relayed = hops is not None and hops > 0
        hop_s = "?" if hops is None else f"{hops}{'*' if relayed and not self.color else ''}"
        low = d.rx_snr is not None and d.rx_snr < self.snr_floor
        snr_s = "?" if d.rx_snr is None else f"{d.rx_snr:+.1f}{'!' if low and not self.color else ''}"
        rssi_s = "?" if d.rx_rssi is None else f"{d.rx_rssi}"
        hop_col, snr_col = f"{hop_s:>4}", f"{snr_s:>6}"
        if self.color:
            if relayed:
                hop_col = f"{_BOLD_YELLOW}{hop_col}{_RESET}"
            if low:
                snr_col = f"{_RED}{snr_col}{_RESET}"
        payload = payload_text(rx)
        if rx.duplicate:
            payload = "(dup) " + payload
        if rx.own:
            payload = "(own) " + payload
        text = f"{t:<8}  {ref:<5} {short(d.kind):<7} {hop_col} {rssi_s:>5} {snr_col}  {payload}"
        if rx.duplicate and self.color:
            text = f"{_DIM}{text}{_RESET}"
        return text

    def emit(self, rx: Reception) -> None:
        if rx.kind not in SHOWN_KINDS and not self.raw:
            return
        self.header()
        self._w(self.line(rx))
        if self.raw:
            self._w(json.dumps(jsonable(rx.decoded.raw, capture_content=rx.capture_content),
                               sort_keys=True))

    def note(self, event: GapEvent) -> None:
        self.header()
        self._w(event.text())

    def message(self, text: str) -> None:
        self._w(text)

    def close(self) -> None:
        self.stream.flush()
