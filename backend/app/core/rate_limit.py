"""Bounded, process-local rate limiting for public authentication endpoints."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, Request, status

from app.core.config import Settings
from app.core.email import normalize_email


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class InMemoryAuthRateLimiter:
    """Thread-safe token buckets with fixed-size IP and identity caches."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_ip_buckets: int = 4096,
        max_identity_buckets: int = 4096,
    ) -> None:
        if max_ip_buckets < 1 or max_identity_buckets < 1:
            raise ValueError("Rate limiter bucket capacities must be positive")
        self._clock = clock
        self._secret = secrets.token_bytes(32)
        self._max_ip_buckets = max_ip_buckets
        self._max_identity_buckets = max_identity_buckets
        self._ip_buckets: OrderedDict[bytes, _Bucket] = OrderedDict()
        self._identity_buckets: OrderedDict[bytes, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def check(
        self,
        *,
        operation: str,
        client_ip: str,
        identity: str,
        ip_limit: int,
        identity_limit: int,
        window_seconds: int,
    ) -> int | None:
        """Consume both limits atomically; return Retry-After on rejection."""

        ip_key = self._digest(f"{operation}:ip:{client_ip}")
        identity_key = self._digest(
            f"{operation}:identity:{client_ip}:{_identity_key(identity)}"
        )
        with self._lock:
            now = self._clock()
            ip_bucket = self._get_bucket(
                self._ip_buckets, ip_key, ip_limit, now, self._max_ip_buckets
            )
            identity_bucket = self._get_bucket(
                self._identity_buckets,
                identity_key,
                identity_limit,
                now,
                self._max_identity_buckets,
            )
            ip_tokens = _refill(ip_bucket, ip_limit, window_seconds, now)
            identity_tokens = _refill(
                identity_bucket, identity_limit, window_seconds, now
            )

            if ip_tokens < 1 or identity_tokens < 1:
                waits = []
                if ip_tokens < 1:
                    waits.append((1 - ip_tokens) * window_seconds / ip_limit)
                if identity_tokens < 1:
                    waits.append((1 - identity_tokens) * window_seconds / identity_limit)
                return max(1, math.ceil(max(waits)))

            ip_bucket.tokens = ip_tokens - 1
            identity_bucket.tokens = identity_tokens - 1
            return None

    def _digest(self, value: str) -> bytes:
        return hmac.digest(self._secret, value.encode("utf-8"), hashlib.sha256)

    @staticmethod
    def _get_bucket(
        buckets: OrderedDict[bytes, _Bucket],
        key: bytes,
        capacity: int,
        now: float,
        max_entries: int,
    ) -> _Bucket:
        bucket = buckets.get(key)
        if bucket is None:
            if len(buckets) >= max_entries:
                buckets.popitem(last=False)
            bucket = _Bucket(tokens=float(capacity), updated_at=now)
            buckets[key] = bucket
        else:
            buckets.move_to_end(key)
        return bucket


def enforce_auth_rate_limit(
    request: Request,
    settings: Settings,
    *,
    operation: str,
    identity: str,
) -> None:
    """Apply configured IP and per-IP identity limits to an auth request."""

    client_ip = _client_ip(request)
    if operation == "login":
        ip_limit = settings.auth_login_ip_limit
        identity_limit = settings.auth_login_identity_limit
        window_seconds = settings.auth_login_window_seconds
    elif operation == "register":
        ip_limit = settings.auth_registration_ip_limit
        identity_limit = settings.auth_registration_identity_limit
        window_seconds = settings.auth_registration_window_seconds
    else:
        raise ValueError(f"Unsupported authentication rate limit operation: {operation}")

    limiter: InMemoryAuthRateLimiter = request.app.state.auth_rate_limiter
    retry_after = limiter.check(
        operation=operation,
        client_ip=client_ip,
        identity=identity,
        ip_limit=ip_limit,
        identity_limit=identity_limit,
        window_seconds=window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _client_ip(request: Request) -> str:
    """Use only the ASGI peer address; invalid or missing peers share a safe bucket."""

    host = request.client.host if request.client is not None else None
    try:
        return ipaddress.ip_address(host or "").compressed
    except ValueError:
        return "unknown"


def _identity_key(identity: str) -> str:
    """Normalize valid emails and bound malformed input before hashing it."""

    try:
        return normalize_email(identity)
    except ValueError:
        return "invalid:" + identity[:320].strip().casefold()


def _refill(bucket: _Bucket, capacity: int, window_seconds: int, now: float) -> float:
    elapsed = max(0.0, now - bucket.updated_at)
    bucket.tokens = min(capacity, bucket.tokens + elapsed * capacity / window_seconds)
    bucket.updated_at = now
    return bucket.tokens
