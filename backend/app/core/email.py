"""Shared email normalization and validation for registration and login."""

from __future__ import annotations

import re

_LOCAL_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_DOMAIN_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL_PATTERN = re.compile(
    rf"(?P<local>{_LOCAL_ATOM}(?:\.{_LOCAL_ATOM})*)@"
    rf"(?P<domain>(?:{_DOMAIN_LABEL}\.)+{_DOMAIN_LABEL})\Z"
)


def normalize_email(email: str) -> str:
    """Trim, lowercase, and validate an email using the account policy."""

    if not isinstance(email, str):
        raise ValueError("Email address is invalid")
    normalized = email.strip().lower()
    match = _EMAIL_PATTERN.fullmatch(normalized)
    if (
        not normalized
        or len(normalized) > 320
        or match is None
        or len(match.group("local")) > 64
        or any(len(label) > 63 for label in match.group("domain").split("."))
    ):
        raise ValueError("Email address is invalid")
    return normalized
