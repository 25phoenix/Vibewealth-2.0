"""Fail-closed preparation capability boundary.

No installed startup/serialization/reap primitive proves termination within the
original absolute deadline. SIGKILL plus shielded process.wait() is NOT a
bounded-reap guarantee. No thread, process, serialization callback or counter is
started, even in test mode. A future owned implementation requires review.
"""
from dataclasses import dataclass

from app.schemas.assistant import PersistedFailureCode
from app.services.assistant_contracts import GroundingContractViolation


@dataclass(frozen=True)
class TestProcessCounter:
    """Legacy test configuration, deliberately unsupported like all counters."""
    __test__ = False
    paused: bool = False
    count: int = 100

    def __init_subclass__(cls, **kwargs):
        raise TypeError("Test counter cannot be subclassed")


def counter_supported(counter, *, test_environment=False):
    return False


class PreparationRun:
    """Refusal only: owns no worker and accepts no execution capability."""
    async def run(self, wire, *, deadline):
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT)


async def prepare_selection_async(context, *, content, history, counter, deadline,
                                  test_environment=False, observation=None):
    # Refuse BEFORE inspecting/serializing sensitive input, queueing a thread,
    # creating a child or invoking an observer. A timeout cannot make unsupported
    # boundaries safe. Ordinary admission independently rejects this capability.
    raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT)
