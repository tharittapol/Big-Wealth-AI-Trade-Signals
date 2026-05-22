"""Firestore client singleton."""
from __future__ import annotations

import os
from functools import lru_cache

from google.cloud import firestore


@lru_cache(maxsize=1)
def get_client() -> firestore.Client:
    """Return a cached Firestore client."""
    return firestore.Client(project=os.getenv("GCP_PROJECT_ID"))
