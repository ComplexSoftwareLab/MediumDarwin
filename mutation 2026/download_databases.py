#!/usr/bin/env python3
"""Download Mutation 2026 SQLite databases from Google Drive."""

from __future__ import annotations

import argparse
import errno
import json
import shutil
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

DRIVE_FOLDER_ID = "1abTVxYywqI2__pb5ImDl6FvpSQcKZSQn"
DRIVE_FOLDER_URL = f"https://drive.google.com/drive/folders/{DRIVE_FOLDER_ID}"
STAGING_DIR_PREFIX = "mutation2026_drive_"
# Rough headroom beyond known file sizes (metadata, partial files, OS).
DISK_HEADROOM_BYTES = 512 * 1024 * 1024


def load_config(root: Path) -> dict:
    return json.loads((root / "projects.json").read_text(encoding="utf-8"))


def required_paths(config: dict, projects: Sequence[str], root: Path) -> List[Path]:
    paths: List[Path] = []
    for project in projects:
        if project not in config:
            raise SystemExit(f"Unknown project: {project}")
        cfg = config[project]
        paths.append(root / cfg["fom_database"])
        paths.extend(root / rel for rel in cfg["hom_databases"])
    return paths


def missing_paths(paths: Iterable[Path]) -> List[Path]:
    return [path for path in paths if not path.is_file() or path.stat().st_size == 0]


def ensure_gdown():
    try:
        import gdown  # noqa: F401
    except ImportError:
        print("Installing gdown ...", file=sys.stderr)
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown"])
    import gdown

    return gdown


def normalize_drive_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def build_drive_index(entries) -> dict[str, object]:
    index: dict[str, object] = {}
    for entry in entries:
        path = normalize_drive_path(entry.path)
        index[path] = entry
        parts = path.split("/")
        if len(parts) > 1:
            index["/".join(parts[1:])] = entry
        if len(parts) > 2:
            index["/".join(parts[-2:])] = entry
    return index


def resolve_drive_entry(index: dict[str, object], rel_posix: str):
    if rel_posix in index:
        return index[rel_posix]
    suffix_matches = [key for key in index if key.endswith(rel_posix)]
    if len(suffix_matches) == 1:
        return index[suffix_matches[0]]
    if len(suffix_matches) > 1:
        exact = [key for key in suffix_matches if key.split("/")[-2:] == rel_posix.split("/")[-2:]]
        if len(exact) == 1:
            return index[exact[0]]
    raise SystemExit(
        f"Database not found on Google Drive: {rel_posix}\n"
        f"Folder: {DRIVE_FOLDER_URL}\n"
        "The upload may still be in progress."
    )


def entry_size_bytes(entry) -> int:
    for attr in ("size", "file_size"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return 0


def format_bytes(num: int) -> str:
    if num >= 1024**3:
        return f"{num / 1024**3:.1f} GB"
    if num >= 1024**2:
        return f"{num / 1024**2:.1f} MB"
    if num >= 1024:
        return f"{num / 1024:.1f} KB"
    return f"{num} B"


def disk_free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def cleanup_partial_files(dest: Path) -> None:
    for pattern in (f"{dest.name}*.part", f"{dest.name}.part"):
        for partial in dest.parent.glob(pattern):
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
    if dest.is_file() and dest.stat().st_size == 0:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_stale_staging_dirs(root: Path) -> None:
    for staging in root.glob(f"{STAGING_DIR_PREFIX}*"):
        if not staging.is_dir():
            continue
        try:
            shutil.rmtree(staging, ignore_errors=True)
            print(f"Removed stale staging directory: {staging.name}")
        except OSError as exc:
            print(
                f"Could not remove stale staging directory {staging.name}: {exc}",
                file=sys.stderr,
            )


def raise_disk_full(dest: Path, exc: OSError) -> None:
    drive = dest.anchor or str(dest.drive) or str(dest.parent)
    free = disk_free_bytes(dest.parent)
    cleanup_partial_files(dest)
    raise SystemExit(
        "Not enough free disk space to download databases.\n"
        f"  Destination drive: {drive}\n"
        f"  Free space now: {format_bytes(free)}\n"
        f"  Failed file: {dest}\n"
        "The full dataset is ~25 GB. Free space on this drive, delete any "
        f"'{STAGING_DIR_PREFIX}*' folders under mutation 2026/, then re-run.\n"
        "You can also download from Zenodo and copy the project folders manually "
        "(see README)."
    ) from exc


def ensure_disk_space(dest: Path, required_bytes: int) -> None:
    if required_bytes <= 0:
        return
    needed = required_bytes + DISK_HEADROOM_BYTES
    free = disk_free_bytes(dest.parent)
    if free < needed:
        raise SystemExit(
            "Not enough free disk space to download databases.\n"
            f"  Drive: {dest.anchor or dest.parent}\n"
            f"  Free: {format_bytes(free)}\n"
            f"  Needed for next file: {format_bytes(needed)} (incl. headroom)\n"
            "Free space or use Zenodo (see README), then re-run."
        )


def download_selected_files(
    gdown,
    *,
    root: Path,
    missing: Sequence[Path],
    quiet: bool,
) -> None:
    entries = gdown.download_folder(
        url=DRIVE_FOLDER_URL,
        skip_download=True,
        quiet=quiet,
    )
    index = build_drive_index(entries)

    total_size = sum(entry_size_bytes(resolve_drive_entry(index, p.relative_to(root).as_posix())) for p in missing)
    if total_size:
        ensure_disk_space(root, total_size + DISK_HEADROOM_BYTES)
        print(f"Estimated download size: {format_bytes(total_size)}")

    for dest in sorted(missing, key=lambda p: p.as_posix()):
        rel_posix = dest.relative_to(root).as_posix()
        entry = resolve_drive_entry(index, rel_posix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cleanup_partial_files(dest)
        file_size = entry_size_bytes(entry)
        if file_size:
            ensure_disk_space(dest, file_size)
        print(f"Downloading {rel_posix} ...")
        try:
            gdown.download(
                id=entry.id,
                output=str(dest),
                quiet=quiet,
                resume=True,
            )
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise_disk_full(dest, exc)
            cleanup_partial_files(dest)
            raise
        except Exception:
            cleanup_partial_files(dest)
            raise


def download_databases(
    root: Path,
    projects: Optional[Sequence[str]] = None,
    *,
    force: bool = False,
    quiet: bool = False,
) -> None:
    cleanup_stale_staging_dirs(root)

    config = load_config(root)
    selected = list(projects or config.keys())
    required = required_paths(config, selected, root)
    missing = required if force else missing_paths(required)

    if not missing:
        print("All required databases are already present.")
        return

    free = disk_free_bytes(root)
    print(
        f"{'Re-downloading' if force else 'Downloading'} "
        f"{len(missing)} database file(s) from Google Drive ..."
    )
    print(f"Source: {DRIVE_FOLDER_URL}")
    print(f"Free disk space on destination drive: {format_bytes(free)}")

    gdown = ensure_gdown()
    download_selected_files(gdown, root=root, missing=missing, quiet=quiet)

    still_missing = missing_paths(missing)
    if still_missing:
        rels = "\n".join(f"  - {path.relative_to(root)}" for path in still_missing)
        raise SystemExit(f"Some databases are still missing after download:\n{rels}")

    print("Database download complete.")


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Download Mutation 2026 SQLite databases from Google Drive."
    )
    parser.add_argument(
        "--projects",
        nargs="*",
        default=None,
        help="Project names to download (default: all in projects.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download databases even if they already exist locally",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    download_databases(
        root,
        args.projects,
        force=args.force,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
