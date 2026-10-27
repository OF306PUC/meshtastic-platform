"""Shared helper for driving the Meshtastic CLI with retry-on-transient-error.

Accepts a shell string or an argv list (no shell, so
ports, PSKs and negative numbers need no quoting), and returns whether the
command finally succeeded so callers can report a partial configuration
instead of carrying on as if nothing happened.
"""
import subprocess
import time

MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds to wait before retrying
SETTLE_DELAY = 2  # seconds to let the node settle after a successful command

# Keywords that indicate a transient serial error worth retrying
RETRYABLE_ERRORS = [
    "couldn't be opened",
    "Input/output error",
    "OS Error",
    "serial device",
    "write failed",
]


def is_retryable(stderr: str, stdout: str) -> bool:
    combined = (stderr + stdout).lower()
    return any(keyword.lower() in combined for keyword in RETRYABLE_ERRORS)


def run(cmd, retries=MAX_RETRIES, settle=SETTLE_DELAY, display=None) -> bool:
    """Run one CLI command; True if it eventually succeeded.

    `display` replaces the echoed command line — callers pass a redacted one
    when the argv carries a channel PSK, which must never reach the console.
    """
    shown = display or (cmd if isinstance(cmd, str) else " ".join(cmd))
    print(f"\nRunning: {shown}")
    for attempt in range(1, retries + 1):
        result = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True)
        print(result.stdout)
        if result.returncode == 0 and not is_retryable(result.stderr, result.stdout):
            time.sleep(settle)
            return True  # success
        # Something went wrong
        print(f"ERROR (attempt {attempt}/{retries}):", result.stderr or result.stdout)
        if attempt < retries:
            print(f"Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
        else:
            print(f"Command failed after {retries} attempts.")
            time.sleep(2)
    return False


def get_config_value(argv_prefix, key):
    """Read back a single config value via `meshtastic --get <key>`.

    `argv_prefix` is the argv list up to --get, e.g. ['meshtastic', '--port', p]
    (no shell, so ports/paths need no quoting). Returns the reported value as a
    string, or '' if it couldn't be read. Used to verify a --set actually
    persisted — e.g. device.rebroadcast_mode, which was silently not sticking
    when set in the same command as device.role.
    """
    result = subprocess.run(argv_prefix + ["--get", key], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        # The CLI prints lines like "device.rebroadcast_mode: 2" (see
        # reads_as() for why an enum comes back as a number).
        if key in line and ":" in line:
            return line.split(":", 1)[1].strip()
    return ""


def reads_as(actual: str, expected: str, enum_type=None) -> bool:
    """Does a value read with `--get` mean `expected`?

    `meshtastic --get` prints a field through `util.toStr`, and for an enum
    that is the raw protobuf int: `device.rebroadcast_mode: 2`, not
    `LOCAL_ONLY`. Comparing the name against that output always fails, which
    reports a setting that DID persist as lost — the opposite of useful. Both
    spellings are accepted; pass `enum_type` (a protobuf EnumTypeWrapper) to
    resolve the name.
    """
    actual = (actual or "").strip()
    if not actual:
        return False
    if actual.casefold() == expected.casefold():
        return True
    if enum_type is None:
        return False
    try:
        return actual == str(enum_type.Value(expected.upper()))
    except Exception:          # not a name of this enum: no match, not a crash
        return False
