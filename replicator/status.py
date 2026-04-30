"""Machine-readable CLI status helpers."""

from __future__ import annotations

import json
from typing import Any


OK = "REP_OK"
ERROR = "REP_ERROR"


def status_payload(
    *,
    code: str = OK,
    message: str,
    command: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "replicator.cli_status.v1",
        "status": "ok" if code == OK else "error",
        "code": code,
        "message": message,
        "command": command,
        "data": data or {},
    }


def print_json_status(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))

