"""Strict origin parsing shared by settings validation and request checks."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def _origin_from_url(value: str, *, allow_path: bool) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("Origin is invalid")
    if value == "null" or "*" in value:
        raise ValueError("Origin is invalid")

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        raise ValueError("Origin is invalid") from error

    scheme = parts.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or not parts.netloc
        or parts.hostname is None
        or parts.username is not None
        or parts.password is not None
        or parts.netloc.endswith(":")
        or (
            not allow_path
            and (parts.path or parts.query or parts.fragment or "?" in value or "#" in value)
        )
    ):
        raise ValueError("Origin is invalid")

    hostname = parts.hostname.lower()
    try:
        if ":" not in hostname:
            hostname = hostname.encode("idna").decode("ascii")
        else:
            hostname = ipaddress.IPv6Address(hostname).compressed
    except UnicodeError as error:
        raise ValueError("Origin is invalid") from error
    except ipaddress.AddressValueError as error:
        raise ValueError("Origin is invalid") from error
    if not hostname or any(character.isspace() for character in hostname):
        raise ValueError("Origin is invalid")

    if ":" in hostname:
        hostname = f"[{hostname}]"
    elif any(_HOST_LABEL.fullmatch(label) is None for label in hostname.split(".")):
        raise ValueError("Origin is invalid")
    default_port = 80 if scheme == "http" else 443
    port_suffix = f":{port}" if port is not None and port != default_port else ""
    return f"{scheme}://{hostname}{port_suffix}"


def normalize_origin(value: str) -> str:
    """Validate and canonicalize a bare HTTP(S) origin (no path or wildcard)."""

    return _origin_from_url(value, allow_path=False)


def origin_from_referer(value: str) -> str:
    """Extract an HTTP(S) Referer origin without prefix matching."""

    return _origin_from_url(value, allow_path=True)


def _single_raw_header(request, name: bytes) -> str | None:
    """Return one raw ASGI header value; reject duplicate security headers."""

    values = [
        value.decode("latin-1")
        for header_name, value in request.scope.get("headers", [])
        if header_name.lower() == name
    ]
    if len(values) > 1:
        raise ValueError("Duplicate request header")
    return values[0] if values else None


def is_trusted_request_origin(request, allowed_origins: list[str]) -> bool:
    """Accept exact Origin, or Referer only when Origin is absent.

    Duplicate Origin and Referer fields are rejected before applying precedence.
    """

    try:
        origin_header = _single_raw_header(request, b"origin")
        referer_header = _single_raw_header(request, b"referer")
    except (AttributeError, TypeError, ValueError):
        return False

    if origin_header is not None:
        try:
            return normalize_origin(origin_header) in allowed_origins
        except ValueError:
            return False

    if referer_header is None:
        return False
    try:
        return origin_from_referer(referer_header) in allowed_origins
    except ValueError:
        return False
