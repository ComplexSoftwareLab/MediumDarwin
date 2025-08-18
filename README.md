# MediumDarwin
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.16893737.svg)](https://doi.org/10.5281/zenodo.16893737)

This repository serves as the companion code for the research paper "MediumDarwin: LittleDarwin Grows with Performance and Research-oriented Extensions." The project is a work in progress. Depending on the acceptance of pull requests, this repository may eventually be merged with the original [LittleDarwin](https://github.com/aliparsai/LittleDarwin).

MediumDarwin is an advanced mutation testing framework for Java, extending the capabilities of LittleDarwin. It is designed to support both industrial-scale testing and academic research, offering a modular and extensible architecture with several performance and usability enhancements.

[Link to the paper](https://github.com/ComplexSoftwareLab/MediumDarwin/blob/main/tool%20paper/ICSME2025.pdf)

Features
--------
*   **Persistent Storage - This is explained in Section 3.1.**: Uses a relational database to store mutation testing data efficiently.
    
*   **Coverage-Based Test Selection - This is explained in Section 3.2 to reduce test execution time.**: Reduces execution time by selecting only relevant tests.
    
*   **Mutant Schemata - Discussed in Section 3.3.**: Minimizes compilation overhead by consolidating mutants into schemata.
    
*   **Refined Mutation Operators - These are discussed in Section 3.4 and Section 4 to improve mutation effectiveness.**: Avoids non-compilable mutants and generates skipped ones.
    
*   **Dynamic Subsumption Analysis - This is explained in Section 3.5 to identify redundant mutants.**: Constructs subsumption graphs to analyze mutant relationships.

Installation
------------
To install and run the tool:

1.  Clone the repository:

```
git clone https://github.com/ComplexSoftwareLab/MediumDarwin.git
cd MediumDarwin
 ```
2.  Create a virtual environment (optional but recommended):

```
 python3 -m venv venv
 source venv/bin/activate  # On Windows use `venv\Scripts\activate`
 ```

3.  Install dependencies:

```
pip install -r requirements.txt
```

Usage
-----

To run MediumDarwin, from this repository's root folder, use:

```
python MediumDarwin.py -H

Options:
  --reset                    Reset the project to the initial state.
  -m, --mutate              Activate the mutation phase.
  --fail_string STR         String to detect build failure from stdout.
  -b, --build               Activate the build phase.
  -q, --code_coverage       Run code coverage analysis.
  --run_all_tests           Run all tests instead of stopping after the first failure.
  --test_target_name NAME   Ant target name for running tests (default: test).
  --junit_target_name NAME  Ant target name for JUnit (default: internal-test).
  -v, --verbose             Enable verbose output.
  --cleanup CMD             Commands to run after each build.
  -p, --path PATH           Path to source files.
  -t, --build-path PATH     Path to build system working directory.
  -c, --build-command CMD   Build command (comma-separated if multiple).
  --test-path PATH          Path to test project build system directory.
  --test-command CMD        Test command (comma-separated if multiple).
  --initial-build-command CMD  Command for initial build.
  --timeout SEC             Timeout for mutant execution (default: 60).
  --initial-timeout SEC     Timeout for initial build/test phase (default: 2x mutation timeout).
  --use-alternate-database PATH  Path to alternate database.
  --license                 Display license and exit.
  --higher-order INT        Mutation order (default: 1; use -1 for dynamic).
  --jobs-no INT             Number of parallel jobs (default: 1).
  --null-check              Use null check mutation operators.
  --method-level            Use method-level mutation operators.
  --all                     Use all mutation operators.
  --whitelist FILE          Whitelisted packages/files (one per line).
  --blacklist FILE          Blacklisted packages/files (one per line).
  -s, --subsumption         Enable subsumption analysis output.
  -e, --schemata            Enable mutant schemata generation.
  --compile_failure_regex REGEX  Regex to detect compile failures.

Note:
- You can specify either a whitelist or a blacklist, not both.
- If both --build and --mutate are active, it's recommended to run them in separate phases.

Example:
  python MediumDarwin.py -m -b --build-command "mvn,install" --timeout 90

```

This command initiates the help and guides you.


Example
-----
The `tool\ paper/run_mutation_analysis.sh` script downloads multiple open source projects and runs both LittleDarwin and MediumDarwin against them. It provides examples of how to use MediumDarwin and reproduces the results in Table I in the tool paper. 

To run the script:
```
cd ./tool\ paper/
./run_mutation_analysis.sh
```

Licence
--------
This project is licensed under the GNU General Public License v3.0. See the LICENSE file for details.
