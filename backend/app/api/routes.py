"""Top-level API routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Report that the API process is responding."""

    return {"status": "ok"}
