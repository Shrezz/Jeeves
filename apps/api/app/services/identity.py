"""Shared identity mapping; token/session verification belongs to the auth resolver."""

import re
from collections.abc import Mapping


def clerk_user_id(authenticated_subject: str) -> str:
    """Preserve the verified Clerk subject; shape validation is not authentication."""
    if not re.fullmatch(r"user_[A-Za-z0-9_]+", authenticated_subject):
        raise ValueError("Expected an authenticated Clerk user ID")
    return authenticated_subject


def owned_record_user_id(record: Mapping[str, object], authenticated_subject: str) -> str:
    """Map a UI database owner_id to agent/RAG user_id without inventing a UUID."""
    user_id = clerk_user_id(authenticated_subject)
    if record.get("owner_id") != user_id:
        raise PermissionError("Record not found")
    return user_id
