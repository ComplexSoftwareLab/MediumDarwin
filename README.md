# MediumDarwin
This repository serves as the companion code for the research paper "MediumDarwin: LittleDarwin Grows with Performance and Research-oriented Extensions." The project is a work in progress. Depending on the acceptance of pull requests, this repository may eventually be merged with the original [LittleDarwin](https://github.com/aliparsai/LittleDarwin).

MediumDarwin is an advanced mutation testing framework for Java, extending the capabilities of LittleDarwin. It is designed to support both industrial-scale testing and academic research, offering a modular and extensible architecture with several performance and usability enhancements.

Features
--------
*   **Persistent Storage**: Uses a relational database to store mutation testing data efficiently.
    
*   **Coverage-Based Test Selection**: Reduces execution time by selecting only relevant tests.
    
*   **Mutant Schemata**: Minimizes compilation overhead by consolidating mutants into schemata.
    
*   **Refined Mutation Operators**: Avoids non-compilable mutants and generates skipped ones.
    
*   **Dynamic Subsumption Analysis**: Constructs subsumption graphs to analyze mutant relationships.

Installation
------------
To install and run the tool:

1.  Clone the repository:

```
git clone https://github.com/yourusername/MediumDarwin.git
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

To run MediumDarwin, use:

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
  python MediumDarwin.py --m -b --build-command "mvn,install" --timeout 90

```

This command initiates the help and guides you.

Liscence
--------
This project is licensed under the GNU General Public License v3.0. See the LICENSE file for details.
