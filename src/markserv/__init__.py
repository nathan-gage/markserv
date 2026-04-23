from importlib.metadata import version as _metadata_version

__all__ = ["__version__", "main"]
__version__ = _metadata_version("markserv")


def main(argv: list[str] | None = None) -> None:
    from .cli import main as cli_main

    cli_main(argv)
