import subprocess
import sys
from importlib.metadata import version as metadata_version

import markserv


def test_package_version_matches_distribution_metadata() -> None:
    assert markserv.__version__ == metadata_version("markserv")


def test_package_import_does_not_eagerly_import_cli() -> None:
    command = "import markserv, sys; print('markserv.cli' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", command], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "False"
