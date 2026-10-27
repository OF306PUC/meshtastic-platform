"""Run a provisioning plan against a radio: a node, a gateway radio or a receiver.

    python configure.py provision -d <deployment> --node <ref> --port /dev/serial/by-id/...
    python configure.py provision -d <deployment> --node <ref> --dry-run

The values come from the registry (role, cadences, sensors, GPS, channels), so
one provisioner serves every kind of radio. Every failed step is reported and
the exit status is non-zero: a partially configured node must not look like a
configured one.

Flashing is out of scope (docs/flashing.md). After provisioning, verify with
`python configure.py inspect` and read the real transmit power from the
"Final Tx power: N dBm" console line at boot — the config value is what the
radio was told, not what it does.
"""
from __future__ import annotations

from meshtastic_platform.cli.meshtastic_cli import SETTLE_DELAY, get_config_value, run
from meshtastic_platform.provision.plan import Step


def execute(steps: list[Step], *, rebroadcast_mode: str | None = None,
            port: str | None = None, settle: float = SETTLE_DELAY) -> list[str]:
    """Run the steps in order; return the labels of those that failed."""
    failures = []
    for step in steps:
        if not run(step.argv, settle=settle, display=step.display()):
            failures.append(step.label)
        if rebroadcast_mode and step.label.startswith("device role"):
            argv = ["meshtastic"] + (["--port", port] if port else [])
            actual = get_config_value(argv, "device.rebroadcast_mode")
            if rebroadcast_mode.lower() not in actual.lower():
                print(f"WARNING: device.rebroadcast_mode did not persist "
                      f"(expected {rebroadcast_mode}, read '{actual or 'unknown'}').")
                failures.append("device.rebroadcast_mode (verify)")
            else:
                print(f"Verified device.rebroadcast_mode = {rebroadcast_mode}")
    return failures


def report(failures: list[str], ref: str) -> int:
    if failures:
        print(f"\n=== {ref}: configuration completed with ERRORS ===")
        for label in failures:
            print(f"  FAILED: {label}")
        print(f"{len(failures)} step(s) failed; the node may be partially configured.")
        return 1
    print(f"\n=== {ref}: configuration completed ===")
    print("Next: `python configure.py inspect` against the same deployment, and read the "
          "'Final Tx power' line on the console at boot.")
    return 0
