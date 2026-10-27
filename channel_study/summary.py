"""Per-node session summary, printed on Ctrl+C and stored in session.json.

RSSI and SNR describe the LAST hop, not the originating node's link: for a
relayed packet the measurement is relay -> receiver, and the relay changes from
packet to packet. So the level percentiles are computed on DIRECT (hops == 0)
receptions only, and relayed ones show up in the hop distribution instead.
Mixing them reports the spread between relays as if it were fading.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile (numpy's default), q in [0, 100]."""
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q / 100
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


@dataclass
class _NodeStats:
    receptions: int = 0
    duplicates: int = 0
    rssi_direct: list = field(default_factory=list)
    snr_direct: list = field(default_factory=list)
    hops: Counter = field(default_factory=Counter)
    kinds: Counter = field(default_factory=Counter)


class Summary:
    def __init__(self):
        self._nodes: dict[str, _NodeStats] = defaultdict(_NodeStats)

    def add(self, ref: str, kind: str, hops, rssi, snr, duplicate: bool) -> None:
        s = self._nodes[ref]
        if duplicate:
            s.duplicates += 1
            return
        s.receptions += 1
        s.kinds[kind] += 1
        s.hops["?" if hops is None else hops] += 1
        if hops == 0:
            if rssi is not None:
                s.rssi_direct.append(rssi)
            if snr is not None:
                s.snr_direct.append(snr)

    def rows(self, gaps: Counter) -> list[dict]:
        out = []
        refs = sorted(set(self._nodes) | {ref for ref, _ in gaps})
        for ref in refs:
            s = self._nodes.get(ref, _NodeStats())
            out.append({
                "ref": ref,
                "receptions": s.receptions,
                "duplicates": s.duplicates,
                "kinds": dict(s.kinds),
                "rssi_p05": percentile(s.rssi_direct, 5),
                "rssi_p50": percentile(s.rssi_direct, 50),
                "rssi_p95": percentile(s.rssi_direct, 95),
                "snr_p05": percentile(s.snr_direct, 5),
                "direct": len(s.rssi_direct),
                "gaps": sum(n for (r, _), n in gaps.items() if r == ref),
                "hops": {str(k): v for k, v in sorted(s.hops.items(), key=lambda kv: str(kv[0]))},
            })
        return out

    @staticmethod
    def render(rows: list[dict]) -> list[str]:
        def f(v, spec="+.1f"):
            return "-" if v is None else format(v, spec)

        lines = [f"{'ref':<6}{'rx':>6}{'dup':>5}  {'RSSI p05/p50/p95 (direct)':<26}"
                 f"{'SNR p05':>8}{'gaps':>6}  hops"]
        for r in rows:
            levels = f"{f(r['rssi_p05'], '.0f')}/{f(r['rssi_p50'], '.0f')}/{f(r['rssi_p95'], '.0f')}"
            hops = " ".join(f"{k}:{v}" for k, v in r["hops"].items()) or "-"
            lines.append(f"{r['ref']:<6}{r['receptions']:>6}{r['duplicates']:>5}  {levels:<26}"
                         f"{f(r['snr_p05']):>8}{r['gaps']:>6}  {hops}")
        return lines
