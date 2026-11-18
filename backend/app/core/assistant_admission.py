"""Single-worker, non-queuing generation quota and capacity ownership."""

import math
import threading
import time
from dataclasses import dataclass

from app.schemas.assistant import (
    GENERATION_STARTS_PER_MINUTE, GLOBAL_PROVIDER_CAPACITY, MAX_LIMITER_BUCKETS,
    USER_PROVIDER_CAPACITY,
)


@dataclass(eq=False)
class GenerationTicket:
    admission: object
    owner: object
    timestamp: float
    started: bool = False
    capacity: bool = False
    closed: bool = False

    def acquire_capacity(self):
        admission = self.admission
        with admission._lock:
            if self.closed or self.capacity:
                raise RuntimeError("Invalid capacity ownership")
            if (len(admission._active) >= GLOBAL_PROVIDER_CAPACITY or
                    sum(ticket.owner == self.owner for ticket in admission._active) >= USER_PROVIDER_CAPACITY):
                return False
            admission._active.add(self)
            self.capacity = True
            return True

    def start(self):
        with self.admission._lock:
            if self.closed or not self.capacity or self.started:
                raise RuntimeError("Invalid generation ownership")
            self.timestamp = self.admission._clock()
            self.started = True

    def close(self):
        with self.admission._lock:
            if self.closed:
                raise RuntimeError("Generation ticket released twice")
            self.closed = True
            self.admission._active.discard(self)
            if not self.started:
                self.admission._events[self.owner].remove(self)


class AssistantAdmission:
    """Provisional quota counts until refunded or converted to a real start.

    No database work, await, or wait for capacity happens under this lock.
    Unclosed tickets are never expired/evicted while their request owns them.
    """

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._events = {}
        self._active = set()
        self._lock = threading.Lock()

    def reserve_quota(self, owner):
        with self._lock:
            now = self._clock()
            for user, events in list(self._events.items()):
                events[:] = [ticket for ticket in events if not ticket.closed or ticket.timestamp > now - 60]
                if not events:
                    del self._events[user]
            if owner not in self._events and len(self._events) >= MAX_LIMITER_BUCKETS:
                return None, 60
            events = self._events.setdefault(owner, [])
            if len(events) >= GENERATION_STARTS_PER_MINUTE:
                return None, max(1, math.ceil(min(ticket.timestamp for ticket in events) + 60 - now))
            ticket = GenerationTicket(self, owner, now)
            events.append(ticket)
            return ticket, None
