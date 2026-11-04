"""Rich-based console reporting for MediumDarwin.

Provides numbered pipeline stages, tqdm-style progress bars, and a live
mutant-execution dashboard. Progress bars are disabled when stdout is not a
TTY, when TERM is dumb, or when the user passes --quiet / --no-progress.
"""

from __future__ import annotations

import os
import sys
import time
import datetime
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table


def progress_bars_enabled(no_progress: bool = False, quiet: bool = False) -> bool:
    """Return True when live progress bars should be drawn."""
    if no_progress or quiet:
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except Exception:
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return True


def nCr(n: int, r: int) -> int:
    """Binomial coefficient without requiring math.comb (Python 3.8+)."""
    if r < 0 or r > n:
        return 0
    r = min(r, n - r)
    result = 1
    for i in range(r):
        result = result * (n - i) // (i + 1)
    return result


def combination_count(n: int, order: int) -> int:
    """Number of non-empty subsets of size 1..order from n items."""
    total = 0
    for r in range(1, order + 1):
        total += nCr(n, r)
    return total


def count_pipeline_stages(options, *, schemata: bool = True) -> int:
    """How many numbered stages this run will emit, based on CLI flags."""
    n = 0
    if schemata:
        if getattr(options, "isBuildActive", False) or getattr(options, "isMutationActive", False):
            n += 2  # discover sources + initial build
            if getattr(options, "isCoverageActive", False):
                n += 1
        if getattr(options, "isMutationActive", False):
            n += 2  # generate mutations + write to DB
        if getattr(options, "isBuildActive", False):
            n += 2  # execute mutants + write reports
        if getattr(options, "isSubsumptionActive", False):
            n += 1
        return n
    if getattr(options, "isMutationActive", False):
        n += 2  # discover + generate
    if getattr(options, "isBuildActive", False):
        n += 2  # initial build + execute
        if getattr(options, "isCoverageActive", False):
            n += 1
        n += 1  # reports
    if getattr(options, "isSubsumptionActive", False):
        n += 1
    return n


def _file_done_count(data: Dict[str, Any]) -> int:
    done = set()
    for key in (
        "survivedList",
        "killedList",
        "timeoutList",
        "nonCoveredList",
        "buildFailureList",
        "testFailureList",
    ):
        done.update(str(x) for x in data.get(key, []))
    return len(done)


def add_reporting_options(option_parser) -> None:
    """Add --debug / --quiet / --no-progress to an OptionParser."""
    option_parser.add_option(
        "--debug",
        action="store_true",
        dest="isDebugActive",
        default=False,
        help="Debug output (implies --verbose): AST dumps, node indices, mutation text, build/test commands.",
    )
    option_parser.add_option(
        "--quiet",
        action="store_true",
        dest="isQuiet",
        default=False,
        help="Errors and warnings only. Disables progress bars and the startup banner.",
    )
    option_parser.add_option(
        "--no-progress",
        action="store_true",
        dest="noProgress",
        default=False,
        help="Disable progress bars even in an interactive terminal.",
    )


def apply_verbosity_flags(options) -> None:
    """Resolve quiet/debug/verbose: quiet wins; debug implies verbose."""
    if getattr(options, "isQuiet", False):
        options.isVerboseActive = False
        options.isDebugActive = False
        return
    if getattr(options, "isDebugActive", False):
        options.isVerboseActive = True


class _NullTask:
    """Stand-in when progress bars are disabled."""

    def advance(self, n: int = 1, description: Optional[str] = None) -> None:
        return None

    def update(self, advance: int = 1) -> None:
        return None

    def set_status(self, text: str) -> None:
        return None


class ConsoleUI:
    """Single reporting surface for MediumDarwin CLI output."""

    QUIET = 0
    DEFAULT = 1
    VERBOSE = 2
    DEBUG = 3

    def __init__(
        self,
        *,
        quiet: bool = False,
        verbose: bool = False,
        debug: bool = False,
        no_progress: bool = False,
    ):
        if quiet:
            self.level = self.QUIET
        elif debug:
            self.level = self.DEBUG
        elif verbose:
            self.level = self.VERBOSE
        else:
            self.level = self.DEFAULT

        self.quiet = quiet
        self.verbose_enabled = (not quiet) and (verbose or debug)
        self.debug_enabled = (not quiet) and debug
        self.bars_enabled = progress_bars_enabled(
            no_progress=no_progress, quiet=quiet
        )
        self.console = Console(highlight=False, soft_wrap=True)
        self._stage_num = 0
        self._stage_total = 0

    @classmethod
    def from_options(cls, options) -> "ConsoleUI":
        return cls(
            quiet=bool(getattr(options, "isQuiet", False)),
            verbose=bool(getattr(options, "isVerboseActive", False)),
            debug=bool(getattr(options, "isDebugActive", False)),
            no_progress=bool(getattr(options, "noProgress", False)),
        )

    def set_stage_total(self, total: int) -> None:
        self._stage_total = max(int(total), 0)
        self._stage_num = 0

    def stage(self, title: str) -> None:
        if self.level < self.DEFAULT:
            return
        self._stage_num += 1
        if self._stage_total:
            label = f"[{self._stage_num}/{self._stage_total}] {title}"
        else:
            label = title
        self.console.print(f"[bold cyan]{label}[/bold cyan]")

    def info(self, message: str) -> None:
        if self.level >= self.DEFAULT:
            self.console.print(message)

    def verbose(self, message: str) -> None:
        if self.verbose_enabled:
            self.console.print(message)

    def debug(self, message: str) -> None:
        if self.debug_enabled:
            self.console.print(f"[magenta]{message}[/magenta]")

    def warn(self, message: str) -> None:
        self.console.print(f"[yellow][WARN][/yellow] {message}")

    def error(self, message: str) -> None:
        self.console.print(f"[bold red]{message}[/bold red]")

    def banner(self, text: Optional[str] = None) -> None:
        if self.level < self.DEFAULT:
            return
        if text is None:
            from .brand import render_banner

            render_banner(self.console, full=self.bars_enabled)
            return
        if not self.bars_enabled:
            self.console.print("[bold]MediumDarwin[/bold]")
            return
        self.console.print(text)

    def summary_table(self, title: str, rows: Sequence[Tuple[str, Any]]) -> None:
        if self.level < self.DEFAULT:
            return
        table = Table(title=title, show_header=True, header_style="bold")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        for key, value in rows:
            table.add_row(str(key), str(value))
        self.console.print(table)

    def track(
        self,
        iterable: Iterable,
        *,
        desc: str,
        total: Optional[int] = None,
        unit: str = "it",
    ) -> Iterable:
        if total is None:
            try:
                total = len(iterable)  # type: ignore[arg-type]
            except TypeError:
                total = None
        if not self.bars_enabled:
            return iterable
        progress = Progress(
            *_bar_columns(),
            console=self.console,
            transient=False,
            disable=False,
        )

        def _gen() -> Iterator:
            with progress:
                task_id = progress.add_task(desc, total=total)
                for item in iterable:
                    yield item
                    progress.advance(task_id)

        return _gen()

    @contextmanager
    def progress_task(self, desc: str, total: Optional[int] = None, unit: str = "it"):
        if not self.bars_enabled:
            yield _NullTask()
            return
        progress = Progress(
            *_bar_columns(),
            console=self.console,
            transient=False,
        )
        with progress:
            task_id = progress.add_task(desc, total=total)

            class _Handle:
                def advance(self, n: int = 1, description: Optional[str] = None) -> None:
                    kwargs = {"advance": n}
                    if description is not None:
                        kwargs["description"] = description
                    progress.update(task_id, **kwargs)

            yield _Handle()

    @contextmanager
    def status(self, message: str):
        if not self.bars_enabled:
            self.info(message)
            yield
            return
        with self.console.status(message, spinner="dots"):
            yield

    def execution_table(
        self,
        res_dict: Dict[str, Dict[str, Any]],
        start_time: float,
        total_override: Optional[int] = None,
    ) -> Table:
        total_mutant_count = 0
        total_done = 0
        total_survived = 0
        total_killed = 0
        total_timeout = 0
        total_noncovered = 0
        for data in res_dict.values():
            total_mutant_count += len(data.get("mutantsList", []))
            total_done += _file_done_count(data)
            total_survived += len(data.get("survivedList", []))
            total_killed += len(data.get("killedList", []))
            total_timeout += len(data.get("timeoutList", []))
            total_noncovered += len(data.get("nonCoveredList", []))
        if total_override is not None:
            total_mutant_count = total_override

        elapsed = max(time.time() - start_time, 0.0)
        remaining = 0.0
        if total_done and total_mutant_count > total_done:
            remaining = (elapsed / total_done) * (total_mutant_count - total_done)

        table = Table(
            title=(
                f"total {total_done}/{total_mutant_count}  "
                f"elapsed {datetime.timedelta(seconds=int(elapsed))}  "
                f"remaining {datetime.timedelta(seconds=int(remaining))}"
            ),
            expand=True,
            show_lines=False,
        )
        table.add_column("File", overflow="fold")
        table.add_column("Progress", justify="right")
        table.add_column("Survived", justify="right", style="green")
        table.add_column("Killed", justify="right", style="red")
        table.add_column("Timeout", justify="right", style="yellow")
        table.add_column("Non-covered", justify="right", style="dim")
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"{total_done}/{total_mutant_count}",
            str(total_survived),
            str(total_killed),
            str(total_timeout),
            str(total_noncovered),
        )
        for file_name, data in res_dict.items():
            n = len(data.get("mutantsList", []))
            done = _file_done_count(data)
            if n and done >= n:
                continue
            short = os.path.basename(file_name) or file_name
            table.add_row(
                short,
                f"{done}/{n}",
                str(len(data.get("survivedList", []))),
                str(len(data.get("killedList", []))),
                str(len(data.get("timeoutList", []))),
                str(len(data.get("nonCoveredList", []))),
            )
        return table

    @contextmanager
    def execution_dashboard(
        self,
        res_dict: Dict[str, Dict[str, Any]],
        start_time: float,
        total: Optional[int] = None,
        desc: str = "Running mutants",
        completed: int = 0,
    ):
        if total is None:
            total = sum(len(d.get("mutantsList", [])) for d in res_dict.values())
        total = max(int(total), 0)
        completed = max(int(completed), 0)

        class _Handle:
            def __init__(self) -> None:
                self.status_text = ""
                self.status_started = 0.0
                self.done = completed
                self._last_print = 0.0

            def set_status(self, text: str) -> None:
                return None

            def update(self, advance: int = 1) -> None:
                return None

        handle = _Handle()

        if not self.bars_enabled:
            def _plain_status(text: str) -> None:
                handle.status_text = text
                handle.status_started = time.time()
                self.info(text)

            def _plain_update(advance: int = 1) -> None:
                if advance:
                    handle.done += advance
                now = time.time()
                if handle.done >= total or now - handle._last_print >= 1.0:
                    self.info(f"{desc}: {handle.done}/{total}")
                    handle._last_print = now

            handle.set_status = _plain_status  # type: ignore[method-assign]
            handle.update = _plain_update  # type: ignore[method-assign]
            yield handle
            return

        progress = Progress(
            *_bar_columns(),
            console=self.console,
            transient=False,
            auto_refresh=False,
        )
        task_id = progress.add_task(
            desc, total=total, completed=min(completed, total)
        )

        def _render() -> Group:
            rows: List[Any] = [progress]
            if handle.status_text:
                age = 0
                if handle.status_started:
                    age = int(max(time.time() - handle.status_started, 0.0))
                rows.append(Text(f"{handle.status_text}  [{age}s]", style="cyan"))
            rows.append(self.execution_table(res_dict, start_time, total))
            return Group(*rows)

        class _Refreshable:
            def __rich__(self):
                return _render()

        with Live(
            _Refreshable(),
            console=self.console,
            refresh_per_second=4,
            transient=False,
        ) as live:
            def _set_status(text: str) -> None:
                handle.status_text = text
                handle.status_started = time.time()
                live.refresh()

            def _update(advance: int = 1) -> None:
                if advance:
                    progress.advance(task_id, advance)
                    handle.done += advance
                live.refresh()

            handle.set_status = _set_status  # type: ignore[method-assign]
            handle.update = _update  # type: ignore[method-assign]
            yield handle


def _bar_columns() -> List:
    return [
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ]
