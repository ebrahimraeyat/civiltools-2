"""
Tests for the licensing system.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from civiltools.licensing.machine_id import get_machine_id
from civiltools.licensing.license_manager import (
    LicenseManager, generate_serial, verify_serial,
)


class TestMachineId:
    def test_returns_hex_string(self):
        mid = get_machine_id()
        assert isinstance(mid, str)
        assert len(mid) == 16
        # Should be valid hex
        int(mid, 16)

    def test_deterministic(self):
        """Same machine should produce same ID."""
        assert get_machine_id() == get_machine_id()


class TestSerialGeneration:
    def test_format(self):
        serial = generate_serial("ABCDEF1234567890")
        assert serial.startswith("CT-")
        parts = serial.split("-")
        assert len(parts) == 5
        assert all(len(p) == 5 for p in parts[1:])

    def test_verification(self):
        mid = "ABCDEF1234567890"
        serial = generate_serial(mid)
        assert verify_serial(serial, mid)

    def test_wrong_machine(self):
        serial = generate_serial("AAAA111122223333")
        assert not verify_serial(serial, "BBBB444455556666")


class TestLicenseManager:
    def test_trial_on_fresh_install(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = LicenseManager(data_dir=Path(tmpdir))
            info = mgr.get_info()
            assert info.is_trial
            assert info.days_remaining > 0
            assert info.is_licensed  # trial counts as licensed (app runs)

    def test_activation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = LicenseManager(data_dir=Path(tmpdir))
            mid = mgr.get_info().machine_id
            serial = generate_serial(mid)
            assert mgr.activate(serial)
            info = mgr.get_info()
            assert info.is_licensed
            assert not info.is_trial

    def test_wrong_serial_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = LicenseManager(data_dir=Path(tmpdir))
            assert not mgr.activate("CT-XXXXX-XXXXX-XXXXX-XXXXX")
