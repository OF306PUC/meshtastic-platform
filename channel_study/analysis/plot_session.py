"""plot_session.py — figures from one recorded channel-study session.

    python -m channel_study.analysis.plot_session runs/2026-11-03/
    python -m channel_study.analysis.plot_session runs/2026-11-03/ --out figs/ --node N4

Per node: RSSI | SNR, then environment and device panels when the node sends
them. Direct (hop 0) and relayed receptions are separate series, because for a
relayed packet RSSI/SNR describe relay -> receiver, not the node's own link.
Gaps the receiver announced (gaps.csv) are shaded. For the receiving radio's
own GPS track: latitude, longitude, altitude, and the trajectory — from
track.csv, sampled over USB during the session, or failing that from the
positions that radio put on air.

Conventions (plotstyle): 7.16 in = IEEE double-column width; no titles inside
the artwork; identity never by colour alone; vector PDF for publication, PNG
only for review, dpi passed explicitly. Provenance (run_id, deployment) goes in
the caption — written next to each figure as <name>.caption.txt.
"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from channel_study.analysis import plotstyle
from channel_study.session import load_session
from channel_study.track import TRACK_FILE

WIDTH_IN = 7.16
REVIEW_DPI = 200

# Direct vs relayed: two series, told apart by line style AND marker AND a
# legend entry — never by hue alone.
_HOP_STYLES = {
    "direct": dict(color=plotstyle.FAMILY_HUE["Short"], linestyle="-", marker="x"),
    "relayed": dict(color=plotstyle.FAMILY_HUE["Medium"], linestyle="none", marker="s"),
}
for _s in _HOP_STYLES.values():
    _s.update(markerfacecolor="white", markeredgecolor=_s["color"], markeredgewidth=0.7)


def _to_local(seconds: pd.Series) -> pd.Series:
    """Unix seconds -> naive local time, to read against the field notebook."""
    tz = datetime.datetime.now().astimezone().tzinfo
    return pd.to_datetime(seconds, unit="s", utc=True).dt.tz_convert(tz).dt.tz_localize(None)


def _read(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["time"] = _to_local(df["received_at"])
    return df.sort_values("time").reset_index(drop=True)


def _first_only(df: pd.DataFrame) -> pd.DataFrame:
    """First receptions only: a duplicate is the same transmission heard again."""
    return df[df["duplicate"] == 0] if "duplicate" in df.columns and not df.empty else df


def _shade_gaps(axes, gaps: pd.DataFrame, ref: str) -> None:
    if gaps.empty:
        return
    g = gaps[gaps["ref"] == ref]
    closed = g[g["state"] == "closed"]
    for _, row in closed.iterrows():
        end = row["time"]
        start = end - pd.to_timedelta(row["silent_s"], unit="s")
        for ax in axes:
            ax.axvspan(start, end, color=plotstyle.BASELINE, alpha=0.35, linewidth=0)


def _series(ax, df, col, label=True):
    """Direct and relayed receptions as two composite-encoded series."""
    if df.empty or col not in df.columns:
        ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center",
                va="center", color=plotstyle.MUTED, fontsize=8)
        return
    for name, part in (("direct", df[df["hops"] == 0]),
                       ("relayed", df[df["hops"].fillna(-1) != 0])):
        part = part.dropna(subset=[col])
        if part.empty:
            continue
        x, y = part["time"], part[col]
        if name == "direct":
            x, y = _break_at_gaps(x, y)
        every = plotstyle.markevery(len(part)) if name == "direct" else 1
        ax.plot(x, y, label=name if label else None, markevery=every, **_HOP_STYLES[name])


def _break_at_gaps(x: pd.Series, y: pd.Series):
    """Insert a NaN wherever arrivals stop for > 3x the usual spacing.

    A line drawn across a silence implies readings that never arrived; the
    break makes the silence look like what it is. The usual spacing is the
    median of the POSITIVE intervals — the link panels merge flows, whose
    receptions can share a timestamp — and 3x tolerates one missed packet.
    """
    dt = x.diff()
    positive = dt[dt > pd.Timedelta(0)]
    if len(x) < 3 or positive.empty:
        return x, y
    cut = dt > 3 * positive.median()
    if not cut.any():
        return x, y
    xs, ys = [], []
    for (t, v), brk in zip(zip(x, y), cut):
        if brk:
            xs.append(t)
            ys.append(float("nan"))
        xs.append(t)
        ys.append(v)
    return pd.Series(xs), pd.Series(ys)


def _time_axis(ax, label: bool):
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    if label:
        ax.set_xlabel("Local time")


def _save(fig, out: Path, name: str, caption: str) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / f"{name}.pdf", out / f"{name}.png"]
    fig.savefig(paths[0])                     # vector, for publication
    fig.savefig(paths[1], dpi=REVIEW_DPI)     # raster, for review only
    (out / f"{name}.caption.txt").write_text(caption + "\n")
    plt.close(fig)
    for p in paths:
        print(f"Saved → {p}")
    return paths


def plot_node(session_dir: Path, ref: str, meta: dict, gaps: pd.DataFrame, out: Path):
    env = _first_only(_read(session_dir / f"{ref}_environment.csv"))
    dev = _first_only(_read(session_dir / f"{ref}_device.csv"))
    pos = _first_only(_read(session_dir / f"{ref}_position.csv"))
    link = pd.concat([d for d in (env, dev, pos) if not d.empty], ignore_index=True)
    if link.empty:
        print(f"[SKIP] {ref}: no receptions")
        return
    link = link.sort_values("time")

    rows = [("rssi", "RSSI (dBm)"), ("snr", "SNR (dB)")]
    if not env.empty:
        rows += [("temperature", "Temperature (°C)"), ("relative_humidity", "RH (%)")]
    if not dev.empty:
        rows += [("channel_utilization", "Channel util. (%)"), ("air_util_tx", "TX airtime (%)")]
    nrows = (len(rows) + 1) // 2
    fig, axes = plt.subplots(nrows, 2, figsize=(WIDTH_IN, 1.9 * nrows), sharex=True, squeeze=False)
    flat = list(axes.flat)
    sources = {"rssi": link, "snr": link, "temperature": env, "relative_humidity": env,
               "channel_utilization": dev, "air_util_tx": dev}
    for i, (ax, (col, ylabel)) in enumerate(zip(flat, rows)):
        _series(ax, sources[col], col, label=(i == 0))
        ax.set_ylabel(ylabel)
        _time_axis(ax, label=ax in axes[-1])
    snr_floor = meta["deployment"].get("snr_floor_db")
    if snr_floor is not None:
        flat[1].axhline(snr_floor, color=plotstyle.INK_SECONDARY, linewidth=0.7, linestyle=(0, (4, 3)))
    for ax in flat[len(rows):]:
        ax.set_visible(False)
    _shade_gaps(flat[:len(rows)], gaps, ref)
    if flat[0].get_legend_handles_labels()[1]:
        flat[0].legend(loc="best")
    fig.tight_layout(h_pad=0.6)
    tx = link.iloc[0]
    caption = (f"Node {ref} as received during run {meta['run_id']} (deployment "
               f"{meta['deployment']['name']}, {meta['deployment']['modem_preset']}, "
               f"{meta['deployment'].get('slot_mhz')} MHz). Transmitter antenna "
               f"{tx.get('tx_antenna_type')} {tx.get('tx_antenna_gain_dbi')} dBi at "
               f"{tx.get('tx_power_dbm')} dBm; received on {tx.get('rx_ref')} "
               f"({tx.get('rx_antenna_type')} {tx.get('rx_antenna_gain_dbi')} dBi). "
               f"Solid: direct (hop 0) receptions; markers only: relayed, whose levels "
               f"describe the relay's link. Shaded: gaps longer than 1.5x the cadence.")
    return _save(fig, out, f"{meta['run_id']}_{ref}", caption)


def _track_frame(session_dir: Path, rx_ref: str) -> tuple[pd.DataFrame, str]:
    """The locally sampled track, or failing that the broadcast one.

    track.csv is read over USB on --track-secs: denser, and it costs no airtime.
    A session recorded without it has only the positions that radio put on air,
    at its declared cadence.
    """
    df = _read(session_dir / TRACK_FILE)
    if not df.empty:
        return df.dropna(subset=["latitude", "longitude"]), "sampled over USB"
    df = _read(session_dir / f"{rx_ref}_position.csv")
    if not df.empty:
        if "own" in df.columns:
            df = df[df["own"] == 1]
        df = df.dropna(subset=["latitude", "longitude"])
    return df, "from the positions it broadcast"


def plot_track(session_dir: Path, meta: dict, out: Path):
    rx_ref = meta["receiver"].get("ref") or "self"
    df, source = _track_frame(session_dir, rx_ref)
    if df.empty:
        print("[SKIP] no GPS track from the receiving radio")
        return
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH_IN, 4.2))
    ax_lat, ax_lon, ax_alt, ax_traj = axes.flat
    style = dict(_HOP_STYLES["direct"])
    for ax, col, label in ((ax_lat, "latitude", "Latitude (°)"),
                           (ax_lon, "longitude", "Longitude (°)"),
                           (ax_alt, "altitude", "Altitude (m)")):
        ax.plot(df["time"], df[col], markevery=plotstyle.markevery(len(df)), **style)
        ax.set_ylabel(label)
        _time_axis(ax, label=ax in (ax_alt,))
    ax_traj.plot(df["longitude"], df["latitude"], markevery=plotstyle.markevery(len(df)), **style)
    # Start and end are told apart by shape AND a direct label, never by colour.
    for row, marker, text, xy, ha in ((df.iloc[0], "^", "start", (5, 3), "left"),
                                      (df.iloc[-1], "s", "end", (-5, -9), "right")):
        ax_traj.plot(row["longitude"], row["latitude"], marker=marker, markersize=5,
                     color=plotstyle.INK_PRIMARY, markerfacecolor="white", linestyle="none")
        ax_traj.annotate(text, (row["longitude"], row["latitude"]), xytext=xy, ha=ha,
                         textcoords="offset points", fontsize=7, color=plotstyle.INK_PRIMARY)
    ax_traj.set_xlabel("Longitude (°)")
    ax_traj.set_ylabel("Latitude (°)")
    # Plain coordinates: an offset like "-1.0943e2" makes a reader do arithmetic.
    for ax in (ax_lat, ax_lon):
        ax.ticklabel_format(axis="y", useOffset=False, style="plain")
    ax_traj.ticklabel_format(useOffset=False, style="plain")
    ax_traj.tick_params(axis="x", labelrotation=30)
    fig.tight_layout(h_pad=0.6)
    interval = (meta.get("track") or {}).get("interval_s")
    every = f" every {interval:g} s" if interval and source.endswith("USB") else ""
    repeated = int(df["repeated"].sum()) if "repeated" in df.columns else 0
    caption = (f"GPS track of the receiving radio {rx_ref} during run {meta['run_id']} "
               f"(deployment {meta['deployment']['name']}), {source}{every}: "
               f"{len(df)} fixes."
               + (f" {repeated} of them repeat the previous fix, GPS timestamp included: "
                  f"nothing new arrived from the receiver's own GPS." if repeated else ""))
    return _save(fig, out, f"{meta['run_id']}_track", caption)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session_dir", help="directory holding session.json and the CSVs")
    ap.add_argument("--out", default=None, help="output directory (default: <session>/figures)")
    ap.add_argument("--node", action="append", help="only these refs (repeatable)")
    args = ap.parse_args(argv)

    session_dir = Path(args.session_dir)
    meta = load_session(session_dir)       # refuses unlabelled data
    out = Path(args.out) if args.out else session_dir / "figures"
    plotstyle.apply_paper_style()
    from meshtastic_platform.radio.presets import snr_floor_db
    meta["deployment"]["snr_floor_db"] = snr_floor_db(meta["deployment"]["modem_preset"])

    refs = sorted({p.name.rsplit("_", 1)[0] for p in session_dir.glob("*_*.csv")
                   if p.name != "gaps.csv"})
    rx_ref = meta["receiver"].get("ref") or "self"
    gaps = _read(session_dir / "gaps.csv")
    for ref in refs:
        if args.node and ref not in args.node:
            continue
        if ref == rx_ref:
            continue
        plot_node(session_dir, ref, meta, gaps, out)
    plot_track(session_dir, meta, out)


if __name__ == "__main__":
    main()
