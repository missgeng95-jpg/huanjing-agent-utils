"""Bounded conversation index pages; cursors are locations, never authority.

This module does not query a database or establish a snapshot. Callers are
responsible for scoped queries and consistency between separate pages.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from .errors import GovernanceValidationError

PAGE_VERSION = "assistant.conversations.page.v1"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}\Z")
_FIELDS = {"v", "binding", "after", "issued_at", "expires_at"}
TTL_SECONDS = 900


class HistoryPageError(GovernanceValidationError):
    def __init__(self, *, expired: bool = False):
        self.code = "HISTORY_CURSOR_EXPIRED" if expired else "HISTORY_PAGE_INVALID"
        self.status_code = 409 if expired else 422
        super().__init__("对话分页已过期，请刷新列表。" if expired else "对话分页参数无法核对，请重新读取列表。")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def identifier(value: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or not ((empty and value == "") or _ID.fullmatch(value)):
        raise HistoryPageError()
    return value


def date_bound(value: str) -> str:
    if value == "":
        return ""
    if not isinstance(value, str) or len(value) > 64 or value != value.strip():
        raise HistoryPageError()
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError()
        return stamp.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        raise HistoryPageError() from None


def page_filters(filters: dict, *, page_size: int, date_from: str, date_to: str) -> dict:
    if type(page_size) is not int or page_size not in (20, 50, 100):
        raise HistoryPageError()
    if any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in filters["q"]):
        raise HistoryPageError()
    start, end = date_bound(date_from), date_bound(date_to)
    if start and end and start >= end:
        raise HistoryPageError()
    return {**filters, "limit": page_size, "date_from": start, "date_to": end}


def binding(owner_id: str, filters: dict) -> str:
    # Hashes bind a location to its scope, not grant access. SQL still uses owner.
    return hashlib.sha256(canonical({"owner": owner_id, "filters": filters})).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def decode(cursor: str, expected: str, now: int) -> dict | None:
    if cursor == "":
        return None
    if not isinstance(cursor, str) or len(cursor) > 2048 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HistoryPageError()
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        if len(raw) > 1536:
            raise ValueError()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if not isinstance(value, dict) or set(value) != _FIELDS or type(value["v"]) is not int or value["v"] != 1 or value["binding"] != expected:
            raise ValueError()
        after = value["after"]
        if not isinstance(after, dict) or set(after) != {"time", "id"}:
            raise ValueError()
        identifier(after["id"])
        if not isinstance(after["time"], str) or not after["time"] or len(after["time"]) > 64:
            raise ValueError()
        datetime.fromisoformat(after["time"].replace("Z", "+00:00"))
        issued, expires = value["issued_at"], value["expires_at"]
        if type(issued) is not int or type(expires) is not int or not 0 <= issued <= now or expires != issued + TTL_SECONDS:
            raise ValueError()
        if base64.urlsafe_b64encode(canonical(value)).decode("ascii").rstrip("=") != cursor:
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise HistoryPageError() from None
    if now >= expires:
        raise HistoryPageError(expired=True)
    return value


def encode(row: dict, filters: dict, expected: str, now: int, token: dict | None) -> str:
    field = "created_at" if filters["sort"].startswith("CREATED") else "updated_at"
    value = {"v": 1, "binding": expected, "after": {"time": row[field], "id": row["session_id"]},
             "issued_at": token["issued_at"] if token else now,
             "expires_at": token["expires_at"] if token else now + TTL_SECONDS}
    encoded = base64.urlsafe_b64encode(canonical(value)).decode("ascii").rstrip("=")
    decode(encoded, expected, now)  # Invalid stored identifiers/timestamps never enter a public cursor.
    return encoded
