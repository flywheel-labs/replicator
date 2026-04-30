"""Readiness checks for app integrations."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from replicator import __version__
from replicator.adapters import PROVIDERS


def check_output_directory(path: Path) -> dict[str, object]:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".replicator-write-test"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        writable = True
        message = "Output directory is writable."
    except OSError as exc:
        writable = False
        message = f"Output directory is not writable: {exc}"
    return {
        "path": str(path),
        "writable": writable,
        "message": message,
    }


def detected_provider_roots() -> dict[str, list[str]]:
    detected: dict[str, list[str]] = {}
    for provider, spec in PROVIDERS.items():
        roots = []
        for raw_path in spec.paths:
            path = Path(raw_path).expanduser()
            if path.exists():
                roots.append(str(path))
        detected[provider] = roots
    return detected


def doctor_payload(output_dir: Path, fixture_root: Path | None = None) -> dict[str, object]:
    fixture = fixture_root or Path("tests/fixtures/home")
    checks = {
        "python": {
            "version": sys.version.split()[0],
            "major": sys.version_info.major,
            "minor": sys.version_info.minor,
            "ok": sys.version_info >= (3, 10),
        },
        "replicator": {
            "version": __version__,
        },
        "git": {
            "available": shutil.which("git") is not None,
        },
        "output_directory": check_output_directory(output_dir),
        "fixtures": {
            "path": str(fixture),
            "available": fixture.exists(),
        },
        "providers": detected_provider_roots(),
    }
    ok = (
        bool(checks["python"]["ok"])
        and bool(checks["git"]["available"])
        and bool(checks["output_directory"]["writable"])
    )
    return {
        "schema": "replicator.doctor.v1",
        "ok": ok,
        "checks": checks,
    }


def render_doctor_report(payload: dict[str, object]) -> str:
    checks = payload["checks"]
    lines = [
        "# Replicator Doctor",
        "",
        f"- Overall OK: `{str(payload['ok']).lower()}`",
        f"- Replicator version: `{checks['replicator']['version']}`",
        f"- Python version: `{checks['python']['version']}`",
        f"- Git available: `{str(checks['git']['available']).lower()}`",
        f"- Output directory writable: `{str(checks['output_directory']['writable']).lower()}`",
        f"- Fixtures available: `{str(checks['fixtures']['available']).lower()}`",
        "",
        "## Provider Roots",
        "",
    ]
    for provider, roots in checks["providers"].items():
        if roots:
            lines.append(f"- `{provider}`: {', '.join(f'`{root}`' for root in roots)}")
        else:
            lines.append(f"- `{provider}`: none detected")
    lines.append("")
    return "\n".join(lines)

