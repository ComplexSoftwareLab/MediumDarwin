#!/usr/bin/env python3
"""Run BSim analysis for one or all projects defined in projects.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from cluster_foms_by_bsim import (
    TQDM_AVAILABLE,
    configure_stdio,
    open_log_file,
    progress_bars_enabled,
    run_analysis,
)

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None  # type: ignore


def _log_line(handle: Optional[TextIO], message: str, *, to_console: bool = True) -> None:
    if to_console:
        print(message, flush=True)
    if handle is not None:
        handle.write(message + "\n")
        handle.flush()


def main() -> None:
    configure_stdio()

    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Run BSim analysis for Mutation 2026 projects.")
    parser.add_argument(
        "--projects",
        nargs="*",
        default=None,
        help="Project names to analyse (default: all in projects.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "results",
        help="Output directory (default: results/)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Append plain UTF-8 stage messages to this log file (no tqdm bar spam)",
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Override HOM cache directory (default: per-project hom_cache under output-dir)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable HOM result caching",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear HOM cache before each project run",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    config = json.loads((root / "projects.json").read_text(encoding="utf-8"))
    selected = args.projects or list(config.keys())
    args.output_dir.mkdir(parents=True, exist_ok=True)

    log_handle: Optional[TextIO] = None
    if args.log_file is not None:
        log_handle = open_log_file(args.log_file)
        log_handle.write(
            f"\n=== BSim pipeline started {datetime.now():%Y-%m-%d %H:%M:%S} ===\n"
        )
        log_handle.flush()

    try:
        _log_line(
            log_handle,
            f"\n{'=' * 72}\n"
            f"BSim pipeline - {len(selected)} project(s): {', '.join(selected)}\n"
            f"{'=' * 72}",
        )

        project_iter = selected
        if progress_bars_enabled() and tqdm is not None:
            project_iter = tqdm(
                selected,
                desc="Projects",
                unit="project",
                dynamic_ncols=True,
                file=sys.stdout,
                ascii=False,
            )

        for index, project in enumerate(project_iter, start=1):
            if project not in config:
                raise SystemExit(f"Unknown project: {project}")
            cfg = config[project]
            fom_db = root / cfg["fom_database"]
            hom_dbs = [root / p for p in cfg["hom_databases"]]
            for db in [fom_db, *hom_dbs]:
                if not db.exists():
                    raise SystemExit(f"Missing database: {db}")

            run_analysis(
                project_name=project,
                fom_database=fom_db,
                hom_databases=hom_dbs,
                output_dir=args.output_dir,
                threshold=float(cfg.get("threshold", 0)),
                workers=args.workers,
                verbose=args.verbose,
                cache_dir=args.cache_dir,
                use_cache=not args.no_cache,
                clear_cache=args.clear_cache,
                project_index=index,
                project_total=len(selected),
                log_file=log_handle,
            )

        _log_line(
            log_handle,
            f"\nPipeline complete - {len(selected)} project(s) finished.",
        )
    finally:
        if log_handle is not None:
            log_handle.write(
                f"=== BSim pipeline finished {datetime.now():%Y-%m-%d %H:%M:%S} ===\n"
            )
            log_handle.close()


if __name__ == "__main__":
    main()
