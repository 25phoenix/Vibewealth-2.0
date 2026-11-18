"""Bounded single-worker assistant read/write limits, without queues or I/O."""

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from app.schemas.assistant import MAX_LIMITER_BUCKETS, READS_PER_MINUTE, WRITES_PER_MINUTE


@dataclass
class _UserWindow:
    reads: deque = field(default_factory=deque)
    writes: deque = field(default_factory=deque)


class AssistantRateLimiter:
    def __init__(self, *, clock=time.monotonic, max_users=MAX_LIMITER_BUCKETS):
        if not 1 <= max_users <= MAX_LIMITER_BUCKETS:
            raise ValueError("Invalid assistant limiter bound")
        self._clock = clock
        self._max_users = max_users
        self._users = {}
        self._lock = threading.Lock()

    def check(self, user_id, *, write=False):
        """Return integer Retry-After on refusal, or consume one admission."""
        with self._lock:
            now = self._clock()
            expired = []
            for owner, window in self._users.items():
                for events in (window.reads, window.writes):
                    while events and events[0] <= now - 60:
                        events.popleft()
                if not window.reads and not window.writes:
                    expired.append(owner)
            for owner in expired:
                del self._users[owner]
            if user_id not in self._users:
                if len(self._users) >= self._max_users:
                    earliest = min(events[0] for window in self._users.values()
                                   for events in (window.reads, window.writes) if events)
                    return max(1, math.ceil(earliest + 60 - now))
                self._users[user_id] = _UserWindow()
            window = self._users[user_id]
            events = window.writes if write else window.reads
            if len(events) >= (WRITES_PER_MINUTE if write else READS_PER_MINUTE):
                return max(1, math.ceil(events[0] + 60 - now))
            events.append(now)
            return None
