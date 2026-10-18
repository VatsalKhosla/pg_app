"""Toolchain smoke test: the ``app`` package is installed from ``src/`` and importable."""

from pathlib import Path

import app


def test_app_package_is_installed_from_src() -> None:
    assert app.__file__ is not None
    package_dir = Path(app.__file__).parent
    assert (package_dir.parent.name, package_dir.name) == ("src", "app")
