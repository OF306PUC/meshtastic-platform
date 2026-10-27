"""configure.py — configure and verify the mesh's radios.

Run it from a clone of this repository; nothing has to be installed beyond
requirements.txt:

    python configure.py validate  -d <deployment>              # check the registry (V1–V8 ...)
    python configure.py validate  --all                    # every deployment (what CI runs)
    python configure.py show      -d <deployment>              # nodes, derived tx_power, EIRP, slot
    python configure.py provision -d <deployment> --node <ref> --port /dev/serial/by-id/... --dry-run
    python configure.py provision -d <deployment> --node <ref> --port /dev/serial/by-id/...
    python configure.py inspect   -d <deployment> --port /dev/serial/by-id/... [--node <ref>]

<deployment> is a file in deployments/ without the .yaml (-d my-mesh reads
deployments/my-mesh.yaml), or a path to a YAML file. -d/--deployment may be
replaced by the MESH_DEPLOYMENT variable. It is never defaulted: a registry
applied to the wrong mesh fails silently.

`provision` writes everything from the node's registry entry (role, hop limit,
slot, derived tx_power, cadences, sensors, channels) and refuses a device that
is not the one the entry describes. `inspect` reads a live radio back and exits
1 on any drift — the deployment's smoke test. Flashing comes first:
docs/flashing.md.
"""
from __future__ import annotations

import argparse
import sys

from meshtastic_platform import registry
from meshtastic_platform.registry import RegistryError


def _deployment_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--deployment", "-d", default=None,
                   help=f"a file in deployments/ without .yaml, or a YAML path "
                        f"(or set {registry.ENV_DEPLOYMENT}); "
                        f"available: {', '.join(registry.available()) or 'none'}")


def cmd_validate(args) -> int:
    if args.all:
        targets = registry.available()
        if not targets:
            print(f"no deployments found in {registry.deployments_dir()}")
            return 2
    else:
        targets = [str(registry.resolve(args.deployment))]   # never a default
    failed = 0
    loaded = []
    for target in targets:
        try:
            reg = registry.load(registry.resolve(target))
        except RegistryError as exc:
            print(f"✗ {target}: {exc}")
            failed += 1
            continue
        loaded.append(reg)
        findings = registry.validate(reg)
        bad = registry.errors(findings)
        try:
            radio = reg.radio.describe()
        except ValueError as exc:
            radio = f"(invalid radio profile: {exc})"
        mark = "✗" if bad else "✓"
        print(f"{mark} {reg.name} [{reg.meta.kind}] {len(reg.nodes)} nodes — {radio}")
        for f in findings:
            if f.level == "error" or not args.quiet:
                print(f"    {f}")
        failed += bool(bad)
    if args.all and not args.quiet:
        for msg in registry.shared_channels(loaded):
            print(f"  note: {msg}")
    return 1 if failed else 0


def cmd_show(args) -> int:
    reg = registry.load_deployment(args.deployment, report=None)
    print(f"{reg.name} [{reg.meta.kind}] — {reg.path}")
    print(f"  {reg.radio.describe()}")
    if reg.meta.cadence_scale != 1:
        print(f"  cadence_scale x{reg.meta.cadence_scale} (effective cadences shown)")
    print()
    print(f"  {'ref':<4} {'function':<9} {'status':<9} {'node_id':<10} {'hardware':<27} "
          f"{'antenna':<16} {'tx':>4} {'EIRP':>5}  {'sensors':<7} intervals")
    for n in reg.nodes:
        a = n.antenna
        ant = f"{a.type} {a.gain_dbi:g}dBi" if a else "-"
        eirp = f"{n.tx_power_dbm + a.gain_dbi:g}" if a and n.tx_power_dbm is not None else "-"
        tx = "-" if n.tx_power_dbm is None else str(n.tx_power_dbm)
        iv = ", ".join(f"{k}={v}" for k, v in reg.intervals(n).items()) or "-"
        print(f"  {n.ref:<4} {n.function:<9} {n.status:<9} {n.node_id or '-':<10} "
              f"{n.hardware or '-':<27} {ant:<16} {tx:>4} {eirp:>5}  "
              f"{'+'.join(s.type for s in n.sensors) or '-':<7} {iv}")

    # Sites: what has been filled in on site, and what is still to do.
    print(f"\n  {'ref':<4} {'site':<30} {'asset':<10} {'surveyed lat, lon':<25} "
          f"{'alt m':>6} {'antenna m':>9}")
    for n in reg.nodes:
        s = n.site
        pos = s.surveyed if s else None
        where = f"{pos.lat:.7f}, {pos.lon:.7f}" if pos else "to fill"
        alt = f"{pos.alt_m:g}" if pos and pos.alt_m is not None else "-"
        height = f"{s.antenna_height_m:g}" if s and s.antenna_height_m is not None else "-"
        print(f"  {n.ref:<4} {(s.name if s and s.name else 'to fill'):<30.30} "
              f"{(s.asset_code if s and s.asset_code else '-'):<10} {where:<25} {alt:>6} {height:>9}")
    return 0


def cmd_inspect(args) -> int:
    from meshtastic_platform.provision import inspector
    reg = registry.load_deployment(args.deployment)
    return inspector.inspect(reg, args.port, ref=args.node, mesh=not args.no_mesh)


def cmd_provision(args) -> int:
    from meshtastic_platform.provision import identity, plan
    from meshtastic_platform.radio import profile as radio_profile

    reg = registry.load_deployment(args.deployment)
    if reg.meta.kind == "historical":
        print(f"ERROR: {reg.name} is a historical registry — a record of what was, not a plan.")
        return 2
    try:
        node = reg.by_ref(args.node)
    except KeyError as exc:
        print(f"ERROR: {exc.args[0]}. Registry entries are written deliberately, never on the fly.")
        return 2
    if node.status == "retired":
        print(f"ERROR: {node.ref} is retired in {reg.name}.")
        return 2
    if not args.port and not args.dry_run:
        print("ERROR: --port is required (use a /dev/serial/by-id/ path: ttyACM* is "
              "enumeration order, not identity).")
        return 2

    try:
        psks = radio_profile.channel_psks(reg.radio)
    except RuntimeError as exc:
        if not args.dry_run:
            print(f"ERROR: {exc}")
            return 2
        psks = {ch.index: "<unset>" for ch in reg.radio.channels}

    print(f"{reg.name}: provisioning {node.ref} ({node.function}, {node.role})")
    print(f"  {reg.radio.describe()}")
    print(f"  tx_power {reg.expected_tx_power(node)} dBm (derived), "
          f"cadences {reg.intervals(node) or 'none'}\n")

    # Identify the device before writing anything; stop on any doubt.
    if args.port:
        import meshtastic.serial_interface
        try:
            iface = meshtastic.serial_interface.SerialInterface(args.port)
        except Exception as exc:
            print(f"ERROR: could not open {args.port}: {exc}")
            return 2
        try:
            dev = identity.read_identity(iface)
        finally:
            iface.close()
        others = []
        for name in registry.available():
            try:
                others.append(registry.load(registry.resolve(name)))
            except RegistryError:
                pass
        problems, notes = identity.preflight(dev, reg, node, others)
        for n in notes:
            print(f"  note: {n}")
        if problems:
            print("\nREFUSING to provision:")
            for p in problems:
                print(f"  ! {p}")
            return 1

    steps = plan.node_steps(reg, node, args.port, psks)
    if args.dry_run:
        print("\nDry run — nothing written. Plan:")
        for s in steps:
            print(f"  [{s.label}]\n    {s.display()}")
        return 0

    from meshtastic_platform.provision import node as node_prov
    failures = node_prov.execute(steps, rebroadcast_mode=reg.radio.rebroadcast_mode,
                                 port=args.port)
    return node_prov.report(failures, node.ref)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python configure.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check a deployment registry's invariants")
    _deployment_arg(p)
    p.add_argument("--all", action="store_true", help="validate every file in deployments/")
    p.add_argument("--quiet", "-q", action="store_true", help="errors only")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("show", help="print a deployment: nodes, derived tx_power, radio profile")
    _deployment_arg(p)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("provision", help="configure a radio from its registry entry")
    _deployment_arg(p)
    p.add_argument("--node", "--ref", dest="node", required=True,
                   help="the node's ref in the deployment registry")
    p.add_argument("--port", help="serial port (prefer /dev/serial/by-id/...)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan (and run the identity checks if --port is given); "
                        "write nothing")
    p.set_defaults(func=cmd_provision)

    p = sub.add_parser("inspect", help="inspect a live radio against its deployment (exit 1 on drift)")
    _deployment_arg(p)
    p.add_argument("--port", help="serial port; auto-detected only if exactly one device is present")
    p.add_argument("--node", "--ref", dest="node",
                   help="the registry ref this device is expected to be (commissioning)")
    p.add_argument("--no-mesh", action="store_true", help="skip the mesh node-database cross-check")
    p.set_defaults(func=cmd_inspect)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RegistryError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
