# Mutation 2026 — BSim Clustering Paper Reproduction

This folder contains scripts, configuration, and a pipeline to reproduce the empirical analysis and figures from the paper below. Subject-system SQLite databases are downloaded separately (Google Drive or Zenodo).

## Subject systems

| Project | FOM database | HOM databases |
|---------|--------------|---------------|
| triangle-example | `triangle-example/mutationdatabase_foms.db` | `cluster_homs_mutationdatabase.db`, `mutationdatabase_everywhere.db` |
| jra | `jra/fom_mutationdatabase.db` | `mutationdatabase_cluster.db`, `mutationdatabase_everywhere.db` |
| antomology | `antomology/mutationdatabase_foms.db` | `mutationdatabase_homs_1.db`, `mutationdatabase_homs_2.db` |
| jterminal | `jterminal/mutationdatabase_foms.db` | `mutationdatabase_homs_1–4.db` |
| commons-csv | `commons-csv/mutationdatabase_foms.db` | `mutationdatabase_homs_1–4.db` |

Project paths and BSim graph thresholds are configured in `projects.json`.

## Paper

**Clustering First-Order Mutants by Behavioural Similarity: A Graph-Based Approach to Higher-Order Mutant Generation**

Sajjad Hesamipour, Thomas Laurent, Anthony Ventresque  
Trinity College Dublin & Lero

Presented at the **[21st International Workshop on Mutation Analysis](https://conf.researchr.org/home/icst-2026/mutation-2026)** (Mutation 2026), co-located with [ICST 2026](https://conf.researchr.org/home/icst-2026), Daejeon, South Korea, 18 May 2026.

The paper clusters first-order mutants (FOMs) by **behavioural similarity (BSim)** using kill-vector comparisons, builds a weighted graph per source file, and applies **Louvain** community detection. The resulting clusters guide **higher-order mutant (HOM)** generation and analysis. This reproduction evaluates cluster vs non-cluster HOMs on five Java subject systems using BSim<sub>HOM</sub>, **DTK**, and Harman subsumption categories.

### Citation

```bibtex
@inproceedings{hesamipour2026clustering,
  author    = {Sajjad Hesamipour and Thomas Laurent and Anthony Ventresque},
  title     = {Clustering First-Order Mutants by Behavioural Similarity: A Graph-Based Approach to Higher-Order Mutant Generation},
  booktitle = {Proceedings of the IEEE International Conference on Software Testing, Verification and Validation Workshop (ICSTW)},
  year      = {2026},
  address   = {Daejeon, South Korea}
}
```

Plain text:

> Sajjad Hesamipour Khelejan, Thomas Laurent, and Anthony Ventresque. *Clustering First-Order Mutants by Behavioural Similarity: A Graph-Based Approach to Higher-Order Mutant Generation*. In *Proceedings of the IEEE International Conference on Software Testing, Verification and Validation Workshops (ICSTW)*, 2026.

## Requirements

```bash
pip install -r requirements.txt
```

Dependencies: `numpy`, `matplotlib`, `networkx`, `scipy`, `python-louvain`, `tqdm`, `gdown`.

## Databases (Google Drive)

Subject-system SQLite databases (~21.1 GB) are **not** in git. They are hosted on Google Drive:

[Mutation 2026 databases](https://drive.google.com/drive/folders/1abTVxYywqI2__pb5ImDl6FvpSQcKZSQn?usp=sharing)

The same databases are also archived on Zenodo ([10.5281/zenodo.20637825](https://doi.org/10.5281/zenodo.20637825)) as a long-term backup if the Google Drive link is ever removed. Download the project folders from Zenodo and place them under this directory (matching the layout in `projects.json`).

The launchers download any missing databases automatically before analysis. You can also download manually:

**Windows (PowerShell):**
```powershell
.\download_databases.ps1
.\download_databases.ps1 -Projects triangle-example
```

**Linux / macOS / Git Bash:**
```bash
chmod +x download_databases.sh   # first time only
./download_databases.sh
./download_databases.sh triangle-example
```

Re-download existing files with `--force` / `-Force`.

You need **~25 GB free** on the drive where this folder lives (e.g. `D:`). If a download fails with “no space left on device”, free disk space, delete any leftover `mutation2026_drive_*` folders here, then re-run. Use `-SkipDownload` / `--skip-download` once the databases are already in place.

## Quick start

From this folder:

**Windows (PowerShell):**
```powershell
.\run_bsim_analysis.ps1
```

**Linux / macOS / Git Bash:**
```bash
chmod +x run_bsim_analysis.sh   # first time only
./run_bsim_analysis.sh
```

Run one or more projects:
```powershell
.\run_bsim_analysis.ps1 -Projects triangle-example -Verbose
.\run_bsim_analysis.ps1 -Projects triangle-example,jra
```
```bash
./run_bsim_analysis.sh triangle-example
./run_bsim_analysis.sh triangle-example jra
./run_bsim_analysis.sh --projects triangle-example,jra --verbose
```

On Windows you can also use Git Bash or WSL with `bash run_bsim_analysis.sh`.

Use `--skip-download` / `-SkipDownload` if the databases are already on disk.

## Outputs

For each project, results are written to `results/<project>/`:

| File | Description |
|------|-------------|
| `fig_results.png` | Four-panel figure matching the paper (BSim, DTK, BSim–DTK correlation, subsumption) |
| `analysis_summary.txt` | Key statistics (means, medians, correlations) |
| `bsim_analysis_results.json` | Full per-HOM results and cluster assignments |
| `hom_cache/` | Per-HOM JSON cache (speeds up re-runs) |

## Analysis script

`cluster_foms_by_bsim.py` implements the paper pipeline:

1. Load FOM kill vectors from MediumDarwin databases
2. Compute pairwise **BSim** (behavioural similarity) within each source file
3. Build a weighted graph and cluster FOMs with **Louvain**
4. Load HOM results and label each as **cluster** or **non-cluster** HOM
5. Compute **BSim<sub>HOM</sub>**, **DTK**, and Harman subsumption categories
6. Generate the paper figures

### Direct usage

```bash
python cluster_foms_by_bsim.py \
  --project triangle-example \
  --fom-database triangle-example/mutationdatabase_foms.db \
  --hom-databases triangle-example/cluster_homs_mutationdatabase.db triangle-example/mutationdatabase_everywhere.db \
  --output-dir results \
  --verbose
```

### Caching

HOM-level results are cached under `results/<project>/hom_cache/` as JSON files. On a cache hit, cluster membership (`is_cluster_hom`) is refreshed against the current Louvain clustering; BSim, DTK, and subsumption values are reused.

| Flag | Effect |
|------|--------|
| *(default)* | Use cache when available |
| `--no-cache` | Recompute every HOM |
| `--clear-cache` | Delete cache before running |
| `--cache-dir <path>` | Override cache location |

Example — force a full recomputation:

```powershell
.\run_bsim_analysis.ps1 -ClearCache -NoCache -Verbose -Projects triangle-example
```
```bash
./run_bsim_analysis.sh --clear-cache --no-cache --verbose triangle-example
```

## Terminology

The original research code used **Diagnostic Similarity (DS)**. The paper renames this metric to **Behavioural Similarity (BSim)**. The formulas are identical.

| Paper | Code |
|-------|------|
| BSim | `compute_bsim()` |
| BSim<sub>HOM</sub>(h) | `bsim_hom` |
| DTK | `dtk` |
| Cluster HOMs | `is_cluster_hom == true` |

## Progress display

The pipeline reports what it is doing at two levels:

1. **Project bar** — when running multiple subjects (`Projects 2/5`)
2. **Per-project stages** — six numbered steps with details:
   - Load FOM outcomes
   - Compute BSim matrix and Louvain clustering
   - Discover HOMs
   - Analyse HOMs (with a `HOMs` progress bar)
   - Generate figures
   - Save results

Progress bars appear whenever the run is attached to an interactive terminal.

## Logs and cross-platform output

Pipeline runs append to `logs/bsim_analysis.log` as plain **UTF-8** text with Unix line endings (`\n`), readable on both **Windows** and **Linux**.

| Where | What you see |
|-------|----------------|
| **Console (TTY)** | Stage messages + live tqdm progress bars |
| **Log file** | Stage messages only (no tqdm redraw spam) |
| **Piped / CI** | Stage messages only (`sys.stdout.isatty()` disables bars) |

The launcher scripts set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`. PowerShell also sets the console to UTF-8.

Generated outputs under `results/` and `logs/` remain local and are listed in `.gitignore`.
