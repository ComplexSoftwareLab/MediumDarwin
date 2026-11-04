# MediumDarwin

<img src="mediumdarwin/assets/banner.svg" alt="MediumDarwin — Mutation testing for Java" width="520">

MediumDarwin is a mutation testing tool for Java. It generates mutants, runs the project's build and tests against them, and writes a mutation score.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.16893737.svg)](https://doi.org/10.5281/zenodo.16893737)

The tool is licensed under GPL-3.0. See `LICENSE`.

## Install

```
git clone https://github.com/ComplexSoftwareLab/MediumDarwin.git
cd MediumDarwin
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Java, and Maven, Gradle, or Ant, must already be on `PATH`.

## Run

From this repository, point `-p` at the Java sources and `-t` at the project directory that contains the build file. Commands are comma-separated.

```
python MediumDarwin.py -m -b -p src/main/java -t . -c mvn,test --timeout 120
```

`-m` generates mutants. `-b` compiles and tests them. `--timeout` is the per-mutant limit in seconds.

Gradle and Ant use the same flags. Pass the build tool's command to `-c`. If compilation and tests are separate commands, pass the test command with `--test-command`. For Ant, set `--test_target_name` and `--junit_target_name` when the JUnit target is not the default.

Other flags you will use:

| Flag | Effect |
| --- | --- |
| `-q` | Collect coverage and run only the tests that reach each mutant. |
| `-s` | Build the dynamic subsumption graph. |
| `-e` | Use mutant schemata instead of compiling one mutant at a time. |
| `--all` | Enable every mutation operator. |
| `--timeout SEC` | Per-mutant timeout. The first build is allowed twice this long. |
| `--reset` | Copy the saved originals back over the source tree. |
| `-h` | Full option list. |

A finished run restores each source file from the saved original. If a run stops halfway, `python MediumDarwin.py --reset -p src/main/java -t .` puts the sources back.

## Where results are saved

Everything is written under the build directory (`-t`), in `MediumDarwinResults/`.

```
MediumDarwinResults/
  mutationdatabase.db     SQLite database of files, mutants, and test results
  index.html              Project mutation score
  report.txt              Text summary of the run
  initialbuild.txt        Log of the first build
  test-reports/           Reports from the initial test run
  src/main/java/com/example/App.java/
    original.java         Untouched copy of that source file
    index.html            Per-file score
    0.java                Mutant source
    0.txt                 Build and test log for that mutant
```

The database path can be changed with `--use-alternate-database`. With `-s`, the subsumption graph is also stored in `MediumDarwinResults/` as `subsumption_graph.gml` and `subsumption_graph.net`.
