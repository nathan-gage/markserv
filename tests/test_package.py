from importlib.metadata import version as metadata_version

import markserv


def test_package_version_matches_distribution_metadata() -> None:
    assert markserv.__version__ == metadata_version("markserv")
