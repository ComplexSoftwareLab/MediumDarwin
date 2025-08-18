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
# OUTPUT_DIR="mutation_results"
LOG_FILE="mutation_analysis.log"
JAVA_VERSION="8"
VENV_DIR=".mediumdarwin_venv"

# Projects to analyze
declare -A PROJECTS=(
  ["commons-dbutils"]="https://github.com/apache/commons-dbutils.git rel/commons-dbutils-1.8.1"
  ["jackson-core"]="https://github.com/FasterXML/jackson-core.git jackson-core-2.18.2"
  ["jettison"]="https://github.com/jettison-json/jettison.git jettison-1.5.4"
  ["commons-cli"]="https://github.com/apache/commons-cli.git rel/commons-cli-1.9.0"
  ["jackson-dataformat-xml"]="https://github.com/FasterXML/jackson-dataformat-xml.git jackson-dataformat-xml-2.18.2"
  ["commons-validator"]="https://github.com/apache/commons-validator.git rel/commons-validator-1.9.0"
)

# Verify Java 8
verify_java() {
  echo "Checking Java version..."
  local java_version=$(java -version 2>&1 | head -n 1 | awk -F '"' '{print $2}')
  
  if [[ $java_version != "1.8"* ]]; then
    echo "ERROR: Java 8 is required but found version $java_version"
    echo "Please install Java 8 and configure it as the default Java version"
    echo "You can use:"
    echo "  sudo apt-get install openjdk-8-jdk"
    echo "  sudo update-alternatives --config java"
    exit 1
  fi
  echo "Java version verified: $java_version"
}

# Install system dependencies
install_system_deps() {
  echo "Installing system dependencies..."
  sudo apt-get update -qq
  sudo apt-get install -qq -y \
    git \
    maven \
    openjdk-8-jdk \
    graphviz \
    sqlite3 \
    python3-pip \
    python3-venv
  
  # Set Java 8 as default
  sudo update-alternatives --set java $(update-alternatives --list java | grep "java-8")
  sudo update-alternatives --set javac $(update-alternatives --list javac | grep "java-8")
}


# Setup Python virtual environment
setup_python_env() {
  echo "Setting up Python virtual environment..."
  python3 -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  
  # Upgrade pip in the virtual environment
  pip install --upgrade pip
}

# Install Python dependencies
install_python_deps() {
  echo "Installing Python dependencies..."
  pip3 install -r ../requirements.txt
}

# Setup MediumDarwin
setup_mediumdarwin() {
  echo "Setting up MediumDarwin..."
  # git clone "$MEDIUMDARWIN_REPO" mediumdarwin
  git clone "$LITTLEDARWIN_REPO" littledarwin
  # cd mediumdarwin || exit
  
  # Build with Java 8
  export JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:bin/java::")
  
  
  # cd ..
}

# Clone project
clone_project() {
  local project_name=$1
  local project_url=$2
  local tag=$3
  
  echo -e "\nCloning $project_name..."
  git clone "$project_url" "$project_name"
  cd "$project_name" || exit
  git checkout tags/"$tag"
  cd ..
}

# Run mutation analysis
run_mutation_analysis() {
  local project_name=$1
  
  echo -e "\nProcessing $project_name..."
  cd "$project_name" || exit
  
  # Build with Java 8
  export JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:bin/java::")
  
  
  # Run analysis
  echo -e "python3 ../../MediumDarwin.py -m --all --build-command \"mvn,compile\" -q -t . -p ./src/main/java"
  python3 ../../MediumDarwin.py \
    --build-command "mvn,compile" \
    -m \
    --all \
    -q \
    -t . \
    -p ./src/main/java \
  
  mv LittleDarwinResults "MediumDarwinResults"

  echo -e "python3 ../littledarwin/LittleDarwin.py -m --all --build-command \"mvn,compile\" -t . -p ./src/main/java"
  python3 ../littledarwin/LittleDarwin.py \
    --build-command "mvn,compile" \
    -m \
    --all \
    -t . \
    -p ./src/main/java \

  cd ..
}

# Help message
show_help() {
    cat <<EOF
MediumDarwin Mutation Analysis Runner

Usage: $0 [options]

Options:
  --no-deps       Skip installation of system dependencies
  --help, -h      Show this help message and exit

Environment variables:
  PROJECTS        Associative array of projects to analyze (format: [project]="url tag")
                  Example: declare -A PROJECTS=([project1]="url1 tag1" [project2]="url2 tag2")

Default projects analyzed:
$(for project in "${!PROJECTS[@]}"; do
    IFS=' ' read -r url tag <<< "${PROJECTS[$project]}"
    echo "  - $project (Tag: $tag)"
done)

Example commands:
  $0                          # Run with default settings
  $0 --no-deps                # Skip system dependencies installation
  $0 --help                   # Show this help message
EOF
    exit 0
}

parse_args() {
  echo "Parsing command line arguments..."
  while [[ $# -gt 0 ]]; do
    echo "Argument: $1"
    case "$1" in
      --no-deps)
        INSTALL_DEPS=false
        shift
        ;;
      --help|-h)
        show_help
        shift
        ;;
      *)
        echo "Error: Unknown option $1"
        show_help
        exit 1
        ;;
    esac
  done
}


# Main execution
main() {
  parse_args "$@"


  exec > >(tee -a "$LOG_FILE") 2>&1
  echo "Starting mutation analysis at $(date)"
  
  verify_java

  if [ "$INSTALL_DEPS" = true ]; then
        install_system_deps
    else
        echo "Skipping system dependencies installation as requested"
  fi
  setup_mediumdarwin
  setup_python_env
  install_python_deps
  # Analyze each project
  for project in "${!PROJECTS[@]}"; do
    IFS=' ' read -r url tag <<< "${PROJECTS[$project]}"
    clone_project "$project" "$url" "$tag"
    run_mutation_analysis "$project"
  done
  
  echo -e "\nAnalysis completed."
  echo "Log: $LOG_FILE"
  
  echo -e "\nProjects analyzed:"
  for project in "${!PROJECTS[@]}"; do
    IFS=' ' read -r url tag <<< "${PROJECTS[$project]}"
    echo "- $project (Tag: $tag)"
  done
}

main "$@"