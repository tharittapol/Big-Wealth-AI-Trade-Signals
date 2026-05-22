"""GCP Secret Manager wrapper with local env var fallback."""
from __future__ import annotations

import os
from functools import lru_cache

import structlog

logger = structlog.get_logger()


@lru_cache(maxsize=None)
def get_secret(name: str) -> str:
    """Return secret value.

    Checks the environment first (works with .env locally), then falls back
    to GCP Secret Manager when running on Cloud Run.
    """
    val = os.getenv(name)
    if val:
        return val

    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        raise RuntimeError(
            f"Secret '{name}' not found in environment and GCP_PROJECT_ID is not set"
        )

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    path = f"projects/{project_id}/secrets/{name}/versions/latest"
    response = client.access_secret_version(request={"name": path})
    value = response.payload.data.decode("UTF-8").strip()
    logger.info("Loaded secret from Secret Manager", name=name)
    return value
