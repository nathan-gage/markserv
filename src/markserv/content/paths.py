from __future__ import annotations

from pathlib import Path, PurePosixPath

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".mkdn"}
DEFAULT_IGNORE_PATTERNS = [".git/"]
DIRECTORY_DEFAULT_BASENAMES = ("README", "readme", "index", "INDEX")
SAFE_ASSET_EXTENSIONS = {
    ".aac",
    ".apng",
    ".avif",
    ".bmp",
    ".bz2",
    ".csv",
    ".eot",
    ".flac",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".json",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".oga",
    ".ogg",
    ".ogv",
    ".otf",
    ".pdf",
    ".png",
    ".svg",
    ".tar",
    ".tgz",
    ".tsv",
    ".ttf",
    ".txt",
    ".wav",
    ".weba",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xml",
    ".xz",
    ".zip",
}
UNSAFE_ASSET_EXTENSIONS = {
    ".bat",
    ".cjs",
    ".cmd",
    ".com",
    ".crt",
    ".css",
    ".der",
    ".dll",
    ".dylib",
    ".exe",
    ".htm",
    ".html",
    ".jar",
    ".js",
    ".key",
    ".map",
    ".mjs",
    ".msi",
    ".p12",
    ".pem",
    ".pfx",
    ".ps1",
    ".sh",
    ".so",
    ".war",
    ".xhtml",
}
UNSAFE_ASSET_BASENAMES = {
    "authorized_keys",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "known_hosts",
}


class SitePathError(LookupError):
    pass


def humanize_name(stem: str) -> str:
    value = stem.replace("_", " ").replace("-", " ").strip()
    return value if value else stem


def is_markdown_path(path: Path) -> bool:
    return path.suffix.lower() in MARKDOWN_SUFFIXES


def is_safe_asset_path(rel_path: str) -> bool:
    normalized_path = normalize_rel_path(rel_path)
    parts = PurePosixPath(normalized_path).parts
    if not parts or any(part.startswith(".") for part in parts):
        return False

    filename = parts[-1].lower()
    if filename in UNSAFE_ASSET_BASENAMES or filename.startswith(".env"):
        return False

    suffixes = {suffix.lower() for suffix in Path(filename).suffixes}
    if suffixes & UNSAFE_ASSET_EXTENSIONS:
        return False
    return bool(suffixes & SAFE_ASSET_EXTENSIONS)


def normalize_rel_path(raw_path: str) -> str:
    cleaned = raw_path.replace("\\", "/").strip("/")
    parts: list[str] = []
    for part in PurePosixPath(cleaned).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise SitePathError("Not found")
        parts.append(part)
    return "/".join(parts)


def resolve_rooted_path(root_dir: Path, rel_path: str) -> Path:
    root = root_dir.resolve()
    candidate = root.joinpath(*([part for part in rel_path.split("/") if part] or ["."]))
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SitePathError("Not found") from exc
    return resolved


def choose_root_for_file(file_path: Path, cwd: Path) -> Path:
    if not file_path.is_relative_to(cwd):
        return file_path.parent

    chosen = file_path.parent
    current = file_path.parent
    while True:
        if (current / ".git").exists() or (current / ".gitignore").exists():
            chosen = current
        if current == cwd:
            return chosen
        current = current.parent
