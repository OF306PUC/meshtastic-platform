"""The registry as a spreadsheet: one row per node, generated, never read back.

A deployment file is the only place a mesh is declared (rule 1), but it is not
what a person carries to a site. Labelling physical units, checking which
antenna came out of which box and writing down what was measured all happen on
a table, and a table is what a spreadsheet is for.

So this exports, and only exports. Nothing here parses a sheet back into a
deployment: a sheet that could be edited back would be a second place the mesh
is declared, and when the two disagreed nothing would say which one won. What
gets decided on site is copied into the YAML by hand, once, in one direction.

Rows are split by MCU family, because that is the axis along which the columns
stop meaning the same thing — `mac` is an eFuse WiFi address on an ESP32 and an
immutable BLE static address on an nRF52840 — and because V8 already warns that
the two families are never compared without grouping by `mcu`.

An EMPTY cadence cell means the node does not emit that flow at all. That is the
deployment file's own distinction (V3b: absent, never null, never 0) and the
export keeps it, because a 0 in a spreadsheet reads as "every zero seconds".
Every other empty cell is something not recorded yet: together they are the
to-fill list, which is the whole point of taking the sheet to the site.
"""
from __future__ import annotations

import csv
from pathlib import Path

from meshtastic_platform.registry.model import Node, Registry

# Columns before the cadences: who the unit is, then what it transmits with.
IDENTITY_COLUMNS = ["deployment", "ref", "function", "status",
                    "hardware", "mcu", "chip", "node_id", "mac", "firmware"]
RADIO_COLUMNS = ["role", "hop_limit", "tx_power_dbm", "tx_power_expected_dbm", "eirp_dbm",
                 "antenna_type", "antenna_gain_dbi", "antenna_model", "antenna_band_mhz",
                 "connector_loss_db", "sensors"]
# Columns after the cadences: filled on site, then copied back into the YAML.
SITE_COLUMNS = ["site_name", "asset_code", "asset_type", "surveyed_lat", "surveyed_lon", "surveyed_alt_m",
                "surveyed_alt_source", "antenna_height_m", "mount",
                "planned_lat", "planned_lon", "planned_alt_m", "notes"]
PBX_COLUMNS = ["pbx_mcu", "pbx_firmware"]

CADENCE_PREFIX = "cadence_"
CADENCE_SUFFIX = "_s"


def flows(reg: Registry) -> list[str]:
    """Every cadence any node in the deployment declares, in a stable order.

    Read from the data rather than listed here: a flow this code did not know
    about would otherwise be dropped from the sheet without a word.
    """
    seen: dict[str, None] = {}
    for n in reg.nodes:
        seen.update(dict.fromkeys(reg.intervals(n)))
    return sorted(seen)


def columns(reg: Registry, nodes: list[Node]) -> list[str]:
    """The header for a sheet.

    A column only appears where it can hold something. `label` is left out
    entirely when no node has one — a deployment whose refs ARE the labels
    painted on the cases would otherwise show an empty column, and on a sheet
    whose empty cells mean "still to fill" that reads as a missing answer
    rather than as a question nobody asked. Same for the PBX pair.
    """
    head = list(IDENTITY_COLUMNS)
    if any(n.label for n in nodes):
        head.insert(head.index("ref") + 1, "label")
    cadence = [f"{CADENCE_PREFIX}{f}{CADENCE_SUFFIX}" for f in flows(reg)]
    pbx = PBX_COLUMNS if any(n.pbx is not None for n in nodes) else []
    return head + RADIO_COLUMNS + cadence + pbx + SITE_COLUMNS


def row(reg: Registry, node: Node) -> dict[str, object]:
    """One node, flattened. Absent values stay absent: None, never 0, never '-'."""
    a, s, p = node.antenna, node.site, node.pbx
    surveyed = s.surveyed if s else None
    planned = s.planned if s else None
    eirp = (node.tx_power_dbm + a.gain_dbi) if a and node.tx_power_dbm is not None else None
    r: dict[str, object] = {
        "deployment": reg.name, "ref": node.ref, "label": node.label,
        "function": node.function, "status": node.status,
        "hardware": node.hardware, "mcu": node.mcu, "chip": node.chip.name,
        "node_id": node.node_id, "mac": node.mac, "firmware": node.firmware,
        "role": node.role, "hop_limit": node.hop_limit,
        "tx_power_dbm": node.tx_power_dbm,
        "tx_power_expected_dbm": reg.expected_tx_power(node),
        "eirp_dbm": eirp,
        "antenna_type": a.type if a else None,
        "antenna_gain_dbi": a.gain_dbi if a else None,
        "antenna_model": a.model if a else None,
        "antenna_band_mhz": f"{a.band_mhz[0]:g}-{a.band_mhz[1]:g}" if a and a.band_mhz else None,
        "connector_loss_db": a.connector_loss_db if a else None,
        "sensors": "+".join(sensor.type for sensor in node.sensors) or None,
        "pbx_mcu": p.mcu if p else None,
        "pbx_firmware": p.firmware if p else None,
        "site_name": s.name if s else None,
        "asset_code": s.asset_code if s else None,
        "asset_type": s.asset_type if s else None,
        "surveyed_lat": surveyed.lat if surveyed else None,
        "surveyed_lon": surveyed.lon if surveyed else None,
        "surveyed_alt_m": surveyed.alt_m if surveyed else None,
        "surveyed_alt_source": surveyed.alt_source if surveyed else None,
        "antenna_height_m": s.antenna_height_m if s else None,
        "mount": s.mount if s else None,
        "planned_lat": planned.lat if planned else None,
        "planned_lon": planned.lon if planned else None,
        "planned_alt_m": planned.alt_m if planned else None,
        "notes": node.notes,
    }
    # A flow the node does not emit has no key at all, so its cell stays empty.
    for flow, secs in reg.intervals(node).items():
        r[f"{CADENCE_PREFIX}{flow}{CADENCE_SUFFIX}"] = secs
    return r


def sheets(reg: Registry) -> dict[str, tuple[list[str], list[dict]]]:
    """{mcu family: (header, rows)}. A node with no recorded MCU gets its own."""
    grouped: dict[str, list[Node]] = {}
    for n in reg.nodes:
        grouped.setdefault(n.mcu or "unrecorded", []).append(n)
    return {mcu: (columns(reg, nodes), [row(reg, n) for n in nodes])
            for mcu, nodes in sorted(grouped.items())}


def write_csv(reg: Registry, out_dir: str | Path) -> list[Path]:
    """Write one sheet per MCU family into out_dir. Returns the files written."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for mcu, (header, rows) in sheets(reg).items():
        path = directory / f"{reg.name}-{mcu}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow({k: ("" if r.get(k) is None else r[k]) for k in header})
        written.append(path)
    return written
