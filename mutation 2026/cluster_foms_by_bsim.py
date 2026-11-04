#!/usr/bin/env python3
"""
Cluster FOMs by Behavioural Similarity (BSim) and analyse HOM characteristics.

Reproduces the analysis reported in:
  "Clustering First-Order Mutants by Behavioural Similarity:
   A Graph-Based Approach to Higher-Order Mutant Generation" (Mutation 2026).

Pipeline:
  1. Load FOM test outcomes from MediumDarwin SQLite databases
  2. Compute pairwise BSim between FOMs (within each source file)
  3. Build a weighted graph and cluster FOMs with the Louvain algorithm
  4. Load HOM test outcomes and classify each HOM as cluster vs non-cluster
  5. Compute BSim_HOM, DTK, and Harman subsumption categories
  6. Generate the four paper figures (BSim, DTK, BSim–DTK correlation, subsumption)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

try:
    from scipy import stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# MediumDarwin database constants
TEST_ID_NO_TEST = -1
TEST_ID_INSTRUMENTED_NOT_COVERED = -2
TEST_ID_NO_INFO = -3
RES_ID_BUILD_FAILURE = -1
RES_ID_KILLED_MUTANT = 0
RES_ID_SURVIVED_MUTANT = 1
RES_ID_NON_COVERED = -2
RES_ID_KILLED_BY_ERROR_MUTANT = 2
RES_ID_TIMEOUT = 3
EXCLUDED_TEST_IDS = (TEST_ID_NO_INFO, TEST_ID_INSTRUMENTED_NOT_COVERED, TEST_ID_NO_TEST)
EXCLUDED_RESULTS = (RES_ID_BUILD_FAILURE, RES_ID_TIMEOUT, RES_ID_NON_COVERED)

SUBSUMPTION_CATEGORIES = [
    "strongly_subsuming_coupled",
    "weakly_subsuming_coupled",
    "weakly_subsuming_decoupled",
    "non_subsuming_decoupled",
    "non_subsuming_decoupled_equivalent",
    "non_subsuming_coupled",
]

CATEGORY_LABELS = {
    "strongly_subsuming_coupled": "Strongly Subsuming,\nCoupled",
    "weakly_subsuming_coupled": "Weakly Subsuming,\nCoupled",
    "weakly_subsuming_decoupled": "Weakly Subsuming,\nDe-coupled",
    "non_subsuming_decoupled": "Non-Subsuming,\nDe-coupled",
    "non_subsuming_decoupled_equivalent": "Non-Subsuming, De-coupled\n(Equivalent)",
    "non_subsuming_coupled": "Non-Subsuming, Coupled\n(Useless)",
}

GROUP_COLORS = {
    "cluster": "#4C72B0",
    "non_cluster": "#DD8452",
    "all": "#55A868",
}

ANALYSIS_STAGES = 6

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


def configure_stdio() -> None:
    """Use UTF-8 console output on Windows and Linux when supported."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError, TypeError):
                pass
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except (AttributeError, OSError):
            pass


def open_log_file(path: Path) -> Any:
    """Open an append-only UTF-8 log with Unix newlines (readable on Windows and Linux)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8", newline="\n")


class StageReporter:
    """Print numbered pipeline stages for a single project run."""

    def __init__(
        self,
        project_name: str,
        total_stages: int = ANALYSIS_STAGES,
        log_file: Optional[Any] = None,
    ):
        self.project_name = project_name
        self.total_stages = total_stages
        self.stage_num = 0
        self.log_file = log_file

    def _emit(self, line: str, *, to_console: bool = True) -> None:
        if to_console:
            print(line, flush=True)
        if self.log_file is not None:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def begin(self, title: str) -> None:
        self.stage_num += 1
        self._emit(f"[{self.stage_num}/{self.total_stages}] {title}")

    def detail(self, message: str) -> None:
        self._emit(f"       {message}")


def progress_bars_enabled() -> bool:
    """tqdm only in an interactive terminal; never when stdout is piped/redirected."""
    if not TQDM_AVAILABLE:
        return False
    if not sys.stdout.isatty():
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return True


def iter_with_progress(
    iterable,
    *,
    total: int,
    desc: str,
    unit: str,
):
    if progress_bars_enabled():
        return tqdm(
            iterable,
            total=total,
            desc=desc,
            unit=unit,
            leave=True,
            dynamic_ncols=True,
            file=sys.stdout,
            ascii=False,
        )
    return iterable


def convert_to_native_types(obj: Any) -> Any:
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: convert_to_native_types(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [convert_to_native_types(v) for v in obj]
    return obj


def result_to_outcome(result: int) -> Optional[int]:
    if result == RES_ID_SURVIVED_MUTANT:
        return 1
    if result in (RES_ID_KILLED_MUTANT, RES_ID_KILLED_BY_ERROR_MUTANT):
        return 0
    return None


def load_fom_test_outcomes(database_path: Path) -> Dict[str, Dict[str, int]]:
    if not database_path.exists():
        raise SystemExit(f"FOM database not found: {database_path}")

    conn = sqlite3.connect(str(database_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.mutation_id, t.qualified_name, mt.result
        FROM mutant_test mt
        JOIN mutant m ON m.id = mt.mutant_id
        JOIN test t ON mt.test_id = t.id
        WHERE mt.test_id NOT IN (-3, -2, -1)
          AND mt.result NOT IN (-1, 3, -2)
        ORDER BY m.mutation_id, t.qualified_name
        """
    )
    rows = cursor.fetchall()
    conn.close()

    outcomes: Dict[str, Dict[str, int]] = {}
    for mutation_id, test_name, result in rows:
        if mutation_id is None or not test_name:
            continue
        outcome = result_to_outcome(result)
        if outcome is None:
            continue
        key = str(int(mutation_id))
        normalized = str(test_name).replace("$", ".").replace("#", ".")
        outcomes.setdefault(key, {})[normalized] = outcome
    return outcomes


def load_fom_file_map(database_path: Path, mutation_ids: Set[str]) -> Dict[str, str]:
    if not database_path.exists():
        return {}

    ids_int = [int(x) for x in mutation_ids if str(x).isdigit()]
    if not ids_int:
        return {}

    conn = sqlite3.connect(str(database_path))
    cursor = conn.cursor()
    mapping: Dict[str, str] = {}
    chunk_size = 900
    for i in range(0, len(ids_int), chunk_size):
        chunk = ids_int[i : i + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        cursor.execute(
            f"""
            SELECT mut.id, f.name
            FROM mutation mut
            JOIN file f ON mut.file_id = f.id
            WHERE mut.id IN ({placeholders})
            """,
            tuple(chunk),
        )
        for mid, file_name in cursor.fetchall():
            if mid is None or not file_name:
                continue
            mapping[str(int(mid))] = str(file_name).replace("\\", "/")
    conn.close()
    return mapping


def compute_bsim(
    outcomes_1: Dict[str, int], outcomes_2: Dict[str, int]
) -> float:
    """BSim(m1, m2) = |{t : T1[t] = T2[t]}| / |T| (Eq. 1 in the paper)."""
    if not outcomes_1 or not outcomes_2:
        return 0.0
    all_tests = set(outcomes_1) | set(outcomes_2)
    if not all_tests:
        return 0.0
    matches = sum(
        1
        for test in all_tests
        if outcomes_1.get(test) is not None
        and outcomes_2.get(test) is not None
        and outcomes_1[test] == outcomes_2[test]
    )
    return matches / len(all_tests)


def compute_pairwise_bsim(
    fom_outcomes: Dict[str, Dict[str, int]],
    fom_to_file: Dict[str, str],
) -> Dict[Tuple[str, str], float]:
    matrix: Dict[Tuple[str, str], float] = {}
    file_to_foms: Dict[str, List[str]] = defaultdict(list)
    for fom_id in fom_outcomes:
        file_name = fom_to_file.get(fom_id)
        if file_name:
            file_to_foms[file_name].append(str(fom_id))

    for foms_in_file in file_to_foms.values():
        foms_sorted = sorted(foms_in_file, key=lambda x: int(x) if x.isdigit() else x)
        for i, fom_1 in enumerate(foms_sorted):
            for fom_2 in foms_sorted[i + 1 :]:
                value = compute_bsim(fom_outcomes[fom_1], fom_outcomes[fom_2])
                matrix[(fom_1, fom_2)] = value
                matrix[(fom_2, fom_1)] = value
    return matrix


def build_bsim_graph(
    fom_outcomes: Dict[str, Dict[str, int]],
    bsim_matrix: Dict[Tuple[str, str], float],
    threshold: float,
    force_connectivity: bool,
) -> nx.Graph:
    graph = nx.Graph()
    for fom_id in fom_outcomes:
        graph.add_node(fom_id)

    for (fom_1, fom_2), value in bsim_matrix.items():
        if fom_1 < fom_2 and value >= threshold:
            graph.add_edge(fom_1, fom_2, weight=value)

    if force_connectivity:
        for _ in range(len(graph.nodes())):
            isolated = [n for n in graph.nodes() if graph.degree(n) == 0]
            if not isolated:
                break
            for node in isolated:
                best_edge = None
                best_value = -1.0
                for (fom_1, fom_2), value in bsim_matrix.items():
                    if node in (fom_1, fom_2) and not graph.has_edge(fom_1, fom_2):
                        if value > best_value:
                            best_value = value
                            best_edge = (fom_1, fom_2)
                if best_edge:
                    fom_1, fom_2 = best_edge
                    graph.add_edge(fom_1, fom_2, weight=best_value)
    return graph


def cluster_foms_louvain(graph: nx.Graph) -> List[List[str]]:
    try:
        import community as community_louvain
    except ImportError as exc:
        raise SystemExit(
            "python-louvain is required. Install with: pip install python-louvain"
        ) from exc

    clusters: List[List[str]] = []
    for component in nx.connected_components(graph):
        subgraph = graph.subgraph(component)
        partition = community_louvain.best_partition(subgraph, randomize=False)
        grouped: Dict[int, List[str]] = defaultdict(list)
        for node, cluster_id in partition.items():
            grouped[cluster_id].append(node)
        clusters.extend(sorted(group) for group in grouped.values())
    return clusters


def check_hom_in_same_cluster(
    fom_ids: List[str], clusters: List[List[str]]
) -> Tuple[bool, Optional[List[str]]]:
    fom_set = set(str(f) for f in fom_ids)
    for cluster in clusters:
        if fom_set.issubset(set(str(f) for f in cluster)):
            return True, cluster
    return False, None


def discover_homs_from_database(database_path: Path) -> Dict[str, List[str]]:
    if not database_path.exists():
        return {}

    conn = sqlite3.connect(str(database_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(mutant)")
    cols = {row[1] for row in cursor.fetchall() if row}
    mutant_id_col = "mutant_id" if "mutant_id" in cols else "id"
    cursor.execute(
        f"""
        SELECT {mutant_id_col}, GROUP_CONCAT(DISTINCT mutation_id)
        FROM mutant
        GROUP BY {mutant_id_col}
        HAVING COUNT(DISTINCT mutation_id) > 1
        """
    )
    rows = cursor.fetchall()
    conn.close()

    homs: Dict[str, List[str]] = {}
    for _, mutation_ids_str in rows:
        if not mutation_ids_str:
            continue
        mutation_ids = sorted(
            [str(int(mid.strip())) for mid in mutation_ids_str.split(",") if mid.strip()],
            key=int,
        )
        if len(mutation_ids) >= 2:
            homs["_".join(mutation_ids)] = mutation_ids
    return homs


def load_hom_test_outcomes(
    database_paths: List[Path], fom_ids: List[str]
) -> Optional[Dict[str, int]]:
    mutation_ids = [int(f) for f in fom_ids if str(f).isdigit()]
    if not mutation_ids:
        return None

    for database_path in database_paths:
        if not database_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(database_path))
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(mutant)")
            cols = {row[1] for row in cursor.fetchall() if row}
            mutant_id_col = "mutant_id" if "mutant_id" in cols else "id"

            placeholders = ",".join(["?"] * len(mutation_ids))
            cursor.execute(
                f"""
                SELECT {mutant_id_col}, COUNT(DISTINCT mutation_id)
                FROM mutant
                WHERE mutation_id IN ({placeholders})
                GROUP BY {mutant_id_col}
                HAVING COUNT(DISTINCT mutation_id) = ?
                """,
                (*mutation_ids, len(mutation_ids)),
            )
            rows = cursor.fetchall()
            if not rows:
                conn.close()
                continue

            hom_mutant_id = rows[0][0]
            cursor.execute(
                f"""
                SELECT t.qualified_name, mt.result
                FROM mutant_test mt
                JOIN test t ON mt.test_id = t.id
                WHERE mt.mutant_id = ?
                  AND mt.test_id NOT IN ({",".join(str(x) for x in EXCLUDED_TEST_IDS)})
                  AND mt.result NOT IN ({",".join(str(x) for x in EXCLUDED_RESULTS)})
                """,
                (hom_mutant_id,),
            )
            test_rows = cursor.fetchall()
            conn.close()

            outcomes: Dict[str, int] = {}
            for test_name, result in test_rows:
                outcome = result_to_outcome(result)
                if outcome is None or not test_name:
                    continue
                outcomes[str(test_name).replace("$", ".").replace("#", ".")] = outcome
            if outcomes:
                return outcomes
        except sqlite3.Error:
            continue
    return None


def classify_hom_category(
    hom_kill_set: Set[str],
    fom_kill_sets: List[Set[str]],
) -> str:
    union = set()
    intersection: Optional[Set[str]] = None
    for kill_set in fom_kill_sets:
        union |= kill_set
        intersection = kill_set.copy() if intersection is None else intersection & kill_set
    intersection = intersection or set()

    if not hom_kill_set:
        return "non_subsuming_decoupled_equivalent"
    if hom_kill_set.issubset(intersection):
        return "strongly_subsuming_coupled"
    if len(hom_kill_set) < len(union) and (hom_kill_set & union):
        if hom_kill_set.issubset(intersection):
            return "strongly_subsuming_coupled"
        return "weakly_subsuming_coupled"
    if len(hom_kill_set) < len(union) and not (hom_kill_set & union):
        return "weakly_subsuming_decoupled"
    if len(hom_kill_set) >= len(union) and not (hom_kill_set & union):
        return "non_subsuming_decoupled"
    if len(hom_kill_set) >= len(union) and (hom_kill_set & union):
        return "non_subsuming_coupled"
    return "unknown"


def get_hom_cache_path(cache_dir: Path, hom_name: str) -> Path:
    safe_name = hom_name.replace("/", "_").replace("\\", "_")
    return cache_dir / f"hom_cache_{safe_name}.json"


def load_hom_from_cache(
    cache_path: Path, verbose: bool = False
) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        if verbose:
            print(f"Warning: could not load cache {cache_path}: {exc}")
        return None


def save_hom_to_cache(
    cache_path: Path, hom_result: Dict[str, Any], verbose: bool = False
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(convert_to_native_types(hom_result), handle, indent=2)
    except OSError as exc:
        if verbose:
            print(f"Warning: could not save cache {cache_path}: {exc}")


def analyse_hom(
    hom_name: str,
    fom_ids: List[str],
    clusters: List[List[str]],
    fom_outcomes: Dict[str, Dict[str, int]],
    hom_databases: List[Path],
) -> Optional[Dict[str, Any]]:
    if any(fid not in fom_outcomes for fid in fom_ids):
        return None

    hom_outcomes = load_hom_test_outcomes(hom_databases, fom_ids)
    if not hom_outcomes:
        return None

    total_tests = len(hom_outcomes)
    failing_tests = sum(1 for v in hom_outcomes.values() if v == 0)
    dtk = 1.0 - (failing_tests / total_tests) if total_tests else 1.0

    bsim_values = [
        compute_bsim(hom_outcomes, fom_outcomes[fid]) for fid in fom_ids
    ]
    bsim_hom = float(np.mean(bsim_values))

    fom_kill_sets = [
        {t for t, o in fom_outcomes[fid].items() if o == 0} for fid in fom_ids
    ]
    hom_kill_set = {t for t, o in hom_outcomes.items() if o == 0}
    in_cluster, _ = check_hom_in_same_cluster(fom_ids, clusters)

    return {
        "hom_name": hom_name,
        "fom_ids": fom_ids,
        "bsim_hom": bsim_hom,
        "dtk": float(dtk),
        "is_cluster_hom": in_cluster,
        "subsumption_category": classify_hom_category(hom_kill_set, fom_kill_sets),
        "num_foms": len(fom_ids),
    }


def process_hom(
    hom_name: str,
    fom_ids: List[str],
    clusters: List[List[str]],
    fom_outcomes: Dict[str, Dict[str, int]],
    hom_databases: List[Path],
    cache_dir: Path,
    use_cache: bool,
    verbose: bool,
) -> Optional[Dict[str, Any]]:
    """Load a HOM from cache or compute and store it."""
    cache_path = get_hom_cache_path(cache_dir, hom_name)
    if use_cache:
        cached = load_hom_from_cache(cache_path, verbose=verbose)
        if cached:
            in_cluster, _ = check_hom_in_same_cluster(fom_ids, clusters)
            cached["is_cluster_hom"] = in_cluster
            return cached

    result = analyse_hom(hom_name, fom_ids, clusters, fom_outcomes, hom_databases)
    if result and use_cache:
        save_hom_to_cache(cache_path, result, verbose=verbose)
    return result


def summarise_group(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "std": 0.0, "n": 0}
    arr = np.array(values, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "n": int(len(arr)),
    }


def generate_paper_figure(
    project_name: str,
    results: List[Dict[str, Any]],
    output_path: Path,
) -> Dict[str, Any]:
    cluster_bsim = [r["bsim_hom"] for r in results if r["is_cluster_hom"]]
    non_cluster_bsim = [r["bsim_hom"] for r in results if not r["is_cluster_hom"]]
    all_bsim = [r["bsim_hom"] for r in results]

    cluster_dtk = [r["dtk"] for r in results if r["is_cluster_hom"]]
    non_cluster_dtk = [r["dtk"] for r in results if not r["is_cluster_hom"]]
    all_dtk = [r["dtk"] for r in results]

    correlation: Dict[str, Any] = {}
    if SCIPY_AVAILABLE and len(all_bsim) > 1:
        pearson_r, pearson_p = stats.pearsonr(all_bsim, all_dtk)
        spearman_r, spearman_p = stats.spearmanr(all_bsim, all_dtk)
        correlation = {
            "pearson_r": float(pearson_r),
            "pearson_p": float(pearson_p),
            "spearman_rho": float(spearman_r),
            "spearman_p": float(spearman_p),
        }

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"Results for {project_name} (n = {len(results):,} HOMs)", fontsize=14)

    # (a) BSim boxplot
    ax = axes[0, 0]
    bp = ax.boxplot(
        [cluster_bsim, non_cluster_bsim, all_bsim],
        tick_labels=["Cluster\nHOMs", "Non-Cluster\nHOMs", "All\nHOMs"],
        patch_artist=True,
        widths=0.55,
    )
    for patch, key in zip(bp["boxes"], ("cluster", "non_cluster", "all")):
        patch.set_facecolor(GROUP_COLORS[key])
        patch.set_alpha(0.75)
    ax.set_ylabel(r"$BSim_{HOM}(h)$")
    ax.set_title("(a) Average BSim between HOMs and their constituent FOMs")
    ax.grid(True, alpha=0.3, axis="y")

    # (b) DTK boxplot
    ax = axes[0, 1]
    bp = ax.boxplot(
        [cluster_dtk, non_cluster_dtk, all_dtk],
        tick_labels=["Cluster\nHOMs", "Non-Cluster\nHOMs", "All\nHOMs"],
        patch_artist=True,
        widths=0.55,
    )
    for patch, key in zip(bp["boxes"], ("cluster", "non_cluster", "all")):
        patch.set_facecolor(GROUP_COLORS[key])
        patch.set_alpha(0.75)
    ax.set_ylabel("DTK")
    ax.set_title("(b) DTK comparison across groups")
    ax.grid(True, alpha=0.3, axis="y")

    # (c) BSim vs DTK scatter
    ax = axes[1, 0]
    cluster_x = [r["bsim_hom"] for r in results if r["is_cluster_hom"]]
    cluster_y = [r["dtk"] for r in results if r["is_cluster_hom"]]
    non_x = [r["bsim_hom"] for r in results if not r["is_cluster_hom"]]
    non_y = [r["dtk"] for r in results if not r["is_cluster_hom"]]
    ax.scatter(cluster_x, cluster_y, alpha=0.35, s=12, c=GROUP_COLORS["cluster"], label="Cluster HOMs")
    ax.scatter(non_x, non_y, alpha=0.35, s=12, c=GROUP_COLORS["non_cluster"], label="Non-Cluster HOMs")
    if SCIPY_AVAILABLE and len(all_bsim) > 1:
        slope, intercept, _, _, _ = stats.linregress(all_bsim, all_dtk)
        x_line = np.array([min(all_bsim), max(all_bsim)])
        ax.plot(x_line, slope * x_line + intercept, "k--", alpha=0.6, linewidth=1.5)
        text = (
            f"Pearson r={correlation['pearson_r']:.4f}, p={correlation['pearson_p']:.4e}\n"
            f"Spearman rho={correlation['spearman_rho']:.4f}, p={correlation['spearman_p']:.4e}"
        )
        ax.text(0.04, 0.96, text, transform=ax.transAxes, va="top", fontsize=9,
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))
    ax.set_xlabel(r"$BSim_{HOM}(h)$")
    ax.set_ylabel("DTK")
    ax.set_title("(c) BSim vs DTK correlation")
    ax.grid(True, alpha=0.3)

    # (d) Subsumption bar chart
    ax = axes[1, 1]
    cluster_pct = category_percentages(results, "is_cluster_hom")
    non_cluster_pct = category_percentages(results, "not_cluster")
    all_pct = category_percentages(results, "all")

    x = np.arange(len(SUBSUMPTION_CATEGORIES))
    width = 0.25
    cluster_vals = [cluster_pct[c] for c in SUBSUMPTION_CATEGORIES]
    non_vals = [non_cluster_pct[c] for c in SUBSUMPTION_CATEGORIES]
    all_vals = [all_pct[c] for c in SUBSUMPTION_CATEGORIES]

    ax.bar(x - width, cluster_vals, width, label="Cluster", color=GROUP_COLORS["cluster"], alpha=0.85)
    ax.bar(x, non_vals, width, label="Non-Cluster", color=GROUP_COLORS["non_cluster"], alpha=0.85)
    ax.bar(x + width, all_vals, width, label="All", color=GROUP_COLORS["all"], alpha=0.85)
    ax.set_ylabel("Percentage (%)")
    ax.set_title("(d) Subsumption-category breakdown per group")
    ax.set_xticks(x)
    ax.set_xticklabels([CATEGORY_LABELS[c] for c in SUBSUMPTION_CATEGORIES], fontsize=8)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    ymax = max(cluster_vals + non_vals + all_vals + [1.0])
    ax.set_ylim(0, min(105, ymax * 1.15 + 5))

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return {
        "num_homs": len(results),
        "num_cluster_homs": len(cluster_bsim),
        "num_non_cluster_homs": len(non_cluster_bsim),
        "bsim": {
            "cluster": summarise_group(cluster_bsim),
            "non_cluster": summarise_group(non_cluster_bsim),
            "all": summarise_group(all_bsim),
        },
        "dtk": {
            "cluster": summarise_group(cluster_dtk),
            "non_cluster": summarise_group(non_cluster_dtk),
            "all": summarise_group(all_dtk),
        },
        "correlation": correlation,
        "subsumption_percentages": {
            "cluster": cluster_pct,
            "non_cluster": non_cluster_pct,
            "all": all_pct,
        },
    }


def category_percentages(results: List[Dict[str, Any]], group: str) -> Dict[str, float]:
    if group == "is_cluster_hom":
        filtered = [r for r in results if r["is_cluster_hom"]]
    elif group == "not_cluster":
        filtered = [r for r in results if not r["is_cluster_hom"]]
    else:
        filtered = results
    total = len(filtered)
    counts = {cat: 0 for cat in SUBSUMPTION_CATEGORIES}
    for result in filtered:
        cat = result["subsumption_category"]
        if cat in counts:
            counts[cat] += 1
    return {cat: (100.0 * counts[cat] / total if total else 0.0) for cat in SUBSUMPTION_CATEGORIES}


def run_analysis(
    project_name: str,
    fom_database: Path,
    hom_databases: List[Path],
    output_dir: Path,
    threshold: float = 0.0,
    workers: Optional[int] = None,
    verbose: bool = False,
    cache_dir: Optional[Path] = None,
    use_cache: bool = True,
    clear_cache: bool = False,
    project_index: Optional[int] = None,
    project_total: Optional[int] = None,
    log_file: Optional[Any] = None,
) -> Dict[str, Any]:
    progress = StageReporter(project_name, log_file=log_file)
    if project_index is not None and project_total is not None:
        header = f"Project {project_index}/{project_total}: {project_name}"
    else:
        header = f"Project: {project_name}"
    progress._emit(f"\n{'=' * 72}\n{header}\n{'=' * 72}")

    progress.begin("Loading FOM test outcomes")
    fom_outcomes = load_fom_test_outcomes(fom_database)
    if not fom_outcomes:
        raise SystemExit(f"No FOM outcomes loaded from {fom_database}")
    progress.detail(f"Loaded {len(fom_outcomes)} FOMs from {fom_database.name}")

    progress.begin("Computing BSim matrix and Louvain clustering")
    fom_to_file = load_fom_file_map(fom_database, set(fom_outcomes))
    bsim_matrix = compute_pairwise_bsim(fom_outcomes, fom_to_file)
    graph = build_bsim_graph(fom_outcomes, bsim_matrix, threshold, force_connectivity=True)
    clusters = cluster_foms_louvain(graph)
    progress.detail(
        f"{len(clusters)} clusters, {graph.number_of_edges()} edges "
        f"(threshold={threshold})"
    )

    progress.begin("Discovering HOMs from databases")
    all_homs: Dict[str, List[str]] = {}
    for db in hom_databases:
        discovered = discover_homs_from_database(db)
        progress.detail(f"{db.name}: {len(discovered)} HOMs")
        all_homs.update(discovered)
    progress.detail(f"{len(all_homs)} unique HOMs in total")

    project_output = output_dir / project_name
    project_output.mkdir(parents=True, exist_ok=True)
    hom_cache_dir = cache_dir or (project_output / "hom_cache")
    if clear_cache and hom_cache_dir.exists():
        shutil.rmtree(hom_cache_dir)
        progress.detail(f"Cleared HOM cache at {hom_cache_dir}")
    if use_cache:
        progress.detail(f"HOM cache enabled: {hom_cache_dir}")

    progress.begin("Analysing HOMs (BSim, DTK, subsumption)")
    hom_results: List[Dict[str, Any]] = []
    worker_count = workers or min(32, (os.cpu_count() or 4) * 2)
    progress.detail(f"Using {worker_count} parallel workers")

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                process_hom,
                name,
                fom_ids,
                clusters,
                fom_outcomes,
                hom_databases,
                hom_cache_dir,
                use_cache,
                False,
            ): name
            for name, fom_ids in all_homs.items()
        }
        completed_iter = iter_with_progress(
            as_completed(futures),
            total=len(futures),
            desc="       HOMs",
            unit="hom",
        )
        for future in completed_iter:
            result = future.result()
            if result:
                hom_results.append(result)

    cache_count = (
        len(list(hom_cache_dir.glob("hom_cache_*.json")))
        if use_cache and hom_cache_dir.exists()
        else 0
    )
    progress.detail(
        f"Completed {len(hom_results)}/{len(all_homs)} HOMs"
        + (f" ({cache_count} cache files)" if use_cache else "")
    )

    progress.begin("Generating paper figures")
    summary = generate_paper_figure(
        project_name,
        hom_results,
        project_output / "fig_results.png",
    )
    progress.detail("Saved fig_results.png")

    output_data = {
        "project": project_name,
        "cache": {
            "enabled": use_cache,
            "directory": str(hom_cache_dir),
            "num_cached_files": len(list(hom_cache_dir.glob("hom_cache_*.json"))) if hom_cache_dir.exists() else 0,
        },
        "clustering": {
            "method": "louvain",
            "threshold": threshold,
            "num_foms": len(fom_outcomes),
            "num_clusters": len(clusters),
            "clusters": clusters,
        },
        "summary": summary,
        "homs": hom_results,
    }

    progress.begin("Saving results")
    results_json = project_output / "bsim_analysis_results.json"
    with results_json.open("w", encoding="utf-8") as handle:
        json.dump(convert_to_native_types(output_data), handle, indent=2)

    summary_txt = project_output / "analysis_summary.txt"
    with summary_txt.open("w", encoding="utf-8") as handle:
        handle.write(f"BSim Cluster Analysis - {project_name}\n")
        handle.write("=" * 60 + "\n\n")
        handle.write(f"HOMs analysed: {summary['num_homs']}\n")
        handle.write(f"Cluster HOMs: {summary['num_cluster_homs']}\n")
        handle.write(f"Non-cluster HOMs: {summary['num_non_cluster_homs']}\n\n")
        for metric in ("bsim", "dtk"):
            handle.write(f"{metric.upper()} statistics:\n")
            for group in ("cluster", "non_cluster", "all"):
                stats_dict = summary[metric][group]
                handle.write(
                    f"  {group}: mean={stats_dict['mean']:.4f}, "
                    f"median={stats_dict['median']:.4f}, n={stats_dict['n']}\n"
                )
            handle.write("\n")
        if summary["correlation"]:
            c = summary["correlation"]
            handle.write(
                f"BSim-DTK correlation: Pearson r={c['pearson_r']:.4f}, "
                f"Spearman rho={c['spearman_rho']:.4f}\n"
            )

    progress.detail(f"Results written to {project_output}")
    progress._emit(f"Done: {project_name}")
    return output_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cluster FOMs by Behavioural Similarity (BSim) and analyse HOMs."
    )
    parser.add_argument("--project", required=True, help="Project name (e.g. triangle-example)")
    parser.add_argument("--fom-database", required=True, type=Path, help="FOM SQLite database")
    parser.add_argument(
        "--hom-databases",
        required=True,
        nargs="+",
        type=Path,
        help="One or more HOM SQLite databases",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="Directory for analysis outputs (default: results/)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="BSim threshold for graph edges (default: 0)",
    )
    parser.add_argument("--workers", type=int, default=None, help="Parallel workers for HOM analysis")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory for per-HOM result cache (default: <output-dir>/<project>/hom_cache)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable HOM result caching and recompute every HOM",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete existing HOM cache before running",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    configure_stdio()

    run_analysis(
        project_name=args.project,
        fom_database=args.fom_database,
        hom_databases=args.hom_databases,
        output_dir=args.output_dir,
        threshold=args.threshold,
        workers=args.workers,
        verbose=args.verbose,
        cache_dir=args.cache_dir,
        use_cache=not args.no_cache,
        clear_cache=args.clear_cache,
    )


if __name__ == "__main__":
    main()
