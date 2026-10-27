"""Interchangeable outputs for a channel-study session.

    class Sink(Protocol):
        def emit(self, rx: Reception) -> None: ...
        def close(self) -> None: ...

A sink receives a Reception — the DecodedPacket plus the time and session
context the decoder deliberately does not know. Sinks may also implement
`note(event)` for session events (gaps opening and closing). Several run at
once, and making CSV optional changes no other code path: it is one more sink
in the list.
"""
from __future__ import annotations

from typing import Any, Protocol

from channel_study.records import Reception


class Sink(Protocol):
    def emit(self, rx: Reception) -> None: ...

    def close(self) -> None: ...


_REDACT_PORTNUMS = {"PRIVATE_APP", "TEXT_MESSAGE_APP"}


def jsonable(value: Any, *, capture_content: bool = False, _portnum: str | None = None) -> Any:
    """A MeshPacket dict made JSON-safe, keeping every field.

    * bytes become "hex:<hex>";
    * the library's `raw` protobuf mirrors are dropped — they duplicate the
      parsed dict field for field;
    * message payloads (PRIVATE_APP, TEXT_MESSAGE_APP) are redacted to their
      length unless capture_content is set: they may be real people's traffic.
    """
    if isinstance(value, dict):
        portnum = value.get("portnum", _portnum) if isinstance(value.get("portnum"), str) else _portnum
        out = {}
        for k, v in value.items():
            if k == "raw" and not isinstance(v, (dict, list, str, int, float, bool, type(None))):
                continue
            if (k in ("payload", "text") and portnum in _REDACT_PORTNUMS and not capture_content):
                n = len(v) if isinstance(v, (bytes, bytearray, str)) else 0
                out[k] = f"<redacted {n} B>"
                continue
            out[k] = jsonable(v, capture_content=capture_content, _portnum=portnum)
        return out
    if isinstance(value, (list, tuple)):
        return [jsonable(v, capture_content=capture_content, _portnum=_portnum) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return "hex:" + bytes(value).hex()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)
