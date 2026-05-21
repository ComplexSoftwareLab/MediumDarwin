#!/usr/bin/env bash

if ((BASH_VERSINFO[0] < 4))
then
  echo "Sorry, you need at least bash-4.0 to run this script."
  exit 1
fi

# Ensure the script is run from the correct directory
if [ "$(basename "$PWD")" != "tool paper" ]; then
  echo "Please navigate to the 'tool paper' directory before running this script."
  exit 1
fi


# MediumDarwin Mutation Analysis Runner (with dependency installation)
# This script clones MediumDarwin, installs dependencies, and runs mutation testing

# Configuration
MEDIUMDARWIN_REPO="https://github.com/ComplexSoftwareLab/MediumDarwin"
LITTLEDARWIN_REPO="https://github.com/aliparsai/LittleDarwin.git"
INSTALL_DEPS=true
LOG_FILE="mutation_analysis.log"
VENV_DIR=".mediumdarwin_venv"
COMPARE_RESULTS=true
COMPARE_ONLY=false
COMPARISONS_DIR="operator_comparisons"
EXTRACT_SCRIPT="extract_mutations.py"
PARALLEL_JOBS="${PARALLEL_JOBS:-1}"
LOGS_DIR="logs"
TOOL_PAPER_ROOT=""

# JDK bin directories (override via env vars or --java*-bin flags).
# JAVA_HOME is derived as ${bin_path%/bin}, matching the experiment runner.
JAVA_HOME_8_BIN="${JAVA_HOME_8_BIN:-/usr/lib/jvm/java-8-openjdk-amd64/bin}"
JAVA_HOME_11_BIN="${JAVA_HOME_11_BIN:-/usr/lib/jvm/java-11-openjdk-amd64/bin}"
JAVA_HOME_21_BIN="${JAVA_HOME_21_BIN:-/usr/lib/jvm/java-21-openjdk-amd64/bin}"
JAVA_HOME_23_BIN="${JAVA_HOME_23_BIN:-/usr/lib/jvm/java-23-openjdk-amd64/bin}"

declare -A JAVA_HOME_BIN=(
  [8]="$JAVA_HOME_8_BIN"
  [11]="$JAVA_HOME_11_BIN"
  [21]="$JAVA_HOME_21_BIN"
  [23]="$JAVA_HOME_23_BIN"
)

# Projects: "git_url git_tag java_version"
# Java versions match the experiment dataset (index 9 in the Python project dict).
declare -A PROJECTS=(
  ["commons-validator"]="https://github.com/apache/commons-validator.git rel/commons-validator-1.9.0 11"
  ["jackson-core"]="https://github.com/FasterXML/jackson-core.git jackson-core-2.18.2 11"
  ["jackson-dataformat-xml"]="https://github.com/FasterXML/jackson-dataformat-xml jackson-dataformat-xml-2.18.2 11"
  ["jettison"]="https://github.com/jettison-json/jettison.git jettison-1.5.4 11"
  ["antomology"]="https://github.com/codehaus/antomology.git 557775e1f893dc30b689ee9469344eea6d4dc58b 8"
  ["commons-cli"]="https://github.com/apache/commons-cli.git rel/commons-cli-1.9.0 11"
  ["commons-dbutils"]="https://github.com/apache/commons-dbutils.git rel/commons-dbutils-1.8.1 8"
  ["jra"]="https://github.com/codehaus/jra.git 13cafda39a475af6facadf7e2c037b7b186b72a5 8"
  ["triangle-example"]="https://github.com/hcoles/triangle-example.git  8"
  ["commons-csv"]="https://github.com/apache/commons-csv.git rel/commons-csv-1.14.0 11"
  ["commons-lang"]="https://github.com/apache/commons-lang.git rel/commons-lang-3.17.0 11"
  ["commons-net"]="https://github.com/apache/commons-net.git rel/commons-net-3.11.1 11"
  ["jackson-databind"]="https://github.com/FasterXML/jackson-databind jackson-databind-2.18.2 11"
  ["jterminal"]="https://github.com/grahamedgecombe/jterminal.git 751142d9d2cafbde0ec36a80f73bb25bf297f2f3 11"
  ["XChart"]="https://github.com/knowm/XChart.git xchart-3.8.8 11"
)

# Per-project overrides (default: ./src/main/java and mvn,compile).
# XChart is a multi-module Maven repo; library sources live under xchart/.
declare -A PROJECT_SOURCE_PATH=(
  ["XChart"]="xchart/src/main/java"
)
declare -A PROJECT_BUILD_COMMAND=(
  ["XChart"]="mvn,-pl,xchart,-am,compile"
)

parse_project_entry() {
  local project_name=$1
  IFS=' ' read -r PROJECT_URL PROJECT_TAG PROJECT_JAVA <<< "${PROJECTS[$project_name]}"
  PROJECT_JAVA=${PROJECT_JAVA:-8}
  PROJECT_SOURCE="${PROJECT_SOURCE_PATH[$project_name]:-./src/main/java}"
  PROJECT_BUILD="${PROJECT_BUILD_COMMAND[$project_name]:-mvn,compile}"
}

# Switch JAVA_HOME and PATH for the requested JDK (mirrors set_java_home() in the Python runner).
set_java_home() {
  local version=$1
  local bin_path="${JAVA_HOME_BIN[$version]}"

  if [[ -z "$bin_path" ]]; then
    echo "ERROR: No JDK configured for Java $version"
    echo "Set JAVA_HOME_${version}_BIN or pass --java${version}-bin"
    exit 1
  fi

  if [[ ! -x "$bin_path/java" ]]; then
    echo "ERROR: Java $version not found at $bin_path/java"
    exit 1
  fi

  export JAVA_HOME="${bin_path%/bin}"
  export PATH="$bin_path:$PATH"

  echo "----------------------------------------"
  echo "JAVA_HOME=$JAVA_HOME"
  echo "Using Java $version:"
  java -version 2>&1 | head -n 3
  echo "----------------------------------------"
}

verify_java_homes() {
  echo "Checking required JDK installations..."
  declare -A required_versions=()

  for project in "${!PROJECTS[@]}"; do
    parse_project_entry "$project"
    required_versions[$PROJECT_JAVA]=1
  done

  local missing=false
  for ver in "${!required_versions[@]}"; do
    if [[ ! -x "${JAVA_HOME_BIN[$ver]}/java" ]]; then
      echo "ERROR: Java $ver required but not found at ${JAVA_HOME_BIN[$ver]}/java"
      missing=true
    else
      echo "  Java $ver OK: ${JAVA_HOME_BIN[$ver]}"
    fi
  done

  if [[ "$missing" = true ]]; then
    echo ""
    echo "Install missing JDKs, for example:"
    echo "  sudo apt-get install openjdk-8-jdk openjdk-11-jdk"
    echo "Or set paths explicitly, e.g.:"
    echo "  export JAVA_HOME_11_BIN=/path/to/jdk-11/bin"
    exit 1
  fi
}

# Install system dependencies
install_system_deps() {
  echo "Installing system dependencies..."
  sudo apt-get update -qq
  sudo apt-get install -qq -y \
    git \
    maven \
    openjdk-8-jdk \
    openjdk-11-jdk \
    openjdk-21-jdk \
    graphviz \
    sqlite3 \
    python3-pip \
    python3-venv
}

# Setup Python virtual environment
setup_python_env() {
  if [[ ! -d "$VENV_DIR" ]]; then
    echo "Setting up Python virtual environment..."
    python3 -m venv "$VENV_DIR"
  else
    echo "Using existing virtual environment: $VENV_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  pip install --upgrade pip
}

# Install Python dependencies
install_python_deps() {
  echo "Installing Python dependencies..."
  pip3 install -r ../requirements.txt
}

# Setup MediumDarwin
setup_mediumdarwin() {
  echo "Setting up LittleDarwin..."
  if [[ ! -d littledarwin ]]; then
    git clone "$LITTLEDARWIN_REPO" littledarwin && cd littledarwin && git checkout b6e3fd3db8330b089b376be8485dffd18e687964 && cd ..
  fi
}

# Clone project (skip if directory already exists).
clone_project() {
  local project_name=$1
  local project_url=$2
  local tag=$3

  if [[ -d "$project_name" ]]; then
    echo "Directory $project_name already exists, skipping clone"
    return 0
  fi

  echo -e "\nCloning $project_name..."
  git clone "$project_url" "$project_name"
  cd "$project_name" || return 1
  if [[ -n "$tag" ]]; then
    git checkout tags/"$tag"
  fi
  cd ..
}

# Run mutation analysis
run_mutation_analysis() {
  local project_name=$1
  local java_version=$2

  parse_project_entry "$project_name"

  echo -e "\nProcessing $project_name (Java $java_version)..."
  echo "  source path: $PROJECT_SOURCE"
  echo "  build command: ${PROJECT_BUILD//,/, }"
  set_java_home "$java_version"
  cd "$project_name" || return 1

  if [[ ! -d "$PROJECT_SOURCE" ]]; then
    echo "ERROR: Source path '$PROJECT_SOURCE' is not a directory in $(pwd)"
    echo "       Set PROJECT_SOURCE_PATH[$project_name] in run_mutation_analysis.sh"
    cd ..
    return 1
  fi

  # Avoid nested MediumDarwinResults/... from mv when re-running a project.
  rm -rf LittleDarwinResults MediumDarwinResults

  echo -e "python3 ../../MediumDarwin.py -m --all --build-command \"${PROJECT_BUILD//,/, }\" -q -t . -p $PROJECT_SOURCE"
  python3 ../../MediumDarwin.py \
    --build-command "$PROJECT_BUILD" \
    -m \
    --all \
    -q \
    -t . \
    -p "$PROJECT_SOURCE"

  if [[ ! -d LittleDarwinResults ]]; then
    echo "ERROR: MediumDarwin did not create LittleDarwinResults in $project_name"
    cd ..
    return 1
  fi
  mv LittleDarwinResults MediumDarwinResults

  echo -e "python3 ../littledarwin/LittleDarwin.py -m --all --build-command \"${PROJECT_BUILD//,/, }\" -t . -p $PROJECT_SOURCE"
  python3 ../littledarwin/LittleDarwin.py \
    --build-command "$PROJECT_BUILD" \
    -m \
    --all \
    -t . \
    -p "$PROJECT_SOURCE"

  cd ..
}

# Full pipeline for one project (MD then LD, then optional compare).
process_one_project() {
  local project=$1
  local project_log="${TOOL_PAPER_ROOT}/${LOGS_DIR}/${project}.log"

  mkdir -p "${TOOL_PAPER_ROOT}/${LOGS_DIR}"
  (
    set -e
    cd "$TOOL_PAPER_ROOT"
    activate_venv
    echo "========== $project started at $(date) =========="
    parse_project_entry "$project"
    clone_project "$project" "$PROJECT_URL" "$PROJECT_TAG"
    run_mutation_analysis "$project" "$PROJECT_JAVA"
    if [[ "$COMPARE_RESULTS" = true ]]; then
      compare_operator_results "$project"
    fi
    echo "========== $project finished at $(date) =========="
  ) >> "$project_log" 2>&1
}

compare_one_project() {
  local project=$1
  local project_log="${TOOL_PAPER_ROOT}/${LOGS_DIR}/${project}.log"

  mkdir -p "${TOOL_PAPER_ROOT}/${LOGS_DIR}"
  (
    set -e
    cd "$TOOL_PAPER_ROOT"
    activate_venv
    echo "========== $project compare-only at $(date) =========="
    compare_operator_results "$project"
    echo "========== $project compare finished at $(date) =========="
  ) >> "$project_log" 2>&1
}

# Run a worker across projects; each project runs MD then LD sequentially.
run_projects_parallel() {
  local worker=$1
  shift
  local -a project_list=("$@")
  local project
  local -a pids=()
  local -a pid_names=()
  local -i failed=0
  local -a still_pids=()
  local -a still_names=()
  local i

  # PID-based slot limit (jobs -r is unreliable in non-interactive bash).
  reap_finished_workers() {
    still_pids=()
    still_names=()
    for i in "${!pids[@]}"; do
      if kill -0 "${pids[$i]}" 2>/dev/null; then
        still_pids+=("${pids[$i]}")
        still_names+=("${pid_names[$i]}")
      else
        if wait "${pids[$i]}"; then
          echo "[${pid_names[$i]}] completed OK"
        else
          echo "[${pid_names[$i]}] FAILED (see ${LOGS_DIR}/${pid_names[$i]}.log)"
          failed=1
        fi
      fi
    done
    pids=("${still_pids[@]}")
    pid_names=("${still_names[@]}")
  }

  if (( PARALLEL_JOBS < 1 )); then
    echo "ERROR: --jobs must be >= 1"
    exit 1
  fi

  echo "Running ${#project_list[@]} project(s) with up to $PARALLEL_JOBS in parallel"
  echo "Per-project logs: ${LOGS_DIR}/<project>.log"

  for project in "${project_list[@]}"; do
    while (( ${#pids[@]} >= PARALLEL_JOBS )); do
      reap_finished_workers
      (( ${#pids[@]} >= PARALLEL_JOBS )) && sleep 1
    done
    echo "[$project] starting (log: ${LOGS_DIR}/${project}.log)"
    "$worker" "$project" &
    pids+=($!)
    pid_names+=("$project")
  done

  while (( ${#pids[@]} > 0 )); do
    reap_finished_workers
    (( ${#pids[@]} > 0 )) && sleep 1
  done

  return "$failed"
}

# Export mutations and diff LittleDarwin vs MediumDarwin (-m output).
compare_operator_results() {
  local project_name=$1
  local ld_results="${project_name}/LittleDarwinResults"
  local md_results="${project_name}/MediumDarwinResults"
  local out_dir="${COMPARISONS_DIR}/${project_name}"

  if [[ ! -f "$EXTRACT_SCRIPT" ]]; then
    echo "ERROR: $EXTRACT_SCRIPT not found in $(pwd); cannot compare operators"
    return 1
  fi

  if [[ ! -d "$ld_results" ]]; then
    echo "WARN: Skipping operator comparison for $project_name (missing $ld_results)"
    return 0
  fi
  if [[ ! -d "$md_results" ]]; then
    echo "WARN: Skipping operator comparison for $project_name (missing $md_results)"
    return 0
  fi
  if [[ -d "${md_results}/LittleDarwinResults" ]]; then
    echo "ERROR: ${md_results}/LittleDarwinResults is nested (stale mv). Re-run after:"
    echo "       cd $project_name && rm -rf LittleDarwinResults MediumDarwinResults"
    return 1
  fi

  mkdir -p "$out_dir"
  echo -e "\nComparing mutation operators: $project_name -> $out_dir/"

  if ! python3 "$EXTRACT_SCRIPT" extract "$ld_results" -o "${out_dir}/littledarwin.csv"; then
    echo "ERROR: LittleDarwin extraction failed for $project_name"
    return 1
  fi
  if ! python3 "$EXTRACT_SCRIPT" extract "$md_results" -o "${out_dir}/mediumdarwin.csv"; then
    echo "ERROR: MediumDarwin extraction failed for $project_name"
    return 1
  fi
  if ! python3 "$EXTRACT_SCRIPT" diff \
      "${out_dir}/littledarwin.csv" \
      "${out_dir}/mediumdarwin.csv" \
      -o "$out_dir"; then
    echo "ERROR: Mutation diff failed for $project_name"
    return 1
  fi

  echo "Mutant comparison for $project_name:"
  if [[ -f "${out_dir}/summary.txt" ]]; then
    sed 's/^/  /' "${out_dir}/summary.txt"
  fi
  echo "  Details: ${out_dir}/added_in_mediumdarwin.csv"
  echo "           ${out_dir}/removed_in_mediumdarwin.csv"
}

aggregate_comparison_summaries() {
  local agg="${COMPARISONS_DIR}/summary_all.txt"
  if [[ ! -d "$COMPARISONS_DIR" ]]; then
    return 0
  fi

  {
    echo "LittleDarwin vs MediumDarwin mutant comparison"
    echo "Generated: $(date -Iseconds 2>/dev/null || date)"
    echo ""
  } > "$agg"

  local found=false
  for summary in "${COMPARISONS_DIR}"/*/summary.txt; do
    [[ -f "$summary" ]] || continue
    found=true
    project=$(basename "$(dirname "$summary")")
    {
      echo "========== ${project} =========="
      cat "$summary"
      echo ""
    } >> "$agg"
  done

  if [[ "$found" = true ]]; then
    echo "Combined summary: $agg"
  fi
}

# Help message
show_help() {
    cat <<EOF
MediumDarwin Mutation Analysis Runner

Usage: $0 [options]

Options:
  --compare-only      Only run operator comparison on existing results (no clone/run)
  --jobs N            Run up to N projects in parallel (default: 1, sequential)
  --no-deps           Skip installation of system dependencies
  --no-compare        Skip LittleDarwin vs MediumDarwin operator comparison
  --java8-bin PATH    JDK 8 bin directory (default: $JAVA_HOME_8_BIN)
  --java11-bin PATH   JDK 11 bin directory (default: $JAVA_HOME_11_BIN)
  --java21-bin PATH   JDK 21 bin directory (default: $JAVA_HOME_21_BIN)
  --java23-bin PATH   JDK 23 bin directory (default: $JAVA_HOME_23_BIN)
  --help, -h          Show this help message and exit

Environment variables:
  JAVA_HOME_8_BIN, JAVA_HOME_11_BIN, JAVA_HOME_21_BIN, JAVA_HOME_23_BIN
  PARALLEL_JOBS       Same as --jobs (CLI flag takes precedence)
  Override JDK locations without passing CLI flags.

Default projects analyzed (url tag java_version [source path]):
$(for project in "${!PROJECTS[@]}"; do
    parse_project_entry "$project"
    echo "  - $project (tag: ${PROJECT_TAG:-<default branch>}, Java: $PROJECT_JAVA, source: $PROJECT_SOURCE)"
done)

Example commands:
  $0                          # Run with default settings
  $0 --compare-only           # Re-diff existing LittleDarwinResults / MediumDarwinResults
  $0 --jobs 4                 # Run up to 4 projects at once (MD then LD per project)
  $0 --compare-only --jobs 4  # Compare existing results for 4 projects in parallel
  $0 --no-deps                # Skip system dependencies installation
  $0 --no-compare             # Skip operator CSV export and diff
  $0 --java11-bin /opt/jdk-11/bin

Operator comparisons (unless --no-compare):
  Per project: ${COMPARISONS_DIR}/<project>/summary.txt
               added_in_mediumdarwin.csv, removed_in_mediumdarwin.csv
  Combined:    ${COMPARISONS_DIR}/summary_all.txt
  $0 --help                   # Show this help message
EOF
    exit 0
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --compare-only)
        COMPARE_ONLY=true
        INSTALL_DEPS=false
        shift
        ;;
      --jobs)
        if [[ ! "$2" =~ ^[0-9]+$ ]] || (( "$2" < 1 )); then
          echo "ERROR: --jobs requires a positive integer"
          exit 1
        fi
        PARALLEL_JOBS="$2"
        shift 2
        ;;
      --no-deps)
        INSTALL_DEPS=false
        shift
        ;;
      --no-compare)
        COMPARE_RESULTS=false
        shift
        ;;
      --java8-bin)
        JAVA_HOME_BIN[8]="$2"
        shift 2
        ;;
      --java11-bin)
        JAVA_HOME_BIN[11]="$2"
        shift 2
        ;;
      --java21-bin)
        JAVA_HOME_BIN[21]="$2"
        shift 2
        ;;
      --java23-bin)
        JAVA_HOME_BIN[23]="$2"
        shift 2
        ;;
      --help|-h)
        show_help
        ;;
      *)
        echo "Error: Unknown option $1"
        show_help
        exit 1
        ;;
    esac
  done
}


run_comparisons_only() {
  if [[ ! -f "$EXTRACT_SCRIPT" ]]; then
    echo "ERROR: $EXTRACT_SCRIPT not found in $(pwd)"
    exit 1
  fi

  echo "Compare-only mode: using existing results under each project directory"
  local -a project_list=()
  for project in "${!PROJECTS[@]}"; do
    project_list+=("$project")
  done
  if ! run_projects_parallel compare_one_project "${project_list[@]}"; then
    return 1
  fi
  aggregate_comparison_summaries
}

activate_venv() {
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
}

# Main execution
main() {
  parse_args "$@"

  if [[ "$COMPARE_ONLY" = true && "$COMPARE_RESULTS" = false ]]; then
    echo "ERROR: --compare-only cannot be used with --no-compare"
    exit 1
  fi

  TOOL_PAPER_ROOT="$PWD"
  exec > >(tee -a "$LOG_FILE") 2>&1

  if [[ "$COMPARE_ONLY" = true ]]; then
    echo "Starting operator comparison only at $(date)"
    echo "Parallel jobs: $PARALLEL_JOBS"
    if [[ ! -d "$VENV_DIR" ]]; then
      echo "ERROR: $VENV_DIR not found. Run a full analysis first or create the venv."
      exit 1
    fi
    activate_venv
    if ! run_comparisons_only; then
      echo "ERROR: One or more comparisons failed"
      exit 1
    fi
    echo -e "\nComparison completed."
    echo "Log: $LOG_FILE"
    echo "Per-project logs: ${LOGS_DIR}/"
    echo "Operator comparisons: ${COMPARISONS_DIR}/"
    exit 0
  fi

  echo "Starting mutation analysis at $(date)"
  echo "Parallel jobs: $PARALLEL_JOBS"

  if [ "$INSTALL_DEPS" = true ]; then
    install_system_deps
  else
    echo "Skipping system dependencies installation as requested"
  fi

  verify_java_homes
  setup_mediumdarwin
  setup_python_env
  install_python_deps
  activate_venv

  local -a project_list=()
  for project in "${!PROJECTS[@]}"; do
    project_list+=("$project")
  done

  if run_projects_parallel process_one_project "${project_list[@]}"; then
    :
  else
    echo "ERROR: One or more projects failed"
    exit 1
  fi

  if [[ "$COMPARE_RESULTS" = true ]]; then
    aggregate_comparison_summaries
  fi

  echo -e "\nAnalysis completed."
  echo "Log: $LOG_FILE"
  echo "Per-project logs: ${LOGS_DIR}/"
  if [[ "$COMPARE_RESULTS" = true ]]; then
    echo "Operator comparisons: ${COMPARISONS_DIR}/"
  fi

  echo -e "\nProjects analyzed:"
  for project in "${project_list[@]}"; do
    parse_project_entry "$project"
    echo "- $project (tag: ${PROJECT_TAG:-<default branch>}, Java: $PROJECT_JAVA)"
  done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
