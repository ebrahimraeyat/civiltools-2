"""
Hardware fingerprint generation for machine-locked licensing.

Generates a deterministic machine ID from:
- CPU info (processor name)
- Disk serial number (system drive)
- Hostname
- MAC address of first NIC

The fingerprint is a SHA-256 hash, truncated to 16 hex chars.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import uuid


def _safe_run(cmd: list[str]) -> str:
    """Run a command, return stdout or empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _get_cpu_id() -> str:
    """Get CPU model string."""
    if platform.system() == "Windows":
        return _safe_run(
            ["wmic", "cpu", "get", "ProcessorId", "/value"]
        )
    return platform.processor()


def _get_disk_serial() -> str:
    """Get system drive serial number (Windows)."""
    if platform.system() == "Windows":
        out = _safe_run(
            ["wmic", "diskdrive", "get", "SerialNumber", "/value"]
        )
        # Parse first non-empty serial
        for line in out.splitlines():
            if "=" in line:
                val = line.split("=", 1)[1].strip()
                if val:
                    return val
    return ""


def _get_mac() -> str:
    """Get primary MAC address."""
    mac = uuid.getnode()
    return f"{mac:012x}"


def get_machine_id() -> str:
    """Generate a deterministic hardware fingerprint.

    Returns a 16-character hex string that is stable across reboots
    but unique per physical machine.
    """
    parts = [
        platform.node(),       # hostname
        _get_cpu_id(),
        _get_disk_serial(),
        _get_mac(),
    ]
    raw = "|".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:16].upper()


def get_machine_id_verbose() -> dict[str, str]:
    """Return machine ID with component details (for debugging)."""
    return {
        "hostname": platform.node(),
        "cpu": _get_cpu_id(),
        "disk": _get_disk_serial(),
        "mac": _get_mac(),
        "machine_id": get_machine_id(),
    }


if __name__ == "__main__":
    info = get_machine_id_verbose()
    for k, v in info.items():
        print(f"  {k}: {v}")
