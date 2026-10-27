"""receiver.py — channel-study receiver: one LILYGO over serial, a laptop, no infrastructure.

Logs what a radio hears to the terminal and, optionally, to CSV / JSONL with a
session.json beside the data. It is NOT the gateway: nothing here publishes or
persists anywhere else. Run it from a clone of this repository; nothing has to
be installed beyond requirements.txt:

    # Listen and display in the terminal
    python receiver.py --port /dev/ttyACM0 -d <deployment>

    # With CSV (and session.json beside it)
    python receiver.py --port /dev/ttyACM0 -d <deployment> --csv runs/<date>/ --operator <name>

    # One node only, environmental telemetry only
    python receiver.py --port /dev/ttyACM0 -d <deployment> --node <ref> --kind environment

    # Dump the full MeshPacket dict (debugging / new fields)
    python receiver.py --port /dev/ttyACM0 -d <deployment> --raw

<deployment> is a file in deployments/ without the .yaml, or a YAML path;
-d/--deployment may come from MESH_DEPLOYMENT; it is never defaulted. The
receiving radio must already be provisioned (python configure.py provision)
on the deployment's channel and preset — a receiver on another preset hears
nothing and reports nothing, so a mismatch is announced before listening.
Figures from a recorded session: python -m channel_study.analysis.plot_session <dir>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import time

from channel_study.listener import KINDS, ChannelStudyReceiver
from channel_study.session import SessionMeta, git_describe, iso, new_run_id
from channel_study.sink.terminal import TerminalSink
from channel_study.summary import Summary
from meshtastic_platform.registry import ENV_DEPLOYMENT, RegistryError, available, load_deployment


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python receiver.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True,
                    help="serial port of the receiving radio: COM3 on Windows, "
                         "/dev/serial/by-id/... on Linux (stable), /dev/cu.* on macOS")
    ap.add_argument("--deployment", "-d", default=None,
                    help=f"a file in deployments/ without .yaml, or a YAML path "
                         f"(or set {ENV_DEPLOYMENT}); never defaulted; "
                         f"available: {', '.join(available()) or 'none'}")
    ap.add_argument("--csv", metavar="DIR", help="write one CSV per (node, kind) into DIR")
    ap.add_argument("--jsonl", metavar="DIR", help="write every packet as JSON lines into DIR")
    ap.add_argument("--node", action="append", metavar="REF", help="only this node (repeatable)")
    ap.add_argument("--kind", action="append", choices=KINDS, help="only this kind (repeatable)")
    ap.add_argument("--raw", action="store_true", help="also print the full MeshPacket dict")
    ap.add_argument("--operator", default=os.environ.get("MESH_OPERATOR"),
                    help="who is recording (or MESH_OPERATOR); required with --csv/--jsonl")
    ap.add_argument("--notes", default="", help="free-form notes stored in session.json")
    ap.add_argument("--capture-content", action="store_true",
                    help="record message bodies (off by default: they may be real phone traffic)")
    ap.add_argument("--no-color", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        reg = load_deployment(args.deployment)
    except RegistryError as exc:
        print(f"ERROR: {exc}")
        return 2
    for ref in args.node or []:
        try:
            reg.by_ref(ref)
        except KeyError as exc:
            print(f"ERROR: {exc.args[0]}")
            return 2
    data_dirs = [d for d in (args.csv, args.jsonl) if d]
    if data_dirs and not args.operator:
        print("ERROR: --operator is required when recording: session.json must say who took "
              "the data (or set MESH_OPERATOR).")
        return 2

    import meshtastic.serial_interface
    from pubsub import pub
    from channel_study.sink.csv import CsvSink
    from channel_study.sink.jsonl import JsonlSink
    from meshtastic_platform.provision import inspector

    try:
        iface = meshtastic.serial_interface.SerialInterface(devPath=args.port)
    except Exception as exc:
        print(f"ERROR: could not open {args.port}: {exc}")
        return 2
    snap = inspector.snapshot(iface)
    me = snap.identity
    rx_node = reg.by_node_id(me.node_id) if me.node_id else None

    term = TerminalSink(snr_floor=reg.radio.snr_floor_db,
                        color=False if args.no_color else None, raw=args.raw)
    term.message(f"[RX] {reg.name}: {reg.radio.describe()}")
    term.message(f"[RX] receiving radio {me.node_id} ({me.hw_model}, fw {me.firmware}) = "
                 f"{rx_node.ref if rx_node else 'NOT IN THE REGISTRY'}")
    if rx_node is None:
        term.message(f"[RX] WARNING: this radio is not in {reg.name}; rx_* fields will be empty. "
                     f"Register it (its antenna and firmware are part of every measurement).")
    for c in inspector.check_radio(snap, reg, psks=None):
        if not c.ok:
            term.message(f"[RX] WARNING: receiver {c.label} is {c.actual}, deployment expects "
                         f"{c.expected} — it may hear nothing from this mesh")

    start = time.time()
    run_id = new_run_id(_dt.datetime.now(_dt.timezone.utc))
    sinks: list = [term]
    if args.csv:
        sinks.append(CsvSink(args.csv, run_id=run_id, clock=time.time))
    if args.jsonl:
        sinks.append(JsonlSink(args.jsonl, run_id=run_id, clock=time.time))
    meta = SessionMeta(
        run_id=run_id, started_utc=iso(start), operator=args.operator or "",
        deployment=SessionMeta.deployment_block(reg),
        receiver={"port": args.port, "node_id": me.node_id, "ref": rx_node.ref if rx_node else None,
                  "registered": rx_node is not None, "hw_model": me.hw_model,
                  "firmware": me.firmware, "mac": me.mac, "config": snap.config,
                  "channels": [{k: v for k, v in ch.items() if k != "psk"} for ch in snap.channels]},
        git=git_describe(), notes=args.notes,
        filters={"node": args.node, "kind": args.kind},
        sinks=[type(s).__name__ for s in sinks], capture_content=args.capture_content)
    for d in dict.fromkeys(data_dirs):
        meta.write(d)

    rx = ChannelStudyReceiver(reg, sinks, run_id=run_id, my_id=me.node_id, my_num=me.node_num,
                              rx_node=rx_node, nodes=set(args.node or []),
                              kinds=set(args.kind or []), capture_content=args.capture_content)
    term.message(f"[RX] run {run_id}: expecting {len(rx.gaps.flows)} flows; gaps announced at "
                 f"1.5x cadence. Ctrl+C to stop.\n")
    pub.subscribe(rx.pubsub_listener, "meshtastic.receive")
    try:
        while True:
            time.sleep(1)
            rx.tick()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pub.unsubscribe(rx.pubsub_listener, "meshtastic.receive")
        except Exception:
            pass
        iface.close()
        rows = rx.summary_rows()
        term.message(f"\n── Session summary · run {run_id} · "
                     f"{_dt.timedelta(seconds=int(time.time() - start))} ──")
        for line in Summary.render(rows):
            term.message(line)
        for line in rx.counters_lines():
            term.message(line)
        meta.ended_utc = iso(time.time())
        meta.decode_stats = {**rx.stats.as_dict(), "processing_errors": rx.errors}
        meta.summary = rows
        meta.gaps = [{"ref": r, "kind": k, "count": n} for (r, k), n in rx.gaps.gaps.items()]
        for d in dict.fromkeys(data_dirs):
            meta.write(d)
            term.message(f"[RX] session written to {d}")
        rx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
