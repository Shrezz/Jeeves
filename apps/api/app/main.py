"""Backend application entry point; claim workflow routes are added by the team."""

from fastapi import FastAPI

app = FastAPI(title="Claim Companion API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Basic process health endpoint."""
    return {"status": "ok"}
