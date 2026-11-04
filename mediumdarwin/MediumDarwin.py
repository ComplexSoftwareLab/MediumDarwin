"""MediumDarwin main orchestration module.

Provides the high-level entry point class `MediumDarwin` that coordinates
mutation generation, build/test execution, and optional subsumption analysis.

This module is invoked by the CLI and can also be used programmatically.
"""

import datetime
import io
import os

# import shelve
import shutil
import subprocess
import sys
import time
from pathlib import Path
import glob
from optparse import OptionParser
from mediumdarwin.SharedFunctions import parse_junit_xml, timeoutAlternative
import importlib_resources as resources

from mediumdarwin import License
from mediumdarwin.LineCoverage import LineCoverage
from mediumdarwin.JavaIO import JavaIO
from mediumdarwin.JavaMutate import JavaMutate, Mutant
from mediumdarwin.SharedFunctions import return_build_file
from mediumdarwin.SharedFunctions import (
    return_D_arguments,
    getCommand,
    detect_build_tool,
    write_selected_tests_file,
    add_gradle_test_selection_via_file,
    add_gradle_isolation,
    prepare_gradle_test_command,
    resolve_sql_db_path,
    ensure_sql_db_parent,
    mutant_test_reports_dir,
)
from mediumdarwin.Database import Database
from mediumdarwin.ConsoleUI import (
    ConsoleUI,
    add_reporting_options,
    apply_verbosity_flags,
    count_pipeline_stages,
)

import networkx as nx

# LittleDarwin modules
from mediumdarwin.JavaParse import JavaParse
from mediumdarwin.ReportGenerator import ReportGenerator

import re


class MediumDarwin:
    """High-level controller for MediumDarwin runs.

    Attributes:
        littleDarwinVersion: Version string for reports.
        sqlDBPath: Path to the SQLite database used for results.
            Overridden by ``--use-alternate-database``.
        MediumDarwinResultsPath: Path to the run results directory.
    """
    littleDarwinVersion = "2.0.0.0"
    sqlDBPath = ""
    MediumDarwinResultsPath = ""

    def find_tests_run(text):
        """Extract the total number of tests run from a Maven/Ant output string.

        Args:
            text: Raw build output (stdout) as a string.

        Returns:
            A list of numeric strings captured from the pattern "Tests run: N".
        """
        pattern = r"Tests run: (\d+)"
        matches = re.findall(pattern, text)
        return matches

    def main(self, mockArgs: list = None):
        """Run the selected phases based on parsed CLI options.

        This method parses arguments, then conditionally runs the mutation
        phase, build phase, and subsumption phase, producing reports
        into the results directory.

        Args:
            mockArgs: Optional list of CLI-like arguments for programmatic use.

        Returns:
            0 on success; may terminate the process when errors are encountered.
        """
        optionParser = OptionParser(
            prog="mediumdarwin")
        options, filterType, filterList, higherOrder = self.parseCmdArgs(
            optionParser, mockArgs
        )
        self.ui = ConsoleUI.from_options(options)
        self.ui.set_stage_total(count_pipeline_stages(options, schemata=False))
        self.ui.banner()

        self.MediumDarwinResultsPath = os.path.join(
            options.buildPath, "MediumDarwinResults"
        )
        self.sqlDBPath = resolve_sql_db_path(options)
        ensure_sql_db_parent(self.sqlDBPath)
        # *****************************************************************************************************************
        # ---------------------------------------- mutant generation phase ------------------------------------------------
        # *****************************************************************************************************************

        if options.isMutationActive:
            self.mutationPhase(options, filterType, filterList, higherOrder)

        # *****************************************************************************************************************
        # ---------------------------------------- test suite running phase -----------------------------------------------
        # *****************************************************************************************************************

        if options.isBuildActive:
            self.buildPhase(options)

        if options.isSubsumptionActive:
            self.subsumptionAnalysisPhase(options)
        # if neither build nor mutation phase is active, let's help the user.
        if not (
            options.isBuildActive
            or options.isMutationActive
            or options.isSubsumptionActive
        ):
            optionParser.print_help()
            self.ui.info(
                "\nExample:\n  MediumDarwin -m -b -t ./ -p ./src/main -c mvn,clean,test --timeout=120\n"
            )

        return 0

    def mutationPhase(self, options, filterType, filterList, higherOrder):
        """

        :param options:
        :type options:
        :param filterType:
        :type filterType:
        :param filterList:
        :type filterList:
        :param higherOrder:
        :type higherOrder:
        """
        if not hasattr(self, "ui") or self.ui is None:
            self.ui = ConsoleUI.from_options(options)
        # creating our module objects.
        javaIO = JavaIO(options.isVerboseActive)
        javaParse = JavaParse(options.isVerboseActive)
        totalMutantCount = 0
        totalMutationCount = 0

        try:
            assert os.path.isdir(options.sourcePath)
        except AssertionError as exception:
            self.ui.error("Source path must be a directory.")
            sys.exit(1)
        # getting the list of files.
        self.ui.stage("Discovering source files")
        javaIO.listFiles(
            targetPath=os.path.abspath(options.sourcePath),
            buildPath=os.path.abspath(options.buildPath),
            filterType=filterType,
            filterList=filterList,
        )
        fileCounter = 0
        fileCount = len(javaIO.fileList)
        # creating a database for generated mutants. the format of this database is different on different platforms,
        # so it cannot be simply copied from a platform to another.
        densityResultsPath = os.path.join(
            javaIO.targetDirectory, "ProjectDensityReport.csv"
        )
        self.ui.info(f"Source Path: {javaIO.sourceDirectory}")
        self.ui.info(f"Target Path: {javaIO.targetDirectory}")
        self.ui.info(f"Creating Mutation Database: {self.sqlDBPath}")
        self.ui.info(f"Source files: {fileCount}")
        # mutationDatabase = shelve.open(databasePath, "c")

        mutationDatabase2 = Database(self.sqlDBPath)
        mutationDatabase2.create_tables()

        mutantTypeDatabase = dict()
        averageDensityDict = dict()
        if mutationDatabase2 is not None:
            mutationDatabase2.delete_data("mutant")
            mutationDatabase2.delete_data("mutation")

        # Read HOM definitions from file if --mutation-ids-file is specified
        hom_definitions = []
        if options.mutationIdsFile != "***dummy***":
            try:
                with open(options.mutationIdsFile, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        # Skip empty lines and comments
                        if not line or line.startswith('#'):
                            continue
                        try:
                            mutation_id_list = [
                                int(x.strip()) for x in line.split(",") if x.strip()]
                            if mutation_id_list:
                                hom_definitions.append(mutation_id_list)
                        except ValueError:
                            self.ui.warn(
                                f"Invalid format in {options.mutationIdsFile} line {line_num}: {line}")
                            self.ui.warn(
                                "Expected format: comma-separated integers (e.g., '1, 2, 3, 4')")
                            continue
            except FileNotFoundError:
                self.ui.error(
                    f"Error: Mutation IDs file not found: {options.mutationIdsFile}")
                sys.exit(1)
            except Exception as e:
                self.ui.error(
                    f"Error reading mutation IDs file {options.mutationIdsFile}: {e}")
                sys.exit(1)

            if not hom_definitions:
                self.ui.error(
                    f"Error: No valid HOM definitions found in {options.mutationIdsFile}")
                sys.exit(1)

            self.ui.info(
                f"Loaded {len(hom_definitions)} HOM definitions from {options.mutationIdsFile}")
            # Global tracking for HOM generation summary
            generated_homs_global = set()  # Track which HOMs were generated (at least once)
            # Track skipped HOMs: {hom_idx: [list of reasons]}
            skipped_homs_global = {}
        else:
            generated_homs_global = None
            skipped_homs_global = None

        # go through each file, parse it, calculate all mutations, and generate files accordingly.
        mutants = dict()
        self.ui.stage("Generating mutations")
        for srcFile in self.ui.track(
            javaIO.fileList, desc="Generating mutations", unit="file"
        ):
            self.ui.verbose(
                f"({fileCounter + 1}/{fileCount}) Source file: {srcFile}"
            )
            targetList = list()
            mutationDatabase2.insert_file(srcFile)
            try:
                # parsing the source file into a tree.
                sourceCode = javaIO.getFileContent(srcFile)
                tree = javaParse.parse(sourceCode)
                # a = javaParse.tree2JSON_DFS(tree)
                # f = open("C:/img/treetostring.json", "w")
                # f.write(repr(a))
                # f.close()

            except Exception as e:
                self.ui.warn("Error in parsing Java code, skipping the file.")
                sys.stderr.write(str(e))
                continue

            fileCounter += 1

            enabledMutators = ["Traditional"]

            if options.isNullCheck:
                enabledMutators = ["Null"]

            if options.isAll:
                enabledMutators = ["All"]

            if options.isMethodLevel:
                enabledMutators = ["Method"]

            # apply mutations on the tree and receive the resulting mutants as a list of strings, and a detailed
            # list of which operators created how many mutants.

            javaMutate = JavaMutate(
                tree, sourceCode, javaParse, srcFile, options.isVerboseActive
            )
            # gather mutations
            mutantTypes = javaMutate.gatherMutations(
                enabledMutators, mutationDatabase2, totalMutationCount
            )
            self.ui.verbose(
                f"Mutations found in {os.path.basename(srcFile)}: {len(javaMutate.mutations)}"
            )
            for mutantType in mutantTypes.keys():
                if mutantTypes[mutantType] > 0:
                    self.ui.verbose(
                        f"  {mutantType}: {mutantTypes[mutantType]}"
                    )
                mutantTypeDatabase[mutantType] = mutantTypes[
                    mutantType
                ] + mutantTypeDatabase.get(mutantType, 0)
            totalMutationCount += len(javaMutate.mutations)

            # Check if mutation IDs file is requested (takes precedence over single mutation-ids)
            if options.mutationIdsFile != "***dummy***":
                # Process each HOM definition (hom_definitions already loaded before file loop)
                file_mutants = []
                # Collect missing mutation IDs per HOM for this file
                missing_ids_set = set()
                skipped_homs = []  # HOMs with no mutations found in this file
                for hom_idx, mutation_id_list in enumerate(hom_definitions):
                    # Filter mutations to only include those with specified IDs for this HOM
                    selected_mutations = [
                        mut for mut in javaMutate.mutations
                        if mut.mutationID in mutation_id_list
                    ]

                    # Check if all requested mutation IDs were found
                    found_ids = {mut.mutationID for mut in selected_mutations}
                    missing_ids = set(mutation_id_list) - found_ids
                    if missing_ids:
                        missing_ids_set.update(missing_ids)

                    # Skip this HOM if no mutations match (they might be in other files)
                    if not selected_mutations:
                        skipped_homs.append(hom_idx + 1)
                        # Track globally for summary
                        if skipped_homs_global is not None:
                            if hom_idx + 1 not in skipped_homs_global:
                                skipped_homs_global[hom_idx + 1] = []
                            skipped_homs_global[hom_idx + 1].append(
                                f"no mutations in {os.path.basename(srcFile)}")
                        continue

                    # Create a mutant with the selected mutations for this HOM
                    self.ui.verbose(
                        f"Generating HOM {hom_idx + 1}/{len(hom_definitions)} with mutation IDs: {mutation_id_list}")
                    hom_mutant = Mutant(
                        mutantID=totalMutantCount + len(file_mutants),
                        mutationList=selected_mutations,
                        sourceCode=sourceCode,
                    )
                    file_mutants.append(hom_mutant)
                    # Track globally that this HOM was generated
                    if generated_homs_global is not None:
                        generated_homs_global.add(hom_idx + 1)

                # Print aggregated warnings per file
                if missing_ids_set:
                    self.ui.warn(
                        f"Some mutation IDs were not found in this file: {missing_ids_set}")
                if skipped_homs:
                    self.ui.warn(
                        f"{len(skipped_homs)} HOM(s) were skipped in this file (no mutations found): {skipped_homs[:20]}{'...' if len(skipped_homs) > 20 else ''}")

                if file_mutants:
                    mutants[srcFile] = file_mutants
                    javaMutate.mutants = mutants[srcFile]
                else:
                    # No mutants created for this file, skip to next file
                    continue

            # Check if specific mutation IDs are requested (single HOM)
            elif options.mutationIds != "***dummy***":
                # Parse mutation IDs from comma-separated string
                try:
                    mutation_id_list = [int(x.strip())
                                        for x in options.mutationIds.split(",")]
                except ValueError:
                    self.ui.error(
                        f"Error: Invalid mutation IDs format: {options.mutationIds}")
                    self.ui.error("Expected format: comma-separated integers (e.g., '4, 5, 6')")
                    sys.exit(1)

                # Filter mutations to only include those with specified IDs
                selected_mutations = [
                    mut for mut in javaMutate.mutations
                    if mut.mutationID in mutation_id_list
                ]

                # Check if all requested mutation IDs were found
                found_ids = {mut.mutationID for mut in selected_mutations}
                missing_ids = set(mutation_id_list) - found_ids
                if missing_ids:
                    self.ui.warn(
                        f"Some mutation IDs were not found in this file: {missing_ids}")

                # Skip this file if no mutations match (they might be in other files)
                if not selected_mutations:
                    self.ui.verbose(
                        "No mutations with the specified IDs found in this file, skipping...")
                    continue

                # Create a single mutant with the selected mutations
                self.ui.verbose(
                    f"Generating single mutant with mutation IDs: {mutation_id_list}")
                single_mutant = Mutant(
                    mutantID=totalMutantCount,
                    mutationList=selected_mutations,
                    sourceCode=sourceCode,
                )
                mutants[srcFile] = [single_mutant]
                javaMutate.mutants = mutants[srcFile]
            else:
                # Normal mutant generation
                mutants[srcFile] = javaMutate.gatherAllMutantsUpToTheOrderOf(
                    cur_order=1,
                    order=higherOrder,
                    mutations=javaMutate.mutations,
                    generated_mutants=[],
                    id_counter=totalMutantCount,
                )
                javaMutate.mutants = mutants[srcFile]
            # go through all mutant types, and add them in total. also output the info to the user.
            totalMutantCount += len(mutants[srcFile])
            # for each mutant, generate the file, and add it to the list.
            fileRelativePath = os.path.relpath(srcFile, javaIO.sourceDirectory)
            densityReport = javaMutate.aggregateReport(
                self.littleDarwinVersion)
            averageDensityDict[fileRelativePath] = javaMutate.averageDensity
            aggregateComplexity = javaIO.getAggregateComplexityReport(
                javaMutate.mutantsPerMethod,
                javaParse.getCyclomaticComplexityAllMethods(tree),
                javaParse.getLinesOfCodePerMethod(tree),
            )
            # ind = 0
            for mutatedFile in mutants[srcFile]:
                line_numbers = []
                for i in range(len(mutatedFile.mutationList)):
                    mutationDatabase2.insert_mutant(
                        mutant_id=mutatedFile.mutantID,
                        mutation_id=mutatedFile.mutationList[i].mutationID,
                    )
                    line_numbers.append(mutatedFile.mutationList[i].lineNumber)
                mutatedFile.mutateCode()
                targetList.append(
                    (
                        javaIO.generateNewFile(
                            srcFile,
                            mutatedFile,
                            javaMutate.mutantsPerLine,
                            densityReport,
                            aggregateComplexity,
                        ),
                        line_numbers,
                    )
                )

            del javaMutate

        mutationDatabase2.close_connection()
        type_rows = [
            (mutantType, mutantTypeDatabase[mutantType])
            for mutantType in list(mutantTypeDatabase.keys())
            if mutantTypeDatabase[mutantType] > 0
        ]
        self.ui.summary_table(
            "Mutation generation",
            [
                ("Total mutations", totalMutationCount),
                ("Total mutants", totalMutantCount),
            ] + type_rows,
        )

        # Print HOM generation summary if HOM definitions were used
        if generated_homs_global is not None and skipped_homs_global is not None:
            total_loaded = len(hom_definitions)
            total_generated = len(generated_homs_global)
            total_skipped = total_loaded - total_generated
            hom_rows = [
                ("Loaded HOM definitions", total_loaded),
                ("Generated HOMs", total_generated),
                ("Skipped HOMs", total_skipped),
            ]
            if total_skipped > 0:
                never_generated = set(
                    range(1, total_loaded + 1)) - generated_homs_global
                hom_rows.append(
                    ("Never generated", len(never_generated))
                )
                self.ui.verbose(
                    f"HOM IDs never generated: {sorted(list(never_generated))[:50]}"
                )
            self.ui.summary_table("HOM generation", hom_rows)

        if totalMutantCount == 0:
            self.ui.error("No mutants generated? Something must be wrong.")
            sys.exit(6)

        with open(densityResultsPath, "w") as densityReportHandle:
            for key in averageDensityDict.keys():
                densityReportHandle.write(
                    key + "," + str(averageDensityDict[key]) + "\n"
                )

    def _copy_junit_xml_reports(self, replacementFile, buildDir, buildType, mutant_id):
        """Copy JUnit XML reports to mutant-specific directory for subsumption analysis.

        Args:
            replacementFile: Path to the mutant file
            buildDir: Build system working directory
            buildType: Type of build system ("mvn", "ant", or "gradle")
            mutant_id: ID of the mutant
        """
        report_path_for_mutant = replacementFile + "-test_reports"
        os.makedirs(report_path_for_mutant, exist_ok=True)

        try:
            if buildType == "mvn":
                default_reports_dir = os.path.join(
                    buildDir, "target", "surefire-reports")
                if os.path.isdir(default_reports_dir):
                    for xml_file in Path(default_reports_dir).glob("*.xml"):
                        if xml_file.is_file():
                            shutil.copy2(str(xml_file), os.path.join(
                                report_path_for_mutant, xml_file.name))
            elif buildType == "ant":
                possible_dirs = [
                    os.path.join(buildDir, "test-results"),
                    os.path.join(buildDir, "target", "test-results"),
                    buildDir,
                ]
                for possible_dir in possible_dirs:
                    if os.path.isdir(possible_dir):
                        xml_files = list(Path(possible_dir).glob("*.xml"))
                        if xml_files:
                            for xml_file in xml_files:
                                if xml_file.is_file():
                                    shutil.copy2(str(xml_file), os.path.join(
                                        report_path_for_mutant, xml_file.name))
                            break
            elif buildType == "gradle":
                # Prefer reports that were already redirected via our Gradle isolation init script.
                existing = list(Path(report_path_for_mutant).glob("*.xml"))
                if existing:
                    return

                # Otherwise, scope the search to the isolated per-mutant Gradle buildDir to avoid
                # accidentally copying XMLs from other mutants or the initial build.
                isolated_root = Path(
                    buildDir) / "MediumDarwinResults" / "gradle-build" / str(mutant_id)
                search_root = isolated_root if isolated_root.exists() else Path(buildDir)
                for xml_file in search_root.glob("**/build/test-results/**/*.xml"):
                    if xml_file.is_file():
                        shutil.copy2(str(xml_file), os.path.join(
                            report_path_for_mutant, xml_file.name))
        except Exception as e:
            # Silently fail if reports can't be copied - subsumption will handle missing reports
            pass

    def _register_tests_from_initial_build(self, buildDir, buildType, mutationDatabase):
        """Parse initial build test reports and insert test records into the database.

        Args:
            buildDir: Build system working directory
            buildType: Type of build system ("mvn", "ant", or "gradle")
            mutationDatabase: Database instance to insert tests into
        """
        reports = []
        if buildType == "mvn":
            default_reports_dir = os.path.join(
                buildDir, "target", "surefire-reports")
            if os.path.isdir(default_reports_dir):
                reports = list(Path(default_reports_dir).glob("*.xml"))
        elif buildType == "ant":
            for possible_dir in [
                os.path.join(buildDir, "test-results"),
                os.path.join(buildDir, "target", "test-results"),
                buildDir,
            ]:
                if os.path.isdir(possible_dir):
                    candidates = list(Path(possible_dir).glob("*.xml"))
                    if candidates:
                        reports = candidates
                        break
        elif buildType == "gradle":
            reports = list(Path(buildDir).glob(
                "**/build/test-results/**/*.xml"))

        if not reports:
            return

        # Existing test names
        existing = set([row[1] for row in mutationDatabase.fetch_data("test")])

        # Parse and insert
        for xml_path in reports:
            try:
                results = parse_junit_xml(str(xml_path))
            except Exception:
                continue
            for res in results:
                test_name = res[0]
                if test_name and test_name not in existing:
                    mutationDatabase.insert_data(
                        "test", "qualified_name", [test_name])
                    existing.add(test_name)

    def _record_mutant_result(self, mutationDatabase, mutant_id, is_killed,
                              is_build_failure=False, is_timeout=False,
                              is_non_covered=False, test_id=None, time_str="0", message=""):
        """Record mutant test result in the database.

        Args:
            mutationDatabase: Database instance
            mutant_id: ID of the mutant
            is_killed: True if mutant was killed, False if survived
            is_build_failure: True if build failed
            is_timeout: True if timeout occurred
            is_non_covered: True if mutant was not covered
            test_id: Test ID (use Database.NO_INFO if not available)
            time_str: Test execution time as string
            message: Error message if any
        """
        if test_id is None:
            test_id = Database.NO_INFO

        # Determine result code
        if is_build_failure:
            result = Database.RES_ID_BUILD_FAILURE
        elif is_timeout:
            result = Database.RES_ID_TIMEOUT
        elif is_non_covered:
            result = Database.RES_ID_NON_COVERED
        elif is_killed:
            # Default to failure, can be refined with XML
            result = Database.RES_ID_KILLED_BY_FAILURE_MUTANT
        else:
            result = Database.RES_ID_SURVIVED_MUTANT

        # Insert into database
        mutationDatabase.insert_data(
            "mutant_test",
            "mutant_id, test_id, result, time, message",
            [mutant_id, test_id, result, time_str, message]
        )

    def buildPhase(self, options):
        """

        :param options:
        :type options:
        """
        if not hasattr(self, "ui") or self.ui is None:
            self.ui = ConsoleUI.from_options(options)
        # let's tell the user upfront that this may corrupt the source code.
        self.ui.warn("Code can be changed accidentally. Create a backup first.")

        reportGenerator = ReportGenerator(self.littleDarwinVersion)
        self.sqlDBPath = resolve_sql_db_path(options)
        ensure_sql_db_parent(self.sqlDBPath)
        databasePath = os.path.abspath(self.sqlDBPath)
        mutantsPath = os.path.dirname(databasePath)
        assert os.path.isdir(mutantsPath)
        resultsDatabasePath = databasePath + "-results"
        reportGenerator.initiateDatabase(resultsDatabasePath)
        try:
            if os.path.basename(options.buildPath) == "pom.xml":
                assert os.path.isfile(options.buildPath)
                buildDir = os.path.abspath(os.path.dirname(options.buildPath))
            else:
                assert os.path.isdir(options.buildPath)
                buildDir = os.path.abspath(options.buildPath)

        except AssertionError as exception:
            self.ui.error("Build system working directory should be a directory.")
        # check if we have separate test-suite
        if options.testCommand != "***dummy***":
            separateTestSuite = True
            if options.testPath == "***dummy***":
                testDir = buildDir
            else:
                try:
                    if os.path.basename(options.buildPath) == "pom.xml":
                        assert os.path.isfile(options.buildPath)
                        testDir = os.path.abspath(
                            os.path.dirname(options.testPath))
                    else:
                        assert os.path.isdir(options.buildPath)
                        testDir = os.path.abspath(options.testPath)
                except AssertionError as exception:
                    self.ui.error(
                        "Test project build system working directory should be a directory."
                    )

        else:
            separateTestSuite = False
        # try to open the database. if it can't be opened, it means that it does not exist or it is corrupt.
        try:
            # mutationDatabase = shelve.open(databasePath, "r")
            mutationDatabase2 = Database(self.sqlDBPath)
        except Exception:
            self.ui.error(
                "Cannot open mutation database. It may be corrupted or unavailable. Delete all generated files and run the mutant generation phase again."
            )
            sys.exit(2)

        if not mutationDatabase2.has_table("file"):
            self.ui.error(
                "No mutants in "
                + self.sqlDBPath
                + ". Run the mutation phase (-m) before the build phase (-b)."
            )
            mutationDatabase2.close_connection()
            sys.exit(2)

        databaseKeys = mutationDatabase2.fetch_mutated_files()

        mutationDatabaseLength = len(databaseKeys)
        textReportData = list()
        htmlReportData = list()
        fileCounter = 0
        totalMutantCounter = 0

        compile_time = 0
        # initial build check to avoid false results. the system must be able to build cleanly without errors.
        # use build command for the initial build unless it is explicitly provided.
        if options.initialBuildCommand == "***dummy***":
            commandString = getCommand(options.buildCommand)

        else:
            commandString = getCommand(options.initialBuildCommand)
        self.ui.stage(
            f"Initial build (timeout {options.initial_timeout}s)"
        )
        try:
            s_time = time.time()
            with self.ui.status("Running initial build..."):
                processInitialKilled, processInitialExitCode, initialOutput, time_delta = (
                    timeoutAlternative(
                        commandString,
                        workingDirectory=buildDir,
                        timeout=int(options.initial_timeout),
                        failMessage=options.fail_string,
                    )
                )
            compile_time += time.time() - s_time
            # workaround for older python versions
            if processInitialKilled or processInitialExitCode:
                raise subprocess.CalledProcessError(
                    1 if processInitialKilled else processInitialExitCode,
                    commandString,
                    initialOutput,
                )
            with open(
                os.path.abspath(os.path.join(
                    mutantsPath, "initialbuild.txt")), "w"
            ) as contentFile:
                contentFile.write(str(initialOutput))

            # Register tests from initial build (always, not just for subsumption)
            # This ensures tests are available in the database for result recording
            # For separate test suites, also register tests from test directory
            if separateTestSuite:
                testBuildType = detect_build_tool(
                    getCommand(options.testCommand)[0])

                if testBuildType:
                    # Run initial test command to get test reports
                    if options.initialBuildCommand == "***dummy***":
                        testCommandString = getCommand(options.testCommand)
                    else:
                        # Use test command for initial test run
                        testCommandString = getCommand(options.testCommand)

                    try:
                        with self.ui.status("Running initial tests..."):
                            processTestKilled, processTestExitCode, testOutput, time_delta = (
                                timeoutAlternative(
                                    testCommandString,
                                    workingDirectory=testDir,
                                    timeout=int(options.initial_timeout),
                                    failMessage=options.fail_string,
                                )
                            )
                        # Register tests even if some tests fail (non-zero exit code)
                        self._register_tests_from_initial_build(
                            testDir, testBuildType, mutationDatabase2
                        )
                        self.ui.info("Initial tests finished.")
                    except Exception as e:
                        # Try to register tests anyway if reports exist
                        self._register_tests_from_initial_build(
                            testDir, testBuildType, mutationDatabase2
                        )
                        self.ui.warn("Initial tests finished with warnings.")

            # Also register tests from build directory (in case tests run as part of build)
            buildType = detect_build_tool(getCommand(options.buildCommand)[0])

            if buildType:
                self._register_tests_from_initial_build(
                    buildDir, buildType, mutationDatabase2
                )

            # run line coverage and store the results
            line_coverage = None
            if options.isCoverageActive == True:
                self.ui.stage("Collecting test coverage")
                with self.ui.status("Running Clover coverage collection..."):
                    with resources.as_file(
                        resources.files("mediumdarwin")
                        .joinpath("jar")
                        .joinpath("clover_db_extractor.jar")
                    ) as jar_path:
                        buildFile = return_build_file(
                            options.buildCommand.replace(",", " ")
                        )
                        build_cmd0 = getCommand(options.buildCommand)[0]
                        buildType = detect_build_tool(build_cmd0)
                        line_coverage = LineCoverage(
                            project_path=options.buildPath,
                            clover_db_extractor_path=jar_path,
                            build_file_path=buildFile,
                            build_type=build_cmd0,
                            sqlDB_path=self.sqlDBPath,
                            D_args=return_D_arguments(
                                " ".join(getCommand(options.testCommand))
                            ),
                            runAllTests=options.runAllTests,
                            timeout=int(options.initial_timeout),
                        )
                        line_coverage.run_clover(
                            junit_target=options.junitTargetName,
                            test_target=(
                                "test" if buildType in (
                                    "mvn", "gradle") else options.testTargetName
                            ),
                        )
            self.ui.info("Initial build succeeded.")
        except subprocess.CalledProcessError as exception:
            initialOutput = exception.output
            with open(
                os.path.abspath(os.path.join(
                    mutantsPath, "initialbuild.txt")), "w"
            ) as contentFile:
                initialOutput = initialOutput
                contentFile.write(
                    str(initialOutput).replace("\\r\\n", "\n")
                    + "\n Command: "
                    + " ".join(exception.cmd)
                )
            self.ui.error("Initial build failed.")
            self.ui.error(
                "Try building the system manually first to make sure it can be built. "
                + "Take a look at "
                + os.path.abspath(os.path.join(mutantsPath,
                                  "initialbuild.txt"))
                + " to find out why this happened."
            )
            sys.exit(3)
        totalMutantCount = mutationDatabase2.fetch_mutated_files_count()

        startTime = time.time()
        # running the build system for each mutant.
        search_time = 0
        prepare_build_time = 0
        tests_run_dict = dict()
        res_dict = dict()
        self.ui.stage("Executing mutants")
        dash_cm = self.ui.execution_dashboard(
            res_dict, startTime, total=totalMutantCount, desc="Running mutants"
        )
        dash = dash_cm.__enter__()
        try:
            for key in databaseKeys:
                fileCounter += 1
                self.ui.verbose(
                    f"({fileCounter}/{mutationDatabaseLength}) collecting results for {key[0]}"
                )

                mutantCount = key[1]
                mutantCounter = 0

                survivedList = list()
                killedList = list()
                timeoutList = list()
                nonCoveredList = list()
                buildFailureList = list()
                testFailureList = list()

                mutants = mutationDatabase2.fetch_file_mutant(key[0])
                res_dict[key[0]] = {
                    "mutantsList": [str(m[1]) for m in mutants],
                    "survivedList": survivedList,
                    "killedList": killedList,
                    "timeoutList": timeoutList,
                    "nonCoveredList": nonCoveredList,
                    "buildFailureList": buildFailureList,
                    "testFailureList": testFailureList,
                }

                for mutant_file in mutants:

                    processBuildKilled = None
                    processBuildExitCode = None
                    processTestKilled = None
                    processTestExitCode = None
                    replacementFile = os.path.join(
                        mutantsPath,
                        os.path.relpath(
                            os.path.relpath(mutant_file[0]), options.sourcePath
                        ),
                        str(mutant_file[1]) + ".java",
                    )

                    # replace the original file with the mutant
                    shutil.copyfile(replacementFile, key[0])
                    # let's make sure that runOutput is empty, and not None to begin with.
                    runOutput = str()
                    runOutputTest = str()

                    mutantCounter += 1
                    totalMutantCounter += 1
                    #  *************** uncomment for debugging purposes only ***************
                    # if (
                    #     key[0]!= "C:\\Users\\sajja\\Desktop\\THOMAS RESULTS\\commons-collections\\src\\main\\java\\org\\apache\\commons\\collections4\\ArrayStack.java"
                    # ):
                    #     continue

                    commandString = getCommand(options.buildCommand)
                    if separateTestSuite:
                        testCommandString = getCommand(options.testCommand)
                    try:
                        if options.isCoverageActive == False or (
                            options.isCoverageActive == True and separateTestSuite == True
                        ):

                            dash.set_status(
                                f"Mutant {mutant_file[1]} ({os.path.basename(str(key[0]))}): "
                                f"{' '.join(commandString)}"
                            )
                            s_time = time.time()
                            processBuildKilled, processBuildExitCode, runOutput, time_delta = (
                                timeoutAlternative(
                                    commandString,
                                    workingDirectory=buildDir,
                                    timeout=int(options.timeout),
                                    failMessage=options.fail_string,
                                )
                            )
                            compile_time += time.time() - s_time
                        elif (
                            options.isCoverageActive == True and separateTestSuite == False
                        ):

                            lines = mutant_file[1]
                            test_names = []
                            s_time = time.time()
                            test_names = mutationDatabase2.fetch_coverage(
                                key[0], lines)
                            search_time += time.time() - s_time

                            # there is no instrumentation for this line, so we should run all
                            if len(test_names) == 0:
                                test_names = [""]

                            while ("-",) in test_names:
                                test_names.remove(("-",))

                            if len(test_names) != 0:
                                # print(replacementFile + "-test_reports")
                                buildKind = detect_build_tool(commandString[0])
                                if buildKind == "mvn":
                                    commandString.append("-DfailIfNoTests=false")
                                    s_time = time.time()
                                    line_coverage.add_tests_to_pom_xml(
                                        include_tests_file=line_coverage.include_file_add,
                                        report_path=replacementFile + "-test_reports",
                                        covered_tests=test_names,
                                        subsumption=options.isSubsumptionActive,
                                    )
                                    prepare_build_time += time.time() - s_time

                                elif buildKind == "ant":
                                    test_names = mutationDatabase2.fetch_all_coverage()
                                    s_time = time.time()
                                    line_coverage.add_tests_to_build_xml(
                                        junit_target=options.junitTargetName,
                                        report_path=replacementFile + "-test_reports",
                                        covered_tests=test_names,
                                        subsumption=options.isSubsumptionActive,
                                    )
                                    prepare_build_time += time.time() - s_time
                                elif buildKind == "gradle":
                                    # Gradle doesn't support per-run reportDir overrides like Surefire; copy reports after run.
                                    shutil.rmtree(
                                        replacementFile + "-test_reports", ignore_errors=True)
                                    os.makedirs(replacementFile +
                                                "-test_reports", exist_ok=True)
                                    # Determine if test selection is needed
                                    selected_file = None
                                    if options.runAllTests == False and isinstance(test_names, list) and test_names != [""]:
                                        selected_file = write_selected_tests_file(
                                            os.path.join(
                                                mutantsPath,
                                                os.path.relpath(os.path.relpath(
                                                    mutant_file[0]), options.sourcePath),
                                                str(mutant_file[1]) +
                                                ".selected-tests.txt",
                                            ),
                                            test_names,
                                        )
                                    # Use systematic function to prepare command with all necessary flags
                                    commandString = prepare_gradle_test_command(
                                        commandString,
                                        project_path=options.buildPath,
                                        mutant_id=mutant_file[1],
                                        reports_dir=replacementFile + "-test_reports",
                                        selected_tests_file=selected_file,
                                    )
                                s_time = time.time()
                                (
                                    processBuildKilled,
                                    processBuildExitCode,
                                    runOutput,
                                    time_delta
                                ) = timeoutAlternative(
                                    commandString,
                                    workingDirectory=buildDir,
                                    timeout=int(options.timeout),
                                    failMessage=options.fail_string,
                                )
                                compile_time += time.time() - s_time
                                if buildKind == "gradle":
                                    self._copy_junit_xml_reports(
                                        replacementFile=replacementFile,
                                        buildDir=buildDir,
                                        buildType="gradle",
                                        mutant_id=mutant_file[1],
                                    )
                            else:
                                processTestKilled = False
                                processTestExitCode = 0
                                runOutput = "not covered"
                                nonCoveredList.append(
                                    os.path.basename(replacementFile))
                        # raise the same exception as the original check_output.
                        if processBuildKilled or processBuildExitCode:

                            if processBuildKilled:
                                timeoutList.append(
                                    os.path.basename(replacementFile))

                            buildFailureList.append(
                                os.path.basename(replacementFile))
                            raise subprocess.CalledProcessError(
                                1 if processBuildKilled else processBuildExitCode,
                                commandString,
                                runOutput,
                            )

                        if separateTestSuite and options.isCoverageActive == False:
                            dash.set_status(
                                f"Mutant {mutant_file[1]} tests: {' '.join(testCommandString)}"
                            )
                            s_time = time.time()
                            (
                                processTestKilled,
                                processTestExitCode,
                                runOutputTest,
                                time_delta
                            ) = timeoutAlternative(
                                testCommandString,
                                workingDirectory=testDir,
                                timeout=int(options.timeout),
                                failMessage=options.fail_string,
                            )
                            compile_time += time.time() - s_time
                            # raise the same exception as the original check_output.
                            if processTestKilled or processTestExitCode:
                                if processTestKilled:
                                    timeoutList.append(
                                        os.path.basename(replacementFile))

                                out = MediumDarwin.find_tests_run(runOutputTest)
                                out = [int(numeric_string)
                                       for numeric_string in out]
                                if mutant_file[0] not in tests_run_dict:
                                    tests_run_dict[mutant_file[0]] = 0
                                tests_run_dict[mutant_file[0]] += sum(out)
                                testFailureList.append(
                                    os.path.basename(replacementFile))
                                raise subprocess.CalledProcessError(
                                    1 if processTestKilled else processTestExitCode,
                                    commandString,
                                    "\n".join(
                                        [
                                            runOutput,
                                            "-----------------------------------------",
                                            runOutputTest,
                                        ]
                                    ),
                                    "utf-8",
                                )
                        elif separateTestSuite and options.isCoverageActive == True:
                            lines = mutant_file[2]
                            s_time = time.time()
                            test_names = mutationDatabase2.fetch_coverage(
                                key[0], lines)
                            search_time += time.time() - s_time

                            # there is no instrumentation for this line, so we should run all
                            if len(test_names) == 0:
                                test_names = [""]

                            while ("-",) in test_names:
                                test_names.remove(("-",))

                            if len(test_names) != 0:
                                # print(replacementFile + "-test_reports")
                                testKind = detect_build_tool(testCommandString[0])
                                if testKind == "mvn":
                                    testCommandString.append(
                                        "-DfailIfNoTests=false")
                                    s_time = time.time()
                                    line_coverage.add_tests_to_pom_xml(
                                        include_tests_file=line_coverage.include_file_add,
                                        report_path=replacementFile + "-test_reports",
                                        covered_tests=test_names,
                                        subsumption=options.isSubsumptionActive,
                                    )
                                    prepare_build_time += time.time() - s_time
                                elif testKind == "ant":
                                    test_names = mutationDatabase2.fetch_all_coverage()
                                    s_time = time.time()
                                    line_coverage.add_tests_to_build_xml(
                                        junit_target=options.junitTargetName,
                                        report_path=replacementFile + "-test_reports",
                                        covered_tests=test_names,
                                        subsumption=options.isSubsumptionActive,
                                    )
                                    prepare_build_time += time.time() - s_time
                                elif testKind == "gradle":
                                    shutil.rmtree(
                                        replacementFile + "-test_reports", ignore_errors=True)
                                    os.makedirs(replacementFile +
                                                "-test_reports", exist_ok=True)
                                    # Determine if test selection is needed
                                    selected_file = None
                                    if options.runAllTests == False and isinstance(test_names, list) and test_names != [""]:
                                        selected_file = write_selected_tests_file(
                                            os.path.join(
                                                mutantsPath,
                                                os.path.relpath(os.path.relpath(
                                                    mutant_file[0]), options.sourcePath),
                                                str(mutant_file[1]) +
                                                ".selected-tests.txt",
                                            ),
                                            test_names,
                                        )
                                    # Use systematic function to prepare command with all necessary flags
                                    testCommandString = prepare_gradle_test_command(
                                        testCommandString,
                                        project_path=options.buildPath,
                                        mutant_id=mutant_file[1],
                                        reports_dir=replacementFile + "-test_reports",
                                        selected_tests_file=selected_file,
                                    )
                                dash.set_status(
                                    f"Mutant {mutant_file[1]} tests: {' '.join(testCommandString)}"
                                )
                                s_time = time.time()
                                (
                                    processTestKilled,
                                    processTestExitCode,
                                    runOutputTest,
                                    time_delta
                                ) = timeoutAlternative(
                                    testCommandString,
                                    workingDirectory=buildDir,
                                    timeout=int(options.timeout),
                                    failMessage=options.fail_string,
                                )
                                include_file_add = getattr(
                                    line_coverage, "include_file_add", None)
                                if include_file_add and os.path.isfile(include_file_add):
                                    shutil.copy2(
                                        include_file_add,
                                        os.path.join(
                                            mutantsPath,
                                            os.path.relpath(os.path.relpath(
                                                mutant_file[0]), options.sourcePath),
                                            str(mutant_file[1]) + ".include",
                                        ),
                                    )
                                compile_time += time.time() - s_time
                                if testKind == "gradle":
                                    self._copy_junit_xml_reports(
                                        replacementFile=replacementFile,
                                        buildDir=testDir,
                                        buildType="gradle",
                                        mutant_id=mutant_file[1],
                                    )
                                if processTestKilled or processTestExitCode:
                                    if processTestKilled:
                                        timeoutList.append(
                                            os.path.basename(replacementFile))

                                    out = MediumDarwin.find_tests_run(
                                        runOutputTest)
                                    out = [int(numeric_string)
                                           for numeric_string in out]
                                    if mutant_file[0] not in tests_run_dict:
                                        tests_run_dict[mutant_file[0]] = 0
                                    tests_run_dict[mutant_file[0]] += sum(out)
                                    testFailureList.append(
                                        os.path.basename(replacementFile)
                                    )
                                    raise subprocess.CalledProcessError(
                                        1 if processTestKilled else processTestExitCode,
                                        commandString,
                                        "\n".join(
                                            [
                                                runOutput,
                                                "-----------------------------------------",
                                                runOutputTest,
                                            ]
                                        ),
                                        "utf-8",
                                    )
                            else:
                                processTestKilled = False
                                processTestExitCode = 0
                                runOutputTest = "not covered"
                                nonCoveredList.append(
                                    os.path.basename(replacementFile))
                        # if we are here, it means no exceptions happened, so lets add this to our success list.
                        runOutput = (
                            runOutput
                            + "\n ----------------------------------------- \n"
                            + runOutputTest
                        )
                        if nonCoveredList == []:
                            survivedList.append(os.path.basename(replacementFile))
                        elif nonCoveredList[-1] != os.path.basename(replacementFile):
                            survivedList.append(os.path.basename(replacementFile))
                    # putting two exceptions in one except clause, specially when one of them is not defined on some
                    # platforms does not look like a good idea; even though both of them do exactly the same thing.
                    except subprocess.CalledProcessError as exception:
                        runOutput = exception.output
                        # oops, error. let's add this to failure list.

                        killedList.append(os.path.basename(replacementFile))
                        # buildFailureList.append(os.path.basename(replacementFile))

                    targetTextOutputFile = os.path.splitext(replacementFile)[
                        0] + ".txt"
                    targetXMLOutputFile = os.path.splitext(replacementFile)[
                        0] + ".xml"

                    dash.update(advance=1)

                    # writing the build output to disk.
                    with open(targetTextOutputFile, "w") as contentFile:
                        contentFile.write(str(runOutput))
                    if options.isCoverageActive == True:
                        shutil.copyfile(
                            line_coverage.build_file_path, targetXMLOutputFile)

                    # Copy JUnit XML reports when coverage is not active (always, not just for subsumption)
                    # This ensures reports are available for database insertion
                    if options.isCoverageActive == False:
                        # Determine build type from test command if separate test suite, otherwise from build command
                        if separateTestSuite:
                            buildType = detect_build_tool(
                                getCommand(options.testCommand)[0])
                        else:
                            buildType = detect_build_tool(
                                getCommand(options.buildCommand)[0])

                        if buildType:
                            # Determine the correct build directory (use testDir if separate test suite)
                            target_build_dir = testDir if separateTestSuite else buildDir
                            self._copy_junit_xml_reports(
                                replacementFile, target_build_dir, buildType, mutant_file[1]
                            )

                    # Record mutant result in database (always, regardless of subsumption flag)
                    # Determine status based on which list the mutant was added to
                    mutant_filename = os.path.basename(replacementFile)
                    is_killed = False
                    is_build_failure = False
                    is_timeout = False
                    is_non_covered = False

                    # Check status in order of priority (most specific first)
                    if mutant_filename in timeoutList:
                        is_timeout = True
                        is_killed = True  # Timeouts count as killed
                    elif mutant_filename in buildFailureList:
                        is_build_failure = True
                        is_killed = True  # Build failures count as killed
                    elif mutant_filename in testFailureList:
                        is_killed = True  # Test failures count as killed
                    elif mutant_filename in nonCoveredList:
                        is_non_covered = True
                    elif mutant_filename in killedList:
                        is_killed = True
                    # If not in any list, it survived (survivedList check happens in the try block)

                    # Record result - use NO_INFO for test_id if XML reports aren't available
                    # This provides basic killed/survived status even when XML can't be parsed
                    self._record_mutant_result(
                        mutationDatabase2,
                        mutant_file[1],  # mutant_id
                        is_killed=is_killed,
                        is_build_failure=is_build_failure,
                        is_timeout=is_timeout,
                        is_non_covered=is_non_covered,
                        test_id=Database.NO_INFO,  # Will be updated by updateMutationTestTable if XML available
                        time_str="0",
                        message=""
                    )

                    # if there's a cleanup option, execute it. the results will be ignored because we don't want our process
                    #  to be interrupted if there's nothing to clean up.
                    if options.cleanUp != "***dummy***":
                        subprocess.call(getCommand(options.cleanUp), cwd=buildDir)
                        if separateTestSuite:
                            subprocess.call(
                                getCommand(options.cleanUp), cwd=testDir)

                # append the information for this file to the reports.
                textReportData.append(
                    key[0]
                    + ": survived ("
                    + str(len(survivedList))
                    + "/"
                    + str(mutantCount)
                    + ") -> "
                    + str(survivedList)
                    + " - killed ("
                    + str(len(killedList))
                    + "/"
                    + str(mutantCount)
                    + ") -> "
                    + str(killedList)
                    + "\r\n"
                )

                # we are done with the file. let's return it to the original state.
                shutil.copyfile(
                    os.path.join(os.path.dirname(
                        replacementFile), "original.java"),
                    key[0],
                )

                targetHTMLOutputFile = os.path.join(
                    os.path.dirname(replacementFile), "index.html"
                )

                with open(targetHTMLOutputFile, "w") as contentFile:
                    contentFile.write(
                        reportGenerator.generateHTMLReportPerFile(
                            key[0],
                            targetHTMLOutputFile,
                            survivedList,
                            killedList,
                            nonCoveredList,
                            buildFailureList,
                            testFailureList,
                            timeoutList,
                        )
                    )
                # append the information for this file to the reports.
                # 0: file name, 1: survived count, 2: non-covered survived count, 3: killed by build command count, 4: killed by test command, 5: html file name
                htmlReportData.append(
                    [
                        key[0],
                        len(survivedList),
                        len(nonCoveredList),
                        len(buildFailureList),
                        len(testFailureList),
                        targetHTMLOutputFile,
                    ]
                )

        finally:
            dash_cm.__exit__(None, None, None)
        self.ui.stage("Writing HTML reports")
        # write final text report.
        textReportData.append(
            str(datetime.timedelta(seconds=int(time.time() - startTime)))
        )
        textReportData.append("\n")
        textReportData.append(
            "search time: " + str(datetime.timedelta(seconds=int(search_time)))
        )
        textReportData.append("\n")
        textReportData.append(
            "prepare build time: "
            + str(datetime.timedelta(seconds=int(prepare_build_time)))
        )
        textReportData.append("\n")
        textReportData.append(
            "compile time: " +
            str(datetime.timedelta(seconds=int(compile_time)))
        )
        textReportData.append("\n")
        textReportData.append(tests_run_dict.__str__())
        with open(
            os.path.abspath(os.path.join(mutantsPath, "report.txt")), "w"
        ) as textReportFile:
            textReportFile.writelines(textReportData)

        with open(
            os.path.abspath(os.path.join(
                mutantsPath, "tests_run_dict.txt")), "w"
        ) as textReportFile:
            textReportFile.write(tests_run_dict.__str__())
        # write final HTML report.
        targetHTMLReportFile = os.path.abspath(
            os.path.join(mutantsPath, "index.html"))
        with open(targetHTMLReportFile, "w") as htmlReportFile:
            htmlReportFile.writelines(
                reportGenerator.generateHTMLFinalReport(
                    htmlReportData, targetHTMLReportFile
                )
            )

    def subsumptionAnalysisPhase(self, options: object) -> None:
        self.ui.stage("Subsumption analysis")
        mutationDatabase = Database(self.sqlDBPath)
        # Only delete records that will be replaced with detailed test-level results
        # Keep build failures, non-covered, and timeouts as they are
        mutationDatabase.delete_data("mutant_test",
                                     "result!="+str(Database.RES_ID_BUILD_FAILURE) +
                                     " AND result!="+str(Database.RES_ID_NON_COVERED) +
                                     " AND result!="+str(Database.RES_ID_TIMEOUT))

        self.updateMutationTestTable(options, mutationDatabase)
        self.createMutantTestMatrix(options, mutationDatabase)

    def updateMutationTestTable(self, options: object, mutationDatabase, file_name=None, mutant_id=None, fallback_result=None) -> None:
        if file_name == None and mutant_id == None:
            file_muants = mutationDatabase.fetch_mutants(options=options)
        else:
            file_muants = mutationDatabase.fetch_file_mutant_with_id(
                file_name=file_name, mutant_id=mutant_id, options=options)
        tests = mutationDatabase.fetch_data("test")
        test_dict = {}
        for test in tests:
            # At this stage we do not need to have test case method or class separated
            test = list(test)
            test[1] = test[1].replace("$", ".")
            test[1] = test[1].replace("#", ".")
            test_dict[test[1]] = test[0]

        def return_values(file, debug=False):
            '''
            return values to be inserted to the db later.
            '''
            nonlocal test_dict

            if debug:
                print_str = "extracting test data from: " + file
                print("".join(["-"] * len(print_str)))
                print(print_str)
            xml_files.append(file)
            results = parse_junit_xml(file)

            values = []
            for result in results:
                test_res = Database.RES_ID_SURVIVED_MUTANT
                error_msg = ""
                if result[2] != "":
                    error_msg = result[2]
                    test_res = Database.RES_ID_KILLED_BY_FAILURE_MUTANT
                elif result[3] != "":
                    error_msg = result[3]
                    test_res = Database.RES_ID_KILLED_BY_ERROR_MUTANT

                if result[0] in test_dict:
                    values.append((file_mutant[1],
                                   test_dict[result[0]],
                                   test_res,
                                   result[1],
                                   error_msg))
                else:
                    values.append((file_mutant[1],
                                   str(Database.NO_TEST),
                                   test_res,
                                   result[1],
                                   error_msg))
            return values

        fallback_messages = {
            Database.RES_ID_BUILD_FAILURE: "no results found. Most probably compilation error.",
            Database.RES_ID_KILLED_MUTANT: "killed",
            Database.RES_ID_SURVIVED_MUTANT: "survived",
            Database.RES_ID_TIMEOUT: "timeout",
            Database.RES_ID_NON_COVERED: "non-covered",
        }

        for file_mutant in file_muants:
            source_path = getattr(options, "sourcePath", None) if options else None
            directory = mutant_test_reports_dir(
                self.MediumDarwinResultsPath,
                file_mutant[0],
                file_mutant[1],
                source_path=source_path,
                suffix=".java-test_reports",
            )
            xml_files = []
            values = []
            if os.path.isdir(directory):
                for xml_file in glob.glob(str(os.path.join(directory, "**", "*.xml")), recursive=True):
                    values.extend(return_values(xml_file))
            if values:
                mutationDatabase.insert_many(
                    "mutant_test", "mutant_id, test_id, result, time, message", values)
            else:
                result = (
                    fallback_result
                    if fallback_result is not None
                    else Database.RES_ID_BUILD_FAILURE
                )
                mutationDatabase.insert_data(
                    "mutant_test",
                    "mutant_id, test_id, result, time, message",
                    [
                        file_mutant[1],
                        Database.NO_INFO,
                        result,
                        "0",
                        fallback_messages.get(result, ""),
                    ],
                )
        # use this sql query to get the records of the mutants that have caused compilation errors:
        # SELECT * FROM mutant_test join mutant on mutant.id=mutant_test.mutant_id join mutation on mutation.id=mutant.mutation_id join mutation_operator on mutation_operator.id=mutation.mutation_operator_id WHERE result=-1;

    def createMutantTestMatrix(self, options: object, mutationDatabase) -> None:
        mutant_tests = mutationDatabase.fetch_data(
            "mutant_test", "*", "result!=" +
            str(Database.RES_ID_SURVIVED_MUTANT) +
            " AND result!="+str(Database.RES_ID_BUILD_FAILURE) +
            " AND result!="+str(Database.RES_ID_NON_COVERED)
        )  # exclude surviving and build failure and non-covered ones
        mutant_test_dict = {}
        test_mutant_dict = {}
        for mutant_test in mutant_tests:
            if mutant_test[0] not in mutant_test_dict:
                mutant_test_dict[mutant_test[0]] = set()
            mutant_test_dict[mutant_test[0]].add(mutant_test[1])
            if mutant_test[1] not in test_mutant_dict:
                test_mutant_dict[mutant_test[1]] = set()
            test_mutant_dict[mutant_test[1]].add(mutant_test[0])
        G = nx.DiGraph()
        mutant_ids = list(mutant_test_dict.keys())
        for mutant in self.ui.track(
            mutant_ids, desc="Building subsumption graph", unit="mutant"
        ):
            for mutant2 in mutant_ids:
                if G.has_node(str(mutant)) == False:
                    G.add_node(str(mutant))
                    G.nodes[str(mutant)]["label"] = str(mutant)

                if G.has_node(str(mutant2)) == False:
                    G.add_node(str(mutant2))
                    G.nodes[str(mutant2)]["label"] = str(mutant2)

                if mutant_test_dict[mutant].issubset(mutant_test_dict[mutant2]):
                    if (
                        str(mutant) != str(mutant2)
                        and G.has_edge(str(mutant), str(mutant2)) == False
                    ):
                        if (
                            mutant_test_dict[mutant] == mutant_test_dict[mutant2]
                        ):  # equal test sets
                            G.add_edge(str(mutant), str(mutant2), color="red")
                            self.ui.verbose(
                                f"[red]{mutant} ---> {mutant2}[/red]"
                            )
                            self.ui.verbose(
                                str(mutant_test_dict[mutant])
                                + " ---> "
                                + str(mutant_test_dict[mutant2])
                            )
                        else:  # subset test sets
                            G.add_edge(str(mutant), str(mutant2), color="blue")
                            self.ui.verbose(
                                f"[blue]{mutant} ---> {mutant2}[/blue]"
                            )
                            self.ui.verbose(
                                str(mutant_test_dict[mutant])
                                + " ---> "
                                + str(mutant_test_dict[mutant2])
                            )

        # Contracting nodes mutates the graph (removes/merges nodes + edges).
        # Iterating NetworkX views while mutating can yield stale (u, v) pairs,
        # which then triggers KeyError when indexing G.edges[u, v].
        #
        # Instead: repeatedly take a snapshot of current "red" edges and contract them.
        changed = True
        while changed:
            changed = False
            red_edges = [(u, v) for (u, v, d) in G.edges(
                data=True) if d.get("color") == "red"]
            if not red_edges:
                break
            for u, v in red_edges:
                if u not in G or v not in G or not G.has_edge(u, v):
                    continue
                # Merge labels before contracting away v into u
                G.nodes[u]["label"] = f"{G.nodes[u].get('label', str(u))}, {G.nodes[v].get('label', str(v))}"
                G = nx.contracted_nodes(G, u, v, self_loops=False)
                changed = True

        TR = nx.transitive_reduction(G)

        # Persist the subsumption graph (with original node ids) in multiple formats
        try:
            nx.write_gpickle(
                TR,
                os.path.join(self.MediumDarwinResultsPath, "dmsg.gpickle"),
            )
        except Exception:
            pass
        try:
            nx.write_graphml(
                TR,
                os.path.join(self.MediumDarwinResultsPath, "dmsg.graphml"),
            )
        except Exception:
            pass
        try:
            nx.write_gexf(
                TR,
                os.path.join(self.MediumDarwinResultsPath, "dmsg.gexf"),
            )
        except Exception:
            pass

        mapping = {}
        for node in TR.nodes:
            if TR.in_degree(node) == 0:
                TR.nodes[node]["color"] = "green"
                self.ui.verbose(
                    f"[green] d({node}) ={G.out_degree(node)}[/green]"
                )
            mapping[node] = G.nodes[node]["label"]

        TR = nx.relabel_nodes(TR, mapping)
        dot_string_alt = nx.nx_pydot.to_pydot(TR).to_string()

        nx.write_gml(
            TR,
            os.path.join(self.MediumDarwinResultsPath,
                         "subsumption_graph.gml"),
            stringizer=str,
        )
        nx.write_pajek(
            TR,
            os.path.join(self.MediumDarwinResultsPath,
                         "subsumption_graph.net"),
        )

        # Also persist the labeled graph in modern formats (optional for downstream tools)
        try:
            nx.write_gpickle(
                TR,
                os.path.join(self.MediumDarwinResultsPath,
                             "dmsg_labeled.gpickle"),
            )
        except Exception:
            pass
        try:
            nx.write_graphml(
                TR,
                os.path.join(self.MediumDarwinResultsPath,
                             "dmsg_labeled.graphml"),
            )
        except Exception:
            pass
        try:
            nx.write_gexf(
                TR,
                os.path.join(self.MediumDarwinResultsPath,
                             "dmsg_labeled.gexf"),
            )
        except Exception:
            pass
        with open(os.path.join(self.MediumDarwinResultsPath, "subsumption_graph.dot"), "w") as file:
            file.write(dot_string_alt)

    def parseCmdArgs(self, optionParser: OptionParser, mockArgs: list = None) -> object:
        """

        :param mockArgs:
        :type mockArgs:
        :param optionParser:
        :type optionParser:
        :return:
        :rtype:
        """
        # parsing input options
        optionParser.add_option(
            "-m",
            "--mutate",
            action="store_true",
            dest="isMutationActive",
            default=False,
            help="Activate the mutation phase.",
        )
        # parsing input options
        optionParser.add_option(
            "--fail_string",
            action="store",
            dest="fail_string",
            default=None,
            help="The string to search in the stdout of the build system to determine if the build has failed.",
        )
        optionParser.add_option(
            "-b",
            "--build",
            action="store_true",
            dest="isBuildActive",
            default=False,
            help="Activate the build phase.",
        )
        optionParser.add_option(
            "-q",
            "--code_coverage",
            action="store_true",
            dest="isCoverageActive",
            default=False,
            help="Run code coverage analysis and exclude tests from mutation.",
        )
        optionParser.add_option(
            "--run_all_tests",
            action="store_true",
            dest="runAllTests",
            default=False,
            help="Should the tool stop after the first failing test?",
        )
        optionParser.add_option(
            # "-ttn",
            "--test_target_name",
            action="store",
            dest="testTargetName",
            default="test",
            help="Set the test target name for ant.",
        )
        optionParser.add_option(
            # "-jtn",
            "--junit_target_name",
            action="store",
            dest="junitTargetName",
            default="internal-test",
            help="Set the junit target name for ant.",
        )
        optionParser.add_option(
            "-v",
            "--verbose",
            action="store_true",
            dest="isVerboseActive",
            default=False,
            help="Verbose output.",
        )
        optionParser.add_option(
            "-p",
            "--path",
            action="store",
            dest="sourcePath",
            default=os.path.dirname(os.path.realpath(__file__)),
            help="Path to source files.",
        )
        optionParser.add_option(
            "--mutation-ids-file",
            action="store",
            dest="mutationIdsFile",
            default="***dummy***",
            help="Path to a file containing multiple HOM definitions, one per line. Each line should contain comma-separated mutation IDs (e.g., '1, 2, 3, 4' on first line, '5, 6, 7' on second line).",
        )
        optionParser.add_option(
            "-t",
            "--build-path",
            action="store",
            dest="buildPath",
            default=os.path.dirname(os.path.realpath(__file__)),
            help="Path to build system working directory.",
        )
        optionParser.add_option(
            "-c",
            "--build-command",
            action="store",
            dest="buildCommand",
            default="mvn,test",
            help="Command to run the build system. If it includes more than a single argument, they should be seperated by comma. For example: mvn,install",
        )
        optionParser.add_option(
            "--test-path",
            action="store",
            dest="testPath",
            default="***dummy***",
            help="path to test project build system working directory",
        )
        optionParser.add_option(
            "--test-command",
            action="store",
            dest="testCommand",
            default="***dummy***",
            help="Command to run the test-suite. If it includes more than a single argument, they should be seperated by comma. For example: mvn,test",
        )
        optionParser.add_option(
            "--initial-build-command",
            action="store",
            dest="initialBuildCommand",
            default="***dummy***",
            help="Command to run the initial build.",
        )
        optionParser.add_option(
            "--timeout",
            type="int",
            action="store",
            dest="timeout",
            default=60,
            help="Timeout value for the build process.",
        )
        optionParser.add_option(
            "--cleanup",
            action="store",
            dest="cleanUp",
            default="***dummy***",
            help="Commands to run after each build.",
        )
        optionParser.add_option(
            "--use-alternate-database",
            action="store",
            dest="alternateDb",
            default="***dummy***",
            help="Path to alternative database.",
        )
        optionParser.add_option(
            "--license",
            action="store_true",
            dest="isLicenseActive",
            default=False,
            help="Output the license and exit.",
        )
        optionParser.add_option(
            "--higher-order",
            type="int",
            action="store",
            dest="higherOrder",
            default=1,
            help="Define order of mutation. Use -1 to dynamically adjust per class.",
        )
        optionParser.add_option(
            "--null-check",
            action="store_true",
            dest="isNullCheck",
            default=False,
            help="Use null check mutation operators.",
        )
        optionParser.add_option(
            "--method-level",
            action="store_true",
            dest="isMethodLevel",
            default=False,
            help="Use method level mutation operators.",
        )
        optionParser.add_option(
            "--all",
            action="store_true",
            dest="isAll",
            default=False,
            help="Use all mutation operators.",
        )
        optionParser.add_option(
            "--whitelist",
            action="store",
            dest="whitelist",
            default="***dummy***",
            help="Analyze only included packages or files defined in this file (one package name or path to file per line).",
        )
        optionParser.add_option(
            "--blacklist",
            action="store",
            dest="blacklist",
            default="***dummy***",
            help="Analyze everything except packages or files defined in this file (one package name or path to file per line).",
        )

        optionParser.add_option(
            "-s",
            "--subsumption",
            action="store_true",
            dest="isSubsumptionActive",
            default=False,
            help="Subsumption analysis output.",
        )
        optionParser.add_option(
            "--initial-timeout",
            type="int",
            action="store",
            dest="initial_timeout",
            help="Timeout value for the initial test/build process (default is double the mutation timeout).",
        )
        optionParser.add_option(
            "--mutation-ids",
            action="store",
            dest="mutationIds",
            default="***dummy***",
            help="Comma-separated list of mutation IDs to generate a single mutant with (e.g., '4, 5, 6').",
        )
        add_reporting_options(optionParser)
        if mockArgs is None:
            (options, args) = optionParser.parse_args()
        else:
            (options, args) = optionParser.parse_args(args=mockArgs)
        apply_verbosity_flags(options)

        if options.initial_timeout is None:
            options.initial_timeout = int(options.timeout) * 2

        if options.whitelist != "***dummy***" and options.blacklist != "***dummy***":
            print("You can either define a whitelist or a blacklist but not both.")
            sys.exit(4)
        filterList = None
        filterType = None
        if options.whitelist != "***dummy***" and os.path.isfile(options.whitelist):
            with io.open(options.whitelist, mode="r", errors="replace") as contentFile:
                filterList = [l.strip() for l in contentFile.readlines()]
                filterType = "whitelist"
        if options.blacklist != "***dummy***" and os.path.isfile(options.blacklist):
            with io.open(options.blacklist, mode="r", errors="replace") as contentFile:
                filterList = [l.strip() for l in contentFile.readlines()]
                filterType = "blacklist"
        if filterList is not None:
            filterList = [_f for _f in filterList if _f]
        if options.isLicenseActive:
            License.outputLicense()
            sys.exit(0)
        if options.higherOrder <= 1 and options.higherOrder != -1:
            higherOrder = 1
        else:
            higherOrder = options.higherOrder
        # there is an upside in not running two phases together. we may include the ability to edit some mutants later.
        if options.isBuildActive and options.isMutationActive:
            print(
                "it is strongly recommended to do the analysis in two different phases.\n\n"
            )
        return options, filterType, filterList, higherOrder
