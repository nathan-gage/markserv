from __future__ import annotations

import struct
import zlib
from pathlib import Path

from fastapi.testclient import TestClient

from markserv.app import build_config, create_app
from markserv.icons import generate_favicon


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_generate_favicon_returns_valid_png() -> None:
    png = generate_favicon("# Hello\nSome content.")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # IHDR chunk should specify 48x48 RGBA
    assert png[12:16] == b"IHDR"
    width, height, bit_depth, color_type = struct.unpack(">IIBB", png[16:26])
    assert (width, height) == (48, 48)
    assert bit_depth == 8
    assert color_type == 6  # RGBA


def test_generate_favicon_is_deterministic() -> None:
    a = generate_favicon("# Test content")
    b = generate_favicon("# Test content")
    assert a == b


def test_generate_favicon_varies_by_content() -> None:
    a = generate_favicon("# Page A")
    b = generate_favicon("# Page B")
    assert a != b


def test_generate_favicon_custom_resolution() -> None:
    png = generate_favicon("# Small", res=32, n_points=50_000)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (32, 32)


def test_generate_favicon_handles_empty_content() -> None:
    png = generate_favicon("")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_favicon_has_transparency() -> None:
    png = generate_favicon("# Transparent test")
    # Find IDAT chunk and decompress
    pos = 8
    idat_data = b""
    while pos < len(png):
        chunk_len = struct.unpack(">I", png[pos : pos + 4])[0]
        chunk_type = png[pos + 4 : pos + 8]
        if chunk_type == b"IDAT":
            idat_data += png[pos + 8 : pos + 8 + chunk_len]
        pos += 12 + chunk_len

    raw = zlib.decompress(idat_data)
    # Each row: 1 filter byte + 48 * 4 (RGBA) bytes = 193 bytes
    row_size = 1 + 48 * 4
    # Check that some pixels have alpha=0 (transparent background)
    transparent_count = 0
    for row_idx in range(48):
        row_start = row_idx * row_size + 1  # skip filter byte
        for px in range(48):
            offset = row_start + px * 4
            alpha = raw[offset + 3]
            if alpha == 0:
                transparent_count += 1

    assert transparent_count > 0, "Expected some transparent pixels"


def test_icon_route_serves_png(tmp_path: Path) -> None:
    write_text(tmp_path / "README.md", "# Hello\nWorld.")
    config = build_config(tmp_path)

    with TestClient(create_app(config)) as client:
        response = client.get("/icons/docs/README.md")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_icon_route_returns_404_for_missing_file(tmp_path: Path) -> None:
    write_text(tmp_path / "README.md", "# Hello")
    config = build_config(tmp_path)

    with TestClient(create_app(config)) as client:
        response = client.get("/icons/docs/nonexistent.md")
        assert response.status_code == 404


def test_icon_route_caches_result(tmp_path: Path) -> None:
    write_text(tmp_path / "README.md", "# Hello\nCaching test.")
    config = build_config(tmp_path)

    with TestClient(create_app(config)) as client:
        r1 = client.get("/icons/docs/README.md")
        r2 = client.get("/icons/docs/README.md")
        assert r1.content == r2.content


def test_page_includes_favicon_link(tmp_path: Path) -> None:
    write_text(tmp_path / "README.md", "# Hello")
    config = build_config(tmp_path)

    with TestClient(create_app(config)) as client:
        response = client.get("/docs/README.md")
        assert 'href="/icons/docs/README.md"' in response.text
        assert 'rel="icon"' in response.text
