"""Factory for the boto3 Glue client.

Kept tiny and centralized so tests can patch a single place and all catalog
modules share consistent region/config.
"""
from __future__ import annotations

import boto3

from config import REGION


def glue_client(region: str | None = None):
    """Return a boto3 Glue client for the given (or default) region."""
    return boto3.client("glue", region_name=region or REGION)
