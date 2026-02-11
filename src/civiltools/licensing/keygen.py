"""
Admin utility — generate serial keys for customers.

Usage:
    python -m civiltools.licensing.keygen <machine_id>

Example:
    python -m civiltools.licensing.keygen A1B2C3D4E5F6G7H8
    → CT-3F2A1-B9C8D-7E6F5-A4B3C

Keep this file OUT of end-user distributions.
In Nuitka builds, exclude this module with:
    --nofollow-import-to=civiltools.licensing.keygen
"""

from __future__ import annotations

import sys

from civiltools.licensing.license_manager import generate_serial
from civiltools.licensing.machine_id import get_machine_id


def main():
    if len(sys.argv) < 2:
        # No argument — generate for this machine (for testing)
        mid = get_machine_id()
        print(f"Machine ID : {mid}")
        serial = generate_serial(mid)
        print(f"Serial Key : {serial}")
        return

    mid = sys.argv[1].strip().upper()
    serial = generate_serial(mid)
    print(f"Machine ID : {mid}")
    print(f"Serial Key : {serial}")


if __name__ == "__main__":
    main()
