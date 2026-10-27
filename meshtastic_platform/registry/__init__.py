"""Per-deployment node registry: load, validate, query.

    reg = load_deployment(name)                # or --deployment / MESH_DEPLOYMENT
    reg.radio.describe()                       # region, preset, slot, power cap
    reg.intervals(reg.by_ref(ref))             # the cadences estimators measure against

Operational tools use load_deployment(), which refuses a registry with
validation errors and prints every warning: nothing a tool does may rest on a
registry the validator rejects.
"""
from __future__ import annotations

from typing import Callable

from meshtastic_platform.registry.loader import (
    ENV_DEPLOYMENT, RegistryError, available, deployments_dir, load, parse, resolve,
)
from meshtastic_platform.registry.model import (
    Antenna, Meta, Node, Position, Registry, Sensor, Site,
)
from meshtastic_platform.registry.validate import (
    Finding, comparable, errors, shared_channels, validate,
)

__all__ = [
    "ENV_DEPLOYMENT", "Antenna", "Finding", "Meta", "Node", "Position", "Registry",
    "RegistryError", "Sensor", "Site", "available", "comparable", "deployments_dir",
    "errors", "load", "load_deployment", "parse", "resolve", "shared_channels", "validate",
]


def load_deployment(name_or_path: str | None = None, *,
                    report: Callable[[str], None] | None = print) -> Registry:
    """Resolve, load and validate a deployment. Raises RegistryError on any error."""
    reg = load(resolve(name_or_path))
    findings = validate(reg)
    if report is not None:
        for f in findings:
            if f.level == "warning":
                report(f"{reg.name}: {f}")
    bad = errors(findings)
    if bad:
        raise RegistryError(f"deployment {reg.name!r} ({reg.path}) fails validation; "
                            f"run `python configure.py validate -d {reg.name}`",
                            [str(f) for f in bad])
    return reg
