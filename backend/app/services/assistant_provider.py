"""Opt-in local transport building block. Not composed into production startup.

Only explicitly approved literal loopback peers are supported; DNS and remote
hosts fail closed. No discovery, model pull, redirects, retries or fallback.
Actual-machine verification and trustworthy token counting are deployment gates.
"""
from dataclasses import dataclass
import ipaddress
from urllib.parse import urlsplit


from app.schemas.assistant import ProviderIdentity, ProviderKind, PersistedFailureCode


class ProviderConfigurationError(ValueError):
    def __init__(self):
        super().__init__('Local provider configuration is not approved.')


@dataclass(frozen=True)
class ApprovedLocalTarget:
    kind: ProviderKind
    model: str
    endpoint: str
    approved_peers: frozenset[tuple[str, int]]

    def __post_init__(self):
        try:
            parsed = urlsplit(self.endpoint)
            peer = ipaddress.ip_address(parsed.hostname or '')
            port = parsed.port
            if (self.kind not in {ProviderKind.OLLAMA, ProviderKind.LLAMA_CPP}
                or parsed.scheme != 'http' or not peer.is_loopback or port is None or port < 1
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path not in {'', '/'}
                or self.approved_peers != frozenset([(str(peer), port)])):
                raise ValueError()
            identity = ProviderIdentity(kind=self.kind, model=self.model)
            if identity.model != self.model:
                raise ValueError()
        except (ValueError, TypeError):
            raise ProviderConfigurationError() from None


class LocalSelectionProvider:
    """Configuration candidate ONLY, not an admitted execution transport.

    Installed httpcore closes connections inside unbounded cancellation shields.
    Its supported API supplies no hard-close acknowledgement. An outer timeout
    cannot fix that. No httpx client or transport is created or called here.
    """
    __slots__ = ('target', 'identity', '_transport', 'termination_complete')

    def __init__(self, target: ApprovedLocalTarget, *, transport=None):
        from threading import Event
        self.target = target
        self.identity = ProviderIdentity(kind=target.kind, model=target.model)
        self._transport = transport  # Refusal tests verify even this is never entered.
        self.termination_complete = Event()
        self.termination_complete.set()  # No transport task has ever been started.

    @property
    def supports_bounded_shutdown(self):
        return False

    async def select_claims(self, request: bytes, *, deadline_monotonic: float,
                            work_deadline_monotonic: float | None = None):
        # Preserve independent deadline arguments at the boundary without
        # presenting the installed transport as safe to dispatch.
        raise ProviderConfigurationError()
