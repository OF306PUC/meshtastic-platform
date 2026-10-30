"""Deployment YAML -> Registry, strictly.

Strict on purpose: an unknown key is an error, not ignored, because a typo in a
registry ("intervalls", "gain_dB") silently becomes "this node has no cadence"
or "this antenna has no gain" — and every downstream number is then wrong
without anything failing. Structural problems are collected and raised
together, so one run reports every one of them.

There is deliberately no default deployment: data analysed against another
mesh's registry is silently wrong, so every tool takes --deployment (or
MESH_DEPLOYMENT) and refuses to guess.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import yaml

from meshtastic_platform.decode import FLOW_KINDS
from meshtastic_platform.radio.profile import Channel, RadioSpec
from meshtastic_platform.radio.regulatory import Band
from meshtastic_platform.registry.model import (
    TX_POWER_POLICIES, Antenna, Meta, Node, Pbx, Position, Registry, Sensor, Site,
)

ENV_DEPLOYMENT = "MESH_DEPLOYMENT"
ENV_DEPLOYMENTS_DIR = "MESH_DEPLOYMENTS_DIR"
_REPO_ROOT = Path(__file__).resolve().parents[2]


class RegistryError(ValueError):
    """A registry that cannot be loaded or must not be used."""

    def __init__(self, message: str, problems: list[str] | None = None):
        self.problems = problems or []
        detail = "".join(f"\n  - {p}" for p in self.problems)
        super().__init__(message + detail)


# ── Locating a deployment ─────────────────────────────────────────────────────

def deployments_dir() -> Path:
    env = os.environ.get(ENV_DEPLOYMENTS_DIR)
    if env:
        return Path(env)
    repo = _REPO_ROOT / "deployments"
    return repo if repo.is_dir() else Path.cwd() / "deployments"


def available() -> list[str]:
    d = deployments_dir()
    # Files starting with "_" (the template) are not deployments.
    return sorted(p.stem for p in d.glob("*.yaml") if not p.stem.startswith("_")) if d.is_dir() else []


def resolve(name_or_path: str | None) -> Path:
    """--deployment value (a name or a path) -> file. Never a default."""
    value = name_or_path or os.environ.get(ENV_DEPLOYMENT)
    if not value:
        raise RegistryError(
            f"no deployment selected: pass --deployment <name> or set {ENV_DEPLOYMENT}. "
            f"There is deliberately no default — data analysed against the wrong "
            f"registry yields silently false PDR. Available: {available() or 'none found'}")
    path = Path(value)
    if path.suffix in (".yaml", ".yml") or os.sep in value:
        if not path.is_file():
            raise RegistryError(f"deployment file not found: {path}")
        return path
    candidate = deployments_dir() / f"{value}.yaml"
    if not candidate.is_file():
        raise RegistryError(f"unknown deployment {value!r} in {deployments_dir()} "
                            f"(available: {available() or 'none'})")
    return candidate


# ── Schema helpers ────────────────────────────────────────────────────────────

class _Reader:
    """Pulls typed fields out of a mapping and records every problem."""

    def __init__(self, problems: list[str]):
        self.problems = problems

    def mapping(self, value, where: str, allowed: set[str], required: set[str] = frozenset()):
        if not isinstance(value, dict):
            self.problems.append(f"{where}: expected a mapping, got {type(value).__name__}")
            return None
        unknown = set(value) - allowed
        if unknown:
            self.problems.append(f"{where}: unknown key(s) {sorted(unknown)} "
                                 f"(allowed: {sorted(allowed)})")
        for key in sorted(required - set(value)):
            self.problems.append(f"{where}: missing required key '{key}'")
        return value

    def get(self, d: dict, key: str, where: str, types, *, nullable=True, hint: str = ""):
        if d is None or key not in d:
            return None
        v = d[key]
        if v is None:
            if not nullable:
                self.problems.append(f"{where}.{key}: may not be null")
            return None
        ok = isinstance(v, types) and not (isinstance(v, bool) and bool not in _as_tuple(types))
        if not ok:
            names = "/".join(t.__name__ for t in _as_tuple(types))
            self.problems.append(f"{where}.{key}: expected {names}, got {v!r}"
                                 + (f" — {hint}" if hint else ""))
            return None
        return v


def _as_tuple(types):
    return types if isinstance(types, tuple) else (types,)


_NUM = (int, float)


def _position(r: _Reader, raw, where) -> Position | None:
    if raw is None:
        return None
    # A template block with every field still null is "not filled in yet", the
    # same as no block; a half-filled one (lat without lon) is an error below.
    if isinstance(raw, dict) and raw and all(v is None for v in raw.values()):
        r.mapping(raw, where, {"lat", "lon", "alt_m", "alt_source"})
        return None
    d = r.mapping(raw, where, {"lat", "lon", "alt_m", "alt_source"}, {"lat", "lon"})
    if d is None:
        return None
    lat = r.get(d, "lat", where, _NUM, nullable=False)
    lon = r.get(d, "lon", where, _NUM, nullable=False)
    for key, val, limit in (("lat", lat, 90.0), ("lon", lon, 180.0)):
        if val is None:
            continue
        if not -limit <= val <= limit:
            r.problems.append(f"{where}.{key}: out of range: {val!r}")
        elif val == 0:
            r.problems.append(f"{where}.{key}: is 0 — looks unset, not surveyed")
    if lat is None or lon is None:
        return None
    alt = r.get(d, "alt_m", where, _NUM)
    return Position(float(lat), float(lon), float(alt) if alt is not None else None,
                    r.get(d, "alt_source", where, str))


def _antenna(r: _Reader, raw, where) -> Antenna | None:
    if raw is None:
        return None
    d = r.mapping(raw, where, {"type", "gain_dbi", "band_mhz", "model", "connector_loss_db"},
                  {"type", "gain_dbi"})
    if d is None:
        return None
    band = d.get("band_mhz")
    if band is not None:
        if (not isinstance(band, list) or len(band) != 2
                or not all(isinstance(x, _NUM) and not isinstance(x, bool) for x in band)
                or band[0] >= band[1]):
            r.problems.append(f"{where}.band_mhz: expected [low, high] in MHz, got {band!r}")
            band = None
        else:
            band = (float(band[0]), float(band[1]))
    atype = r.get(d, "type", where, str, nullable=False)
    gain = r.get(d, "gain_dbi", where, _NUM, nullable=False)
    if atype is None or gain is None:
        return None
    model = r.get(d, "model", where, str)
    loss = r.get(d, "connector_loss_db", where, _NUM)
    return Antenna(atype, float(gain), band, model or None,
                   float(loss) if loss is not None else None)


def _sensors(r: _Reader, raw, where) -> tuple[Sensor, ...]:
    if not isinstance(raw, list):
        r.problems.append(f"{where}: expected a list (use [] for a node with no sensor)")
        return ()
    out = []
    for i, item in enumerate(raw):
        w = f"{where}[{i}]"
        d = r.mapping(item, w, {"type", "i2c_addr", "port"}, {"type"})
        if d is None:
            continue
        addr = d.get("i2c_addr")
        if isinstance(addr, int) and not isinstance(addr, bool):
            addr = f"0x{addr:02x}"         # YAML read an unquoted 0x44 as 68
        elif addr is not None and not isinstance(addr, str):
            r.problems.append(f"{w}.i2c_addr: expected a string like \"0x44\", got {addr!r}")
            addr = None
        stype = r.get(d, "type", w, str, nullable=False)
        if stype is not None:
            out.append(Sensor(stype, addr, r.get(d, "port", w, str)))
    return tuple(out)


def _pbx(r: _Reader, raw, where) -> Pbx | None:
    if raw is None:
        return None
    d = r.mapping(raw, where, {"mcu", "firmware"}, {"mcu"})
    if d is None:
        return None
    mcu = r.get(d, "mcu", where, str, nullable=False)
    if mcu is None:
        return None
    return Pbx(mcu, firmware=r.get(d, "firmware", where, str,
                                   hint="quote versions, or YAML reads \"1.1\" as a float"))


def _intervals(r: _Reader, raw, where) -> dict[str, int]:
    if not isinstance(raw, dict):
        r.problems.append(f"{where}: expected a mapping of flow -> seconds "
                          f"(use {{}} for a node that broadcasts no measured flow)")
        return {}
    out = {}
    for kind, secs in raw.items():
        if kind not in FLOW_KINDS:
            r.problems.append(f"{where}: unknown flow kind {kind!r} (expected one of {FLOW_KINDS})")
            continue
        if secs is None or secs == 0:
            r.problems.append(
                f"{where}.{kind}: is {secs!r}. A flow the node does not emit must be "
                f"ABSENT, not null or 0 — absence is the only signal the estimators read")
            continue
        if not isinstance(secs, int) or isinstance(secs, bool) or secs < 0:
            r.problems.append(f"{where}.{kind}: must be a positive int (seconds), got {secs!r}")
            continue
        out[kind] = secs
    return out


_NODE_KEYS = {"ref", "label", "function", "status", "node_id", "mac", "hardware", "mcu",
              "firmware", "role", "hop_limit", "antenna", "tx_power_dbm", "site",
              "intervals", "sensors", "pbx", "notes"}
_NODE_REQUIRED = {"ref", "function", "status", "role", "hop_limit", "intervals", "sensors"}
_QUOTE_HINT = "quote it in the YAML"


def _node(r: _Reader, raw, where) -> Node | None:
    d = r.mapping(raw, where, _NODE_KEYS, _NODE_REQUIRED)
    if d is None:
        return None
    ref = r.get(d, "ref", where, str, nullable=False)
    if ref is None:
        return None
    where = f"nodes[{ref}]"

    site = None
    if d.get("site") is not None:
        sd = r.mapping(d["site"], f"{where}.site",
                       {"name", "asset_code", "asset_type", "surveyed", "planned",
                        "antenna_height_m", "planned_antenna_height_m", "mount"})
        if sd is not None:
            site = Site(
                name=r.get(sd, "name", f"{where}.site", str),
                asset_code=r.get(sd, "asset_code", f"{where}.site", str),
                asset_type=r.get(sd, "asset_type", f"{where}.site", str),
                surveyed=_position(r, sd.get("surveyed"), f"{where}.site.surveyed"),
                planned=_position(r, sd.get("planned"), f"{where}.site.planned"),
                antenna_height_m=r.get(sd, "antenna_height_m", f"{where}.site", _NUM),
                planned_antenna_height_m=r.get(sd, "planned_antenna_height_m", f"{where}.site", _NUM),
                mount=r.get(sd, "mount", f"{where}.site", str),
            )

    hop = r.get(d, "hop_limit", where, int, nullable=False)
    tx = r.get(d, "tx_power_dbm", where, int, hint="integer dBm")
    return Node(
        ref=ref,
        label=r.get(d, "label", where, str),
        function=r.get(d, "function", where, str, nullable=False) or "",
        status=r.get(d, "status", where, str, nullable=False) or "",
        node_id=r.get(d, "node_id", where, str,
                      hint="'!' starts a YAML tag, so a node id must be quoted"),
        mac=r.get(d, "mac", where, str, hint=_QUOTE_HINT),
        hardware=r.get(d, "hardware", where, str),
        mcu=r.get(d, "mcu", where, str),
        firmware=r.get(d, "firmware", where, str,
                       hint="quote versions, or YAML reads \"2.7\" as a float"),
        role=r.get(d, "role", where, str, nullable=False) or "",
        hop_limit=hop if hop is not None else -1,
        intervals=_intervals(r, d.get("intervals"), f"{where}.intervals"),
        sensors=_sensors(r, d.get("sensors"), f"{where}.sensors"),
        antenna=_antenna(r, d.get("antenna"), f"{where}.antenna"),
        tx_power_dbm=tx,
        site=site,
        pbx=_pbx(r, d.get("pbx"), f"{where}.pbx"),
        notes=r.get(d, "notes", where, str),
    )


_META_KEYS = {"deployment", "kind", "description", "firmware_target", "cadence_scale"}
_META_REQUIRED = {"deployment", "kind"}
_RADIO_KEYS = {"region", "modem_preset", "channel_num", "channels", "rebroadcast_mode",
               "position_precision", "rx_boosted_gain", "eirp_caps", "tx_power_policy"}
_RADIO_REQUIRED = {"region", "modem_preset", "channels", "rebroadcast_mode",
                   "position_precision", "rx_boosted_gain"}


def _band_pair(r: _Reader, value, where):
    if (not isinstance(value, list) or len(value) != 2
            or not all(isinstance(x, _NUM) and not isinstance(x, bool) for x in value)
            or value[0] >= value[1]):
        r.problems.append(f"{where}: expected [low, high] in MHz, got {value!r}")
        return None
    return float(value[0]), float(value[1])


def _radio(r: _Reader, raw) -> RadioSpec | None:
    d = r.mapping(raw, "radio", _RADIO_KEYS, _RADIO_REQUIRED)
    if d is None:
        return None
    channels = []
    raw_ch = d.get("channels")
    if not isinstance(raw_ch, list) or not raw_ch:
        r.problems.append("radio.channels: expected a non-empty list (the first is the primary)")
    else:
        for i, item in enumerate(raw_ch):
            w = f"radio.channels[{i}]"
            c = r.mapping(item, w, {"index", "name", "psk_env"}, {"index", "name", "psk_env"})
            if c is None:
                continue
            idx = r.get(c, "index", w, int, nullable=False)
            name = r.get(c, "name", w, str, nullable=False)
            env = r.get(c, "psk_env", w, str, nullable=False)
            if None not in (idx, name, env):
                channels.append(Channel(idx, name, env))
    caps = None
    if "eirp_caps" in d:
        caps = []
        raw_caps = d.get("eirp_caps")
        if not isinstance(raw_caps, list):
            r.problems.append("radio.eirp_caps: expected a list (use [] when no cap applies)")
        else:
            for i, item in enumerate(raw_caps):
                w = f"radio.eirp_caps[{i}]"
                c = r.mapping(item, w, {"band_mhz", "eirp_dbm", "label"}, {"band_mhz", "eirp_dbm"})
                if c is None:
                    continue
                band = _band_pair(r, c.get("band_mhz"), f"{w}.band_mhz")
                eirp = r.get(c, "eirp_dbm", w, _NUM, nullable=False)
                if band is not None and eirp is not None:
                    caps.append(Band(band[0], band[1], float(eirp),
                                     r.get(c, "label", w, str) or ""))
    precision = r.get(d, "position_precision", "radio", int, nullable=False)
    boosted = r.get(d, "rx_boosted_gain", "radio", bool, nullable=False)
    policy = r.get(d, "tx_power_policy", "radio", str) or "derived"
    if policy not in TX_POWER_POLICIES:
        r.problems.append(f"radio.tx_power_policy: {policy!r} is not one of "
                          f"{sorted(TX_POWER_POLICIES)}")
        policy = "derived"
    return RadioSpec(
        region=r.get(d, "region", "radio", str, nullable=False) or "",
        modem_preset=r.get(d, "modem_preset", "radio", str, nullable=False) or "",
        channel_num=r.get(d, "channel_num", "radio", int),
        channels=tuple(channels),
        rebroadcast_mode=r.get(d, "rebroadcast_mode", "radio", str, nullable=False) or "",
        position_precision=precision if precision is not None else 0,
        rx_boosted_gain=bool(boosted),
        eirp_caps=tuple(caps) if caps is not None else None,
        tx_power_policy=policy,
    )


def parse(data: Any, *, path: Path | None = None, sha256: str | None = None) -> Registry:
    """Already-parsed YAML -> Registry. Raises RegistryError listing every problem."""
    problems: list[str] = []
    r = _Reader(problems)
    top = r.mapping(data, "<top>", {"meta", "radio", "nodes"}, {"meta", "radio", "nodes"})
    if top is None:
        raise RegistryError(f"invalid registry {path or ''}", problems)

    md = r.mapping(top.get("meta"), "meta", _META_KEYS, _META_REQUIRED) or {}
    scale = r.get(md, "cadence_scale", "meta", int)
    meta = Meta(
        deployment=r.get(md, "deployment", "meta", str, nullable=False) or "",
        kind=r.get(md, "kind", "meta", str, nullable=False) or "",
        firmware_target=r.get(md, "firmware_target", "meta", str,
                              hint="quote versions, or YAML reads \"2.7\" as a float"),
        cadence_scale=scale if scale is not None else 1,
        description=r.get(md, "description", "meta", str),
    )
    radio = _radio(r, top.get("radio"))

    raw_nodes = top.get("nodes")
    nodes = []
    if not isinstance(raw_nodes, list) or not raw_nodes:
        problems.append("nodes: expected a non-empty list")
    else:
        for i, raw in enumerate(raw_nodes):
            n = _node(r, raw, f"nodes[{i}]")
            if n is not None:
                nodes.append(n)

    if problems or radio is None:
        raise RegistryError(f"invalid registry {path or ''}".strip(), problems)
    return Registry(meta=meta, radio_spec=radio, nodes=tuple(nodes), path=path, sha256=sha256)


def load(path: str | Path) -> Registry:
    """Read and parse one deployment file (structure only; see validate)."""
    path = Path(path)
    blob = path.read_bytes()
    try:
        data = yaml.safe_load(blob)
    except yaml.YAMLError as exc:
        hint = ""
        if "could not determine a constructor for the tag '!" in str(exc):
            hint = " — a node id starts with '!', which YAML reads as a tag: quote it"
        raise RegistryError(f"{path}: not valid YAML{hint}", [str(exc)]) from None
    return parse(data, path=path, sha256=hashlib.sha256(blob).hexdigest())
