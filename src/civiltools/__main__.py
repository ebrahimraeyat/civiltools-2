"""Entry point: ``python -m civiltools`` or ``civiltools`` console script."""

import sys


def main():
    # Licensing check must happen before heavy imports
    from civiltools.licensing.license_manager import LicenseManager

    mgr = LicenseManager()
    if not mgr.check_or_prompt():
        sys.exit(1)

    # Now launch the GUI
    from civiltools.app import run_app

    sys.exit(run_app())


if __name__ == "__main__":
    main()
