"""IEEE-paper plotting style + composite encoding for presets and for nodes.

Style: white surface, boxed axes with inward ticks, serif type, thin lines,
sparse open markers, dotted grid.

Nine presets exceed the categorical-color limit, so identity uses **composite
encoding** instead of nine hues:
  * hue           = preset family  — Short / Medium / Long
  * line style + marker = speed variant within the family (Turbo -> ... -> Slow)
  * a direct label names each curve, so identity is never colour-alone.

Palette (validated with the dataviz skill's validate_palette.js, light surface,
``--pairs all``): blue / orange / aqua — worst all-pairs CVD ΔE 9.2 (>= 8 target),
normal-vision ΔE 24.0. NOTE: a *true* Meshtastic green (#008300) was rejected —
it fails CVD against the orange family (ΔE 3.2, protan), so the CVD-safe aqua is
used for the Long family. Aqua sits below 3:1 contrast on white, which the
direct labels (the relief rule) cover.

``node_style`` applies the same idea to a deployment's nodes, keyed on a node
GROUP rather than preset family. The roster comes from the deployment registry:
``set_roster(*roster_from_registry(reg))`` before plotting.

This module is AUTHORITATIVE for figure style. Any new colour must be
CVD-validated at ΔE >= 8 against every existing pair before it lands here.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from meshtastic_platform.radio.presets import FAMILIES

# --- validated 3-hue family palette (light surface) ---
FAMILY_HUE: dict[str, str] = {
    "Short": "#2a78d6",   # blue   (categorical slot 1)
    "Medium": "#eb6834",  # orange (categorical slot 2)
    "Long": "#1baf7a",    # aqua   (categorical slot 3; CVD-safe stand-in for green)
}

# Speed variant within a family, fastest/lowest-airtime first. Solid -> dotted.
VARIANT_STYLES: list = ["-", "--", "-.", ":"]
VARIANT_MARKERS: list = ["x", "s", "*", "D"]

# Chrome / ink (dataviz reference palette, light mode).
SURFACE = "#ffffff"
GRID = "#8f8e88"
MUTED = "#898781"
BASELINE = "#c3c2b7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"

# Families in speed order come from the radio catalogue (radio.presets), which
# covers every preset exactly once.

# Reverse map: preset_key -> (family, variant_index).
_PRESET_INDEX: dict[str, tuple[str, int]] = {
    key: (family, i)
    for family, variants in FAMILIES.items()
    for i, key in enumerate(variants)
}


def preset_style(preset_key: str) -> dict:
    """Composite-encoding style for a preset: family hue + variant style/marker.

    Returns kwargs suitable for ``ax.plot`` (open marker, hue edge). Presets not
    in a known family fall back to a neutral solid line.
    """
    if preset_key not in _PRESET_INDEX:
        return dict(color=INK_SECONDARY, linestyle="-", marker="o",
                    markerfacecolor="white", markeredgecolor=INK_SECONDARY)
    family, idx = _PRESET_INDEX[preset_key]
    hue = FAMILY_HUE[family]
    return dict(
        color=hue,
        linestyle=VARIANT_STYLES[idx % len(VARIANT_STYLES)],
        marker=VARIANT_MARKERS[idx % len(VARIANT_MARKERS)],
        markerfacecolor="white",
        markeredgecolor=hue,
        markeredgewidth=0.7,
    )


# Marker cycle for figures that plot an arbitrary *subset* of presets. The
# variant marker above repeats across families (SHORT_FAST and LONG_FAST are
# both variant 1, so both get a square), which is fine when all nine curves are
# shown together -- family hue separates them -- but not when three presets from
# three families sit on the same axes. Ordered for shape contrast.
DISTINCT_MARKERS: list = ["o", "s", "^", "D", "v", "P", "X", "*", ">"]


def distinct_marker_styles(preset_keys) -> dict[str, dict]:
    """``preset_style`` per key, overriding the marker so no two curves repeat.

    Hue (family) and line style (speed variant) are kept, so the composite
    encoding still reads; only the marker channel is reassigned, by position in
    ``preset_keys``. Pass the keys in plot order and reuse the result for every
    axes in the figure, so a curve keeps its marker in insets and legends.
    """
    styles: dict[str, dict] = {}
    for i, key in enumerate(preset_keys):
        style = preset_style(key)
        style["marker"] = DISTINCT_MARKERS[i % len(DISTINCT_MARKERS)]
        styles[key] = style
    return styles


# --- node identity (a deployment's mesh) ---
# The same composite encoding as the presets above, applied to the other thing
# plotted repeatedly: nodes. Hue carries the GROUP (e.g. antenna type, or with /
# without a sensor), because that is the distinction a reader needs first, and
# line style + marker separate the members within a group. Two hues instead of
# one per node also validate far more comfortably: blue vs orange scores
# all-pairs CVD ΔE 24.7 and clears 3:1 contrast on white.
#
# Empty until set_roster() is called: there is no built-in deployment.
ROLES: dict[str, list[str]] = {}
SITES: dict[str, str] = {}
ROLE_HUE: dict[str, str] = {}
ROLE_STEPS: dict[str, list[str]] = {}

# Group hues by position: the first group takes the blue ramp, the second the
# orange one. A third group would need a third CVD-validated ramp; set_roster()
# refuses rather than reuse a hue.
_GROUP_HUES = [FAMILY_HUE["Short"], FAMILY_HUE["Medium"]]

# Member markers: a group of up to 28 members keeps a unique (line style,
# marker) pair — with 3 lightness steps per hue, a fifth member would otherwise
# differ from the first by colour alone. Markers are shape, not colour: no
# palette validation is affected.
NODE_MARKERS: list = ["x", "s", "*", "D", "o", "^", "v"]

# Lightness steps within each group, one per member. Line style and marker alone
# proved too weak to separate three same-hue curves on dense, oscillating
# telemetry: the dash pattern is swamped once the line changes direction every
# few pixels, which left the marker doing all the work. Stepping lightness adds
# a channel that survives that.
#
# Blue steps are 300 / 450 / 600 of the reference palette's blue ramp; orange is
# the categorical slot plus a darker step of the same hue.
#
# Validated (light surface, --pairs all): lightness band, chroma floor and CVD
# separation all PASS. Two known, accepted shortfalls:
#   * #184f95 vs #2a78d6 scores normal-vision ΔE 14.7 against a 15 floor — the
#     categorical lightness band simply has no room for three blues that all
#     clear it. Legal here only because line style + marker + a legend entry
#     carry identity alongside colour; do not drop those channels.
#   * #6da7ec sits at 2.44:1 on white, under 3:1, so the relief rule applies:
#     figures using it must keep visible labels (legend or direct label).
_GROUP_STEPS = [["#6da7ec", "#2a78d6", "#184f95"], ["#eb6834", "#a8410f"]]

# Reverse map: node_label -> (group, member_index).
_NODE_INDEX: dict[str, tuple[str, int]] = {}


def set_roster(groups: dict[str, list[str]], sites: dict[str, str] | None = None) -> None:
    """Set the node roster: {group: [node labels]} in plot order.

    Group order decides hue (first blue, second orange). Called once per
    figure script, before plotting, typically with roster_from_registry().
    """
    if len(groups) > len(_GROUP_HUES):
        raise ValueError(f"{len(groups)} node groups, but only {len(_GROUP_HUES)} validated "
                         f"group hues exist; validate a new ramp before adding one")
    ROLES.clear()
    ROLES.update({g: list(m) for g, m in groups.items()})
    ROLE_HUE.clear()
    ROLE_STEPS.clear()
    for i, g in enumerate(groups):
        ROLE_HUE[g] = _GROUP_HUES[i]
        ROLE_STEPS[g] = _GROUP_STEPS[i]
    _NODE_INDEX.clear()
    _NODE_INDEX.update({label: (g, i) for g, members in ROLES.items()
                        for i, label in enumerate(members)})
    SITES.clear()
    SITES.update(sites or {})


def roster_from_registry(reg, group_by: str = "antenna") -> tuple[dict, dict]:
    """(groups, sites) for set_roster(), from a deployment registry.

    group_by:
      "antenna"  by antenna type
      "sensors"  nodes with a sensor vs without
    Only nodes that broadcast a measured flow are plotted (gateways and
    receivers are sinks). Sites are the registry's site names, when filled in.
    """
    groups: dict[str, list[str]] = {}
    sites: dict[str, str] = {}
    for n in reg.nodes:
        if n.function != "node" or not n.intervals:
            continue
        if group_by == "antenna":
            key = n.antenna.type if n.antenna else "unknown antenna"
        elif group_by == "sensors":
            key = "with sensor" if n.sensors else "without sensor"
        else:
            raise ValueError(f"group_by must be 'antenna' or 'sensors', got {group_by!r}")
        groups.setdefault(key, []).append(n.name)
        if n.site and n.site.name:
            sites[n.name] = n.site.name
    return groups, sites


def node_style(node_label: str) -> dict:
    """Composite-encoding style for a node: role hue + member style/marker.

    Returns kwargs suitable for ``ax.plot``. Nodes outside the known roster fall
    back to a neutral solid line, so a node added to the mesh still plots.
    """
    if node_label not in _NODE_INDEX:
        return dict(color=INK_SECONDARY, linestyle="-", marker="o",
                    markerfacecolor="white", markeredgecolor=INK_SECONDARY)
    role, idx = _NODE_INDEX[node_label]
    steps = ROLE_STEPS[role]
    hue = steps[idx % len(steps)]
    return dict(
        color=hue,
        linestyle=VARIANT_STYLES[idx % len(VARIANT_STYLES)],
        marker=NODE_MARKERS[idx % len(NODE_MARKERS)],
        markerfacecolor="white",
        markeredgecolor=hue,
        markeredgewidth=0.7,
    )


def role_of(node_label: str) -> str:
    """Which group a node belongs to; "" for a node outside the roster."""
    for role, members in ROLES.items():
        if node_label in members:
            return role
    return ""


def describe(node_label: str) -> str:
    """Node name with its group and, where known, its site."""
    parts = [p for p in (role_of(node_label), SITES.get(node_label)) if p]
    return f"{node_label} ({' · '.join(parts)})" if parts else node_label


def markevery(n_points: int, target: int = 12) -> int:
    """Marker stride that puts about `target` markers on a curve.

    The preset figures this style came from plot a handful of points each, so a
    marker per point reads as "sparse open markers". A telemetry series carries
    thousands, where a marker per point is a solid band -- the marker channel
    stops encoding identity and starts hiding the line. Striding restores it.
    """
    return max(1, n_points // max(1, target))


def apply_paper_style() -> None:
    """IEEE-paper matplotlib defaults: white surface, boxed axes, inward ticks."""
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 8,
        "axes.labelsize": 10.5,
        "axes.titlesize": 12,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 6,
        # boxed axes: black frame
        "axes.edgecolor": "black",
        "axes.linewidth": 0.8,
        "axes.facecolor": SURFACE,
        "figure.facecolor": SURFACE,
        "axes.spines.top": True,
        "axes.spines.right": True,
        # inward ticks, minor ticks on
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_SECONDARY,
        "ytick.labelcolor": INK_SECONDARY,
        "xtick.minor.visible": True,
        "ytick.minor.visible": True,
        # dotted recessive grid
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.4,
        "grid.linestyle": ":",
        # ink
        "text.color": INK_PRIMARY,
        "axes.labelcolor": INK_PRIMARY,
        # marks / legend / output
        "lines.linewidth": 1.2,
        "lines.markersize": 2.2,
        "legend.frameon": True,
        "legend.framealpha": 0.9,
        "legend.edgecolor": "0.7",
        "figure.dpi": 150,
        # Raster output resolution. The CLI scripts pass dpi= explicitly to
        # savefig (--dpi, default 200), so this only applies to callers that
        # don't; keep the two in step.
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    })