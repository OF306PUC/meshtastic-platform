"""Session metadata: the lab equivalent of labelling the sample.

Every recorded session writes session.json alongside its data: run_id, UTC
start/end, operator, the deployment registry used (and its sha256), the
receiving radio's config, its firmware, `git describe` of this repo, and
free-form notes. Without it, two months later nobody knows which preset a
session was taken under, and the data is worth half as much.

It is written when recording STARTS (a crashed session is still labelled) and
rewritten at the end with the end time, the decode counters and the summary.

Sessions from different deployments must never be pooled: bench RSSI does not
transfer to the field, and data analysed against the wrong registry yields
false PDR. load_sessions() refuses to mix them.
"""
from __future__ import annotations

import datetime as _dt
import json
import secrets
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import meshtastic_platform
from meshtastic_platform.registry import Registry

SESSION_FILE = "session.json"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def new_run_id(now_utc: _dt.datetime) -> str:
    return now_utc.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


def git_describe(repo: Path = _REPO_ROOT) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), "describe", "--always", "--dirty", "--tags"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unknown ({exc.__class__.__name__})"
    if out.returncode != 0:
        return f"unknown ({(out.stderr.strip().splitlines() or ['git failed'])[-1]})"
    return out.stdout.strip()


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class SessionMeta:
    run_id: str
    started_utc: str
    operator: str
    deployment: dict[str, Any]
    receiver: dict[str, Any]
    git: str
    notes: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    sinks: list[str] = field(default_factory=list)
    capture_content: bool = False
    platform_version: str = meshtastic_platform.__version__
    ended_utc: str | None = None
    decode_stats: dict[str, Any] | None = None
    track: dict[str, Any] | None = None
    summary: list[dict] | None = None
    gaps: list[dict] | None = None

    @staticmethod
    def deployment_block(reg: Registry) -> dict[str, Any]:
        return {
            "name": reg.name,
            "kind": reg.meta.kind,
            "path": str(reg.path) if reg.path else None,
            "sha256": reg.sha256,
            "region": reg.radio.region,
            "modem_preset": reg.radio.modem_preset,
            "channel_num": reg.radio.slot.channel_num,
            "channels": [c.name for c in reg.radio.channels],
            "slot_mhz": reg.radio.slot.center_mhz,
            "eirp_cap_dbm": reg.radio.eirp_cap_dbm,
            "cadence_scale": reg.meta.cadence_scale,
            "firmware_target": reg.meta.firmware_target,
        }

    def write(self, directory: str | Path) -> Path:
        path = Path(directory) / SESSION_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, sort_keys=False, default=str) + "\n")
        tmp.replace(path)
        return path


def load_session(directory: str | Path) -> dict[str, Any]:
    path = Path(directory) / SESSION_FILE
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found: unlabelled data, refusing to analyse it")
    return json.loads(path.read_text())


def load_sessions(directories: list[str | Path], *, allow_mixed: bool = False) -> list[dict]:
    """Load several sessions; refuse to mix deployments unless told to."""
    sessions = [load_session(d) for d in directories]
    names = {s["deployment"]["name"] for s in sessions}
    if len(names) > 1 and not allow_mixed:
        raise ValueError(f"sessions come from different deployments {sorted(names)}: "
                         f"bench and field data must not be pooled")
    presets = {s["deployment"]["modem_preset"] for s in sessions}
    if len(presets) > 1 and not allow_mixed:
        raise ValueError(f"sessions were taken under different presets {sorted(presets)}")
    return sessions
