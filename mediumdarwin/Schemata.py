import sys
import io
import networkx as nx
import dill
import time
import datetime
import re
import itertools
from mediumdarwin.JavaMutate import Mutation
from unicurses import *
from pathlib import Path
import importlib_resources as resources
from joblib import Parallel, delayed, cpu_count
from optparse import OptionParser
from antlr4.tree.Tree import TerminalNodeImpl
from colorama import Fore, Style
from antlr4 import Token
from mediumdarwin.LineCoverage import LineCoverage
from mediumdarwin import License
from mediumdarwin.JavaIO import JavaIO
from mediumdarwin.JavaParse import JavaParse
from mediumdarwin.JavaMutate import JavaMutate, LogicalOperatorReplacement, ConditionalOperatorReplacement, HOM
from mediumdarwin.Database import Database
from mediumdarwin.JavaParser import JavaParser
from graphviz import Source
from mediumdarwin.SharedFunctions import *
from mediumdarwin.JavaMutate import (
    recursiveCloneANTLRNodeAndItsChildren,
    recursiveCloneANTLRNodeAndItsChildren,
    replaceNodes,
    findNodeAt,
    findNodesWithMutationID
)


def parseCmdArgs(optionParser: OptionParser, mockArgs: list = None) -> object:
    """

    :param mockArgs:
    :type mockArgs:
    :param optionParser:
    :type optionParser:
    :return:
    :rtype:
    """

    optionParser.add_option(
        "--reset",
        action="store_true",
        dest="reset",
        default=False,
        help="Reset the project by returning to the initial state.",
    )
    # parsing input options
    optionParser.add_option(
        "-m",
        "--mutate",
        action="store_true",
        dest="isMutationActive",
        default=False,
        help="Activate the mutation phase.",
    )

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
        "--test_target_name",
        action="store",
        dest="testTargetName",
        default="test",
        help="Set the test target name for ant.",
    )

    optionParser.add_option(
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
        "--cleanup",
        action="store",
        dest="cleanUp",
        default="***dummy***",
        help="Commands to run after each build.",
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
        help="Timeout value for the mutants.",
    )

    optionParser.add_option(
        "--initial-timeout",
        type="int",
        action="store",
        dest="initial_timeout",
        help="Timeout value for the initial test/build process (default is double the mutation timeout).",
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
        "--jobs-no",
        type="int",
        action="store",
        dest="numberOfJobs",
        default=1,
        help="Choose the number of jobs that you want to have for the purpose of parallelization.",
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
        "-e",
        "--schemata",
        action="store_true",
        dest="isSchemataActive",
        default=False,
        help="Mutant Schemata.",
    )

    optionParser.add_option(
        "--compile_failure_regex",
        action="store",
        dest="compile_failure_regex",
        default=r".*\[(\d+),(\d+)\] error:.*",
        help="Regex to detect compile failures in schemata generation. It should match compile errors and contain three groups: 1) the path to the java file with the error, 2) the line number, and 3) the column number."
",
    )
    optionParser.add_option(
        "-H",
        "--help-me",
        action="store_true",
        dest="help_me",
        default=False,
        help="print help.",
    )

    if mockArgs is None:
        (options, args) = optionParser.parse_args()
    else:
        (options, args) = optionParser.parse_args(args=mockArgs)

    if options.help_me:
        print(r"""
              Usage: script.py [options]

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
                --compile_failure_regex REGEX  Regex to detect compile failures in schemata generation. It should match compile errors and contain three groups: 1) the path to the java file with the error, 2) the line number, and 3) the column number.

              
              Note:
              - You can specify either a whitelist or a blacklist, not both.
              - If both --build and --mutate are active, it's recommended to run them in separate phases.
              
              Example:
                MediumDarwin.py -m -b --build-command "mvn,install" --timeout 90
              """)
        sys.exit(0)

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
    if options.higherOrder < 1:  # and options.higherOrder != -1:
        print("Order cannot be smaller than 1.")
        sys.exit(4)
    else:
        higherOrder = options.higherOrder
    # there is an upside in not running two phases together. we may include the ability to edit some mutants later.
    if options.isBuildActive and options.isMutationActive:
        print(
            "it is strongly recommended to do mutant generation, mutant execution, and subsumption analysis in different phases.\n\n"
        )
    return options, filterType, filterList, higherOrder


class Schemata:
    littleDarwinVersion = "0.10.7"
    clean_time = 0
    compile_time = 0
    test_time = 0

    def subsumptionAnalysisPhase(self, options: object) -> None:
        mutationDatabase = Database(self.sqlDBPath)
        mutationDatabase.delete_data("mutant_test")

        self.updateMutationTestTable(options, mutationDatabase)
        self.createMutantTestMatrix(options, mutationDatabase)

    def updateMutationTestTable(self, options: object, mutationDatabase, file_name=None, mutant_id=None) -> None:
        if file_name == None and mutant_id == None:
            file_muants = mutationDatabase.fetch_mutants()
        else:
            file_muants = mutationDatabase.fetch_file_mutant_with_id(
                file_name=file_name, mutant_id=mutant_id)
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

        for file_mutant in file_muants:
            fileRelativePath = os.path.join(
                self.LittleDarwinResultsPath,
                os.path.relpath(file_mutant[0], options.sourcePath),
            )
            directory = str(
                os.path.join(
                    fileRelativePath,
                    str(file_mutant[1]) + "-test_reports",
                )
            )
            xml_files = []
            if os.path.exists(directory):
                values = []
                for xml_file in glob(str(os.path.join(directory, "**", "*.xml")), recursive=True):
                    values_ = return_values(xml_file)
                    values.extend(values_)
                mutationDatabase.insert_many(
                    "mutant_test", "mutant_id, test_id, result, time, message", values)
            else:
                mutationDatabase.insert_data(
                    "mutant_test",
                    "mutant_id, test_id, result, time, message",
                    [
                        file_mutant[1],
                        Database.NO_INFO,
                        Database.RES_ID_BUILD_FAILURE,
                        "0",
                        "no results found. Most probably compilation error.",
                    ],
                )
        # use this sql query to get the records of the mutants that have caused compilation errors:
        # SELECT * FROM mutant_test join mutant on mutant.id=mutant_test.mutant_id join mutation on mutation.id=mutant.mutation_id join mutation_operator on mutation_operator.id=mutation.mutation_operator_id WHERE result=-1;

    def createMutantTestMatrix(self, options: object, mutationDatabase) -> None:
        mutant_tests = mutationDatabase.fetch_data(
            "mutant_test", "*", "result!=" +
            str(Database.RES_ID_SURVIVED_MUTANT) +
            " AND result!="+str(Database.RES_ID_BUILD_FAILURE) +
            " AND result!="+str(Database.RES_ID_UNCOVERED)
        )  # exclude surviving and build failure and uncovered ones
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
        for mutant in mutant_test_dict.keys():
            for mutant2 in mutant_test_dict.keys():
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
                            print(
                                Fore.RED + str(mutant) +
                                " ---> " + str(mutant2),
                            )
                            print(
                                str(mutant_test_dict[mutant])
                                + " ---> "
                                + str(mutant_test_dict[mutant2])
                            )
                            print(Style.RESET_ALL)
                        else:  # subset test sets
                            G.add_edge(str(mutant), str(mutant2), color="blue")
                            print(
                                Fore.BLUE + str(mutant) +
                                " ---> " + str(mutant2),
                            )
                            print(
                                str(mutant_test_dict[mutant])
                                + " ---> "
                                + str(mutant_test_dict[mutant2])
                            )
                            print(Style.RESET_ALL)
                        print("-----------------------------------")

        for node in G.nodes:
            for edge in G.edges(node):
                if G.edges[edge[0], edge[1]]["color"] == "red":
                    G.nodes[edge[0]]["label"] = (
                        G.nodes[edge[0]]["label"] + ", " +
                        G.nodes[edge[1]]["label"]
                    )
                    G = nx.contracted_nodes(
                        G, edge[0], edge[1], self_loops=False)

        TR = nx.transitive_reduction(G)

        mapping = {}
        for node in TR.nodes:
            if TR.in_degree(node) == 0:
                TR.nodes[node]["color"] = "green"
                print(Fore.GREEN + " d(" + str(node) + ") =" +
                      str(G.out_degree(node)))
            mapping[node] = G.nodes[node]["label"]

        print(Style.RESET_ALL)
        TR = nx.relabel_nodes(TR, mapping)
        dot_string_alt = nx.nx_pydot.to_pydot(TR).to_string()

        nx.write_gml(
            TR,
            os.path.join(self.LittleDarwinResultsPath,
                         "subsumption_graph.gml"),
            stringizer=str,
        )
        nx.write_pajek(
            TR,
            os.path.join(self.LittleDarwinResultsPath,
                         "subsumption_graph.gml"),
        )
        with open(os.path.join(self.LittleDarwinResultsPath, "subsumption_graph.dot"), "w") as file:
            file.write(dot_string_alt)

    def run_test(
        self,
        mutant_id: int,
        mutation: list,
        test_command: list,
        source_directory: str,
        targetTextOutputFile: str = "",
        coverage: bool = False,
        file: str = "",
        timeout=120,
        fail_message="FAILED",
        debug=False,
    ):
        """
        A wrapper function to run the test command in parallel

        mutation: the list of the mutations to be activated;
        test_command: the test command to be executed;
        source_directory: the project's directory
        """
        (
            process_test_killed,
            process_test_exit_code,
            run_output_test,
            time_delta
        ) = timeoutAlternative(
            commandString=test_command.copy(),
            workingDirectory=source_directory,
            timeout=timeout,
            failMessage=fail_message,
            activeMutants=mutation,
        )
        file_name = return_build_file(" ".join(test_command))
        backupFile = None
        buildType = ""
        root_, file_ = os.path.split(targetTextOutputFile)
        path = Path(root_)
        if test_command[0].endswith("mvn"):
            buildType = "mvn"
        elif test_command[0].endswith("ant"):
            buildType = "ant"
        if file_name == None:
            if buildType == "ant":
                file_name = os.path.join(source_directory, "build.xml")
                backupFile = os.path.join(
                    path.absolute(),
                    str(mutant_id) + ".build.xml",
                )
            elif buildType == "mvn":
                file_name = os.path.join(source_directory, "pom.xml")
                backupFile = os.path.join(
                    path.absolute(),
                    str(mutant_id) + ".pom.xml",
                )
        else:
            if buildType == "ant":
                backupFile = os.path.join(
                    path.absolute(),
                    str(mutant_id) + ".build.xml",
                )
            elif buildType == "mvn":
                backupFile = os.path.join(
                    path.absolute(),
                    str(mutant_id) + ".pom.xml",
                )
        if debug:
            print("mutation: " + repr(mutation))
            print("test command: " + " ".join(test_command))
        if file_name == None or backupFile == None:
            print("build file not found no backup is taken")
        else:
            if coverage:
                if debug:
                    print("moving: " + file_name + " -> " + backupFile)
                shutil.move(file_name, backupFile)
            else:
                if debug:
                    print("copying: " + file_name + " -> " + backupFile)
                shutil.copy(file_name, backupFile)
        with open(targetTextOutputFile, "w") as contentFile:
            contentFile.write(" ".join(test_command) + "\n\r")
            contentFile.write(str(run_output_test))
        if process_test_killed or process_test_exit_code:
            if debug:
                print(f"killed: {mutation}")
            return (mutant_id, mutation, Database.RES_ID_KILLED_MUTANT, file, time_delta)
        else:
            if debug:
                print(f"survived: {mutation}")
            return (mutant_id, mutation, Database.RES_ID_SURVIVED_MUTANT, file, time_delta)

    def return_class_body(self, tree):
        """
        returns ClassBodyContext nodes of the AST tree
        """
        class_bodies = []
        parents = [tree]
        for parent in parents:
            if isinstance(parent, JavaParser.ClassBodyContext) or isinstance(parent, JavaParser.InterfaceBodyContext):
                class_bodies.append(parent)
            else:
                try:
                    parents.extend(parent.getChildren())
                except AttributeError:
                    pass
        return class_bodies

    def return_body_node(self, tree):
        """
        returns ClassBodyContext nodes of the AST tree
        """
        body_id = -1
        parents = [tree]
        for parent in parents:
            if isinstance(parent, JavaParser.MethodBodyContext) or isinstance(parent, JavaParser.ConstructorBodyContext):
                body_id = parent.children[0].nodeIndex
                return body_id
            elif isinstance(parent, JavaParser.ClassBodyDeclarationContext) and (parent.getText().startswith("static{")):
                body_id = parent.children[1].nodeIndex
                return body_id
            elif isinstance(parent, JavaParser.LambdaBodyContext):
                if isinstance(parent.children[0], JavaParser.BlockContext):
                    body_id = parent.children[0].nodeIndex
                    return body_id
            else:
                try:
                    parents.append(parent.parentCtx)
                except AttributeError:
                    pass
        return body_id

    def return_method_body(self, tree, java_parse):
        """
        returns ClassBodyContext nodes of the AST tree
        """
        method_bodies = []
        parents = [tree]
        for parent in parents:
            if isinstance(parent, JavaParser.MethodBodyContext) or isinstance(parent, JavaParser.ConstructorBodyContext):
                method_bodies.append(parent.children[0])
                parents.extend(parent.children[0].getChildren())
            elif isinstance(parent, JavaParser.ClassBodyDeclarationContext) and (parent.getText().startswith("static{")):
                method_bodies.append(parent.children[1])
                parents.extend(parent.children[1].getChildren())
            elif isinstance(parent, JavaParser.LambdaBodyContext):
                # method_ = java_parse.seekFirstMatchingParent(
                #     parent, JavaParser.MethodBodyContext)
                # class_ = java_parse.seekFirstMatchingParent(
                #     parent, JavaParser.ClassBodyDeclarationContext)
                # if (method_ is None and (class_ is None or (not class_.getText().startswith("static{")))):
                if isinstance(parent.children[0], JavaParser.BlockContext):
                    method_bodies.append(parent.children[0])
            else:
                try:
                    parents.extend(parent.getChildren())
                except AttributeError:
                    pass
        return method_bodies

    def find_error_ant(self, text):
        """
        Find the line and the column which causes error in Ant (Javac) output
        text: the output of the test command
        """
        # line = []
        # iter_ = re.finditer(".*\[javac\]\s+(.*\.java):(\d+):\s+error(.*)", text)
        # for m in iter_:
        #     line.append(m.end())
        ant_regex = r".*\[javac\]\s+(.*\.java):(\d+):\s+error(.*)\n.*\[javac\](.*)\n.*\[javac\](.*)\^"
        ls = re.findall(ant_regex, text)
        ls_new = []
        for l in ls:
            ls_new.append((int(l[1]), len(l[4]) - 1))
        return ls_new

    def find_error_mvn(self, text, regex=r".*\[(\d+),(\d+)\] error:.*"):
        """
        Find the line and the column which causes error in Maven output
        text: the output of the test command
        """
        ls = list(set(re.findall(regex, text)))
        ls_new = []
        ls_new = []
        for l in ls:
            l_new = list(l)
            l_new[0] = l_new[0]
            l_new[1] = int(l_new[1])
            l_new[2] = int(l_new[2])-1
            ls_new.append(l_new)
        return ls_new

    def mutant_schemata_generation(
        self,
        options,
        filterType,
        filterList,
        mutation_database,
        debug=True
    ):
        if mutation_database is None:
            print("Error opening databases.")
            return
        build_command = getCommand(options.buildCommand)
        enabledMutators = "Traditional"

        if options.isNullCheck:
            enabledMutators = "Null"
        if options.isAll:
            enabledMutators = "All"
        if options.isMethodLevel:
            enabledMutators = "Method"

        java_io = JavaIO(options.isVerboseActive)

        try:
            assert os.path.isdir(options.sourcePath)
        except AssertionError as exception:
            print("Source path must be a directory.")
            sys.exit(1)

        # Parsing the source file into a tree.
        java_io.listFiles(
            targetPath=os.path.abspath(options.sourcePath),
            buildPath=os.path.abspath(options.buildPath),
            filterType=filterType,
            filterList=filterList,
        )

        fileCounter = 0
        fileCount = len(java_io.fileList)

        # refreshing the database
        mutation_database.delete_data("mutant")
        mutation_database.delete_data("mutation")

        densityResultsPath = os.path.join(
            java_io.targetDirectory, "ProjectDensityReport.csv"
        )
        print("Source Path: ", java_io.sourceDirectory)
        print("Target Path: ", java_io.targetDirectory)
        print("Creating Mutation Database: ", self.sqlDBPath)

        file_mutations_dict = {}
        compile_mutations_files = set()

        build_failures = set()
        mutantTypes_project = dict()
        trees_dict = dict()
        last_mutation_id = 0

        for file in java_io.fileList:
            print(
                "\n(" + str(fileCounter + 1) + "/" +
                str(fileCount) + ") Source file: ",
                file,
            )

            file_mutations_dict[file] = dict()

            file_id = mutation_database.fetch_data(
                "file", columns="id", condition=f"name = '{file}'"
            )[0][0]

            try:
                # parsing the source file into a tree.
                java_parse = JavaParse(options.isVerboseActive)
                source_code = java_io.getFileContent(file)
                tree = java_parse.parse(source_code)
            except Exception as e:
                print("Error in parsing Java code, skipping the file.")
                sys.stderr.write(str(e))
                continue
            fileCounter += 1

            # -----------------------------------------------------
            targetDir = os.path.join(
                self.LittleDarwinResultsPath,
                os.path.relpath(file, options.sourcePath),
            )
            if not os.path.exists(targetDir):
                os.makedirs(targetDir, exist_ok=True)
            if not os.path.isfile(os.path.join(targetDir, "original.java")):
                shutil.copyfile(file, os.path.join(targetDir, "original.java"))
            # -----------------------------------------------------
            mutantsPerLine = dict()
            mutantsPerMethod = dict()
            mutationOperators = list()

            # ? for debugging purposes
            if (debug):
                json_ = java_parse.tree2JSON_DFS(tree)
                f = open("C:/img/treetostring.json", "w")
                f.write(json_)
                f.close()
                java8_mutate_test = JavaMutate(
                    sourceTree=tree,
                    sourceCode=source_code,
                    javaParseObject=java_parse,
                    file_name=file,
                    verbose=True,
                    mutantTypes=[enabledMutators]
                )
                mutantTypes = java8_mutate_test.gatherMutations(
                    metaTypes=[enabledMutators],
                )
                print("--> TEST Mutations found: ", sum(mutantTypes.values()))
                for mutantType in mutantTypes.keys():
                    if mutantTypes[mutantType] > 0:
                        print("---->", mutantType, ":",
                              mutantTypes[mutantType])
                print("-------------------------------------")

            mutantTypes_file = dict()

            java8_mutate = JavaMutate(
                sourceTree=tree,
                sourceCode=source_code,
                javaParseObject=java_parse,
                file_name=file,
                verbose=options.isVerboseActive,
                metaTypes=[enabledMutators]
            )
            # gather all the nodes that can be mutated
            (node_dict, depth_node, overloaded) = java8_mutate.gatherMutableNodes(
                javaParseObject=java_parse,
                metaTypes=[enabledMutators], mutationOperator=MutationOperator)
            # sort the nodes by depth so that we can mutate them from bottom to top
            depths = list(depth_node.keys())
            depths.sort(reverse=True)

            for node_depth in depths:
                depth_node[node_depth] = list(depth_node[node_depth])
                for nodeInd in depth_node[node_depth]:
                    # get the node to be mutated
                    main_node = java_parse.getNode(tree, nodeInd)
                    body_ind = self.return_body_node(main_node)
                    # ? for debugging purposes
                    if (debug):
                        print("nodeIndex: "+str(nodeInd))
                    node_dict[nodeInd] = sorted(
                        node_dict[nodeInd], key=lambda x: str(type(x)).lower(), reverse=False)
                    for mO in node_dict[nodeInd]:
                        mO.mutation_id = last_mutation_id
                        mO.generateMutations()
                        precedence_ordered_mutations = list()
                        # In LogicalOperatorReplacement and ConditionalOperatorReplacement we need to generate all possible combinations as they change the precedence
                        if (isinstance(mO, LogicalOperatorReplacement) or isinstance(mO, ConditionalOperatorReplacement)):
                            precedence_ordered_mutations = java8_mutate.all_mutations_pairs(
                                order=len(mO.mutations), mutations=mO.mutations)
                        mutantTypes_project[mO.mutatorType] = len(mO.mutations) if not mO.mutatorType in mutantTypes_project.keys(
                        ) else mutantTypes_project[mO.mutatorType]+len(mO.mutations)

                        mutantTypes_file[mO.mutatorType] = len(mO.mutations) if not mO.mutatorType in mutantTypes_file.keys(
                        ) else mutantTypes_file[mO.mutatorType]+len(mO.mutations)
                        if (precedence_ordered_mutations):
                            is_overloaded = False
                            for mutation in mO.mutations:
                                if nodeInd in overloaded:
                                    is_overloaded = True
                                    compile_mutations_files.add(
                                        (file, mutation))
                                    mutationIDs_tmp = JavaParse.findNodeInSubtree(tree, mutation.nodeID).mutationID if hasattr(
                                        JavaParse.findNodeInSubtree(tree, mutation.nodeID), "mutationID") else ""
                                    mutationIDs_tmp += "," + \
                                        str(mutation.mutationID) if (
                                            mutationIDs_tmp != "") else str(mutation.mutationID)
                                    JavaParse.findNodeInSubtree(
                                        tree, mutation.nodeID).mutationID = mutationIDs_tmp
                                operator_id = mutation_database.fetch_data(
                                    "mutation_operator",
                                    "id",
                                    f"name = '{mutation.mutatorType}'",
                                )
                                operator_id = operator_id[0][0]

                                new_node_jsons = []
                                new_node_ids = []
                                new_node_types = []
                                for i in range(len(mutation.mutation_dict[mutation.mutationID][0])):
                                    new_node_ids.append(
                                        mutation.mutation_dict[mutation.mutationID][0][i])
                                    new_node_jsons.append(
                                        java_parse.tree2JSON_DFS(mutation.mutation_dict[mutation.mutationID][1][i]))
                                    new_node_types.append(
                                        mutation.mutation_dict[mutation.mutationID][2][i])

                                mutation_database.insert_mutation(
                                    mutation.mutationID,
                                    file_id,
                                    mutation.nodeID,
                                    mutation.startPos,
                                    mutation.endPos,
                                    mutation.lineNumber,
                                    mutation.replacementText,
                                    mutation_operator_id=operator_id,
                                    node_json=new_node_jsons,
                                    new_node_id=new_node_ids,
                                    new_node_type=new_node_types,
                                    is_compile_time=1 if is_overloaded else 0,
                                    object_=dill.dumps(
                                        mutation) if is_overloaded else None
                                )
                                # mutations_in_node[tuple_str].mutationID = tuple_str
                                file_mutations_dict[file][mutation.mutationID] = mutation
                                last_mutation_id += 1
                                if mutation.lineNumber in mutantsPerLine.keys():
                                    mutantsPerLine[mutation.lineNumber] += 1
                                else:
                                    mutantsPerLine[mutation.lineNumber] = 1
                            if is_overloaded:
                                continue
                            mutations_in_node = dict()
                            # -1: the original node
                            mutations_in_node["-1"] = recursiveCloneANTLRNodeAndItsChildren(
                                main_node)
                            for mutation_order in precedence_ordered_mutations:
                                for mutation_tuples in mutation_order:
                                    hom = HOM(list(mutation_tuples))
                                    tuple_str = ""
                                    # I use this so that when I generate higher order mutants I replace them in the same tree
                                    for mutation_ind in range(len(mutation_tuples)):
                                        mutation = mutation_tuples[mutation_ind]
                                        operator_id = mutation_database.fetch_data(
                                            "mutation_operator",
                                            "id",
                                            f"name = '{mutation.mutatorType}'",
                                        )
                                        operator_id = operator_id[0][0]

                                        tuple_str += "," + \
                                            str(mutation.mutationID) if (
                                                tuple_str != "") else str(mutation.mutationID)
                                    mutations_in_node[tuple_str] = recursiveCloneANTLRNodeAndItsChildren(
                                        hom.return_mutated_node(main_node, list(mutation_tuples)))
                                    hom.return_original_node(
                                        main_node, list(mutation_tuples))
                                    mutations_in_node[tuple_str].mutationID = tuple_str
                                    mutations_in_node[tuple_str].hom = hom
                            tmp = java8_mutate.returnTernary(
                                mutations_in_node, main_node.mutationType if hasattr(main_node, "mutationType") else 0, body_ind)
                            # ? for debugging purposes
                            if (debug):
                                print("final expression: " +
                                      tmp.getText())
                            tmp.parentCtx = main_node.parentCtx
                            replaceNodes(main_node, tmp)
                        else:
                            for mutation in mO.mutations:
                                # getting the pointer to the node to be mutated
                                # we need the expression after the return keyword (example: return x)
                                if mutation.mutatorType == "NullifyReturnValue":
                                    replaced_node = JavaParse.findNodeInSubtree(tree, JavaParse.findNodeInSubtree(
                                        tree, mutation.nodeID).getChild(1).nodeIndex)
                                elif mutation.mutatorType == "NullifyInputVariable":  # we need the block of the method
                                    replaced_node = JavaParse.findNodeInSubtree(tree, JavaParse.findNodeInSubtree(
                                        tree, mutation.nodeID).methodBody().block().nodeIndex)
                                else:  # all other cases
                                    replaced_node = JavaParse.findNodeInSubtree(
                                        tree, mutation.nodeID)
                                body_ind = self.return_body_node(replaced_node)
                                # ? for debugging purposes
                                if (debug):
                                    print(
                                        "type: "+str(type(replaced_node)))
                                    print("mutation type: " +
                                          mutation.mutatorType)

                                operator_id = mutation_database.fetch_data(
                                    "mutation_operator",
                                    "id",
                                    f"name = '{mutation.mutatorType}'",
                                )
                                operator_id = operator_id[0][0]

                                new_node_jsons = []
                                new_node_ids = []
                                new_node_types = []
                                for i in range(len(mutation.mutation_dict[mutation.mutationID][0])):
                                    new_node_ids.append(
                                        mutation.mutation_dict[mutation.mutationID][0][i])
                                    new_node_jsons.append(
                                        java_parse.tree2JSON_DFS(mutation.mutation_dict[mutation.mutationID][1][i]))
                                    new_node_types.append(
                                        mutation.mutation_dict[mutation.mutationID][2][i])

                                mutation_database.insert_mutation(
                                    mutation.mutationID,
                                    file_id,
                                    mutation.nodeID,
                                    mutation.startPos,
                                    mutation.endPos,
                                    mutation.lineNumber,
                                    mutation.replacementText,
                                    mutation_operator_id=operator_id,
                                    node_json=new_node_jsons,
                                    new_node_id=new_node_ids,
                                    new_node_type=new_node_types,
                                    is_compile_time=1 if ((hasattr(replaced_node, "mutationType") and replaced_node.mutationType ==
                                                          JavaParse.MUTATION_TYPE_COMPILE_TIME) or mutation.nodeID in overloaded) else 0,
                                    object_=dill.dumps(mutation) if ((hasattr(replaced_node, "mutationType") and replaced_node.mutationType ==
                                                                      JavaParse.MUTATION_TYPE_COMPILE_TIME) or mutation.nodeID in overloaded) else None
                                )

                                file_mutations_dict[file][mutation.mutationID] = mutation

                                last_mutation_id += 1
                                if mutation.lineNumber in mutantsPerLine.keys():
                                    mutantsPerLine[mutation.lineNumber] += 1
                                else:
                                    mutantsPerLine[mutation.lineNumber] = 1

                                mutations_in_node = dict()
                                skipTernary = False

                                # -1: the original node
                                mutations_in_node["-1"] = recursiveCloneANTLRNodeAndItsChildren(
                                    replaced_node)
                                # Compile time mutations are not ternary
                                if (hasattr(replaced_node, "mutationType") and replaced_node.mutationType == JavaParse.MUTATION_TYPE_COMPILE_TIME) or mutation.nodeID in overloaded:
                                    compile_mutations_files.add(
                                        (file, mutation))
                                else:
                                    mutation.apply_mutation_in_place(
                                        replaced_node)
                                # copy the mutated expression
                                copiedParent = recursiveCloneANTLRNodeAndItsChildren(
                                    replaced_node)

                                tuple_str = copiedParent.mutationID if hasattr(
                                    copiedParent, "mutationID") else ""
                                tuple_str += "," + \
                                    str(mutation.mutationID) if (
                                        tuple_str != "") else str(mutation.mutationID)
                                # copiedParent.mutationID = mutation.mutationID
                                copiedParent.mutationID = tuple_str
                                mutations_in_node[tuple_str] = copiedParent
                                if (hasattr(replaced_node, "mutationType") and replaced_node.mutationType == JavaParse.MUTATION_TYPE_COMPILE_TIME) or mutation.nodeID in overloaded:
                                    skipTernary = True
                                else:
                                    # reverse mutate after copying the parent
                                    mutation.apply_reverse_mutation_in_place(
                                        replaced_node)
                                # ? for debugging purposes
                                if (debug):
                                    print("original_Version: " +
                                          replaced_node.getText())
                                    print("mutated_Version: " +
                                          copiedParent.getText())
                                #! **********************************************
                                if (skipTernary):
                                    tmp = copiedParent
                                else:
                                    # For RemoveMethod and NullifyInputVariable we use if instead of ternary
                                    if (mutation.mutatorType == "RemoveMethod" or mutation.mutatorType == "NullifyInputVariable"):
                                        blockContext = JavaParser.BlockContext(
                                            replaced_node)
                                        bracet1 = TerminalNodeImpl(Token())
                                        bracet1.symbol.text = "{"
                                        blockContext.addChild(bracet1)
                                        temp = JavaMutate.returnConditional(
                                            mutationID=mutation.mutationID, node=copiedParent, original_nodeIndex=JavaMutate.return_class_id(replaced_node), contextID=replaced_node.contextID)
                                        blockContext.addChild(temp)
                                        for ind in range(len(replaced_node.children)):
                                            if ind != 0 and ind != (len(replaced_node.children)-1):
                                                blockContext.addChild(
                                                    replaced_node.children[ind])
                                        bracet2 = TerminalNodeImpl(Token())
                                        bracet2.symbol.text = "}"
                                        blockContext.addChild(bracet2)
                                        tmp = blockContext
                                    else:
                                        tmp = java8_mutate.returnTernary(
                                            mutations_in_node, replaced_node.mutationType if hasattr(replaced_node, "mutationType") else 0, body_ind)
                                # ************************************************************************************************
                                # ? for debugging purposes
                                if (debug):
                                    print("final expression: "+tmp.getText())
                                # tmp.mutationID = mutation.mutationID
                                tmp.parentCtx = replaced_node.parentCtx
                                replaceNodes(replaced_node, tmp)

            print("--> Mutations found: ", sum(mutantTypes_file.values()))
            for mutantType in mutantTypes_file.keys():
                if mutantTypes_file[mutantType] > 0:
                    print("---->", mutantType, ":",
                          mutantTypes_file[mutantType])
            print("-------------------------------------")
            # adding getEnv and ld variables to methods
            class_bodies = self.return_class_body(tree)
            for class_body in class_bodies:
                if (class_body.contextID == JavaParse.CLASS_BODY_CONTEXT_ID):
                    JavaMutate.add_getEnv(class_body)
            method_bodies = self.return_method_body(tree, java_parse)
            for method_body in method_bodies:
                blockContext = JavaMutate.add_ld_variable(
                    method_body)
                blockContext.parentCtx = method_body.parentCtx
                replaceNodes(method_body, blockContext)

            # saving the file
            with open(file, "w",) as f:
                # the last node is <EOF>
                del tree.children[-1]
                f.write(java_parse.getText(tree))

            # report generation
            java8_mutate.mutationOperators = list(mutationOperators)
            densityReport = java8_mutate.aggregateReport_schemata(
                self.littleDarwinVersion, file_mutations_dict[file].values(
                ), mutantsPerLine
            )

            aggregateComplexity = java_io.getAggregateComplexityReport(
                mutantsPerMethod,
                java_parse.getCyclomaticComplexityAllMethods(tree),
                java_parse.getLinesOfCodePerMethod(tree),
            )

            if (
                mutantsPerLine is not None
                and densityReport is not None
                and aggregateComplexity is not None
            ):
                densityPerLineCSVFile = os.path.abspath(
                    os.path.join(targetDir, "MutantDensityPerLine.csv")
                )
                complexityPerMethodCSVFile = os.path.abspath(
                    os.path.join(targetDir, "ComplexityPerMethod.csv")
                )
                densityReportFile = os.path.abspath(
                    os.path.join(targetDir, "aggregate.html")
                )

            if (
                not os.path.isfile(complexityPerMethodCSVFile)
                or not os.path.isfile(densityPerLineCSVFile)
                or not os.path.isfile(densityReportFile)
            ):
                with open(densityPerLineCSVFile, "w") as densityFileHandle:
                    for key in sorted(mutantsPerLine.keys()):
                        densityFileHandle.write(
                            str(key) + "," + str(mutantsPerLine[key]) + "\n"
                        )

                with open(complexityPerMethodCSVFile, "w") as densityFileHandle:
                    for key in sorted(aggregateComplexity.keys()):
                        line = [str(key)]
                        line.extend([str(x) for x in aggregateComplexity[key]])
                        densityFileHandle.write(";".join(line) + "\n")

                with open(densityReportFile, "w") as densityFileHandle:
                    densityFileHandle.write(densityReport)
            trees_dict[os.path.abspath(file)] = tree

        # removing build failure causing mutations
        # running the build command
        while True:
            (
                process_test_killed,
                process_test_exit_code,
                run_output_test,
                time_delta
            ) = timeoutAlternative(
                build_command.copy(),
                workingDirectory=os.path.abspath(options.buildPath),
                timeout=int(options.timeout),
                failMessage=options.fail_string,
            )
            if not process_test_killed and not process_test_exit_code:
                break  # if the build command succeeds
            if debug:
                print("build failure:")
                print(run_output_test)
            # if the build command fails, find the line and the column that causes error
            ls_new = list()
            # find the line and the column that causes error
            if build_command[0] == "ant":
                ls_new = self.find_error_ant(run_output_test)
            # elif build_command[0] == "mvn":
            else:
                ls_new = self.find_error_mvn(
                    run_output_test, options.compile_failure_regex)
            # ls_new.sort()
            if (ls_new == []):
                print(
                    "Schemata compilation failed but the line and the column are not detected. You might want to check the regex. The output is saved to failure_output.txt")
                with open(os.path.abspath(
                    os.path.join(
                        options.buildPath, "LittleDarwinResults", "failure_output.txt"
                    )
                ), "w") as contentFile:
                    contentFile.write(str(run_output_test))
                sys.exit(3)
            matches = set()
            for l in ls_new:
                source_code = java_io.getFileContent(l[0])
                lines = source_code.split('\n')
                row = l[1]-1
                column = l[2]-1
                startPos = column-7
                endPos = column+2
                # Search for the mutation ID
                match = re.search(r"MUT(\d+)\s*\*/",
                                  lines[row][startPos:endPos])
                # If there is no match re-index the start position and try again
                while match is None:
                    startPos -= 1
                    if (startPos < 0):
                        if (row == 0):
                            print("ERROR in detecting the mutant ID!")
                            with open(os.path.abspath(
                                os.path.join(
                                    options.buildPath, "LittleDarwinResults", "failure_output.txt"
                                )
                            ), "w") as contentFile:
                                contentFile.write(str(run_output_test))
                            raise subprocess.CalledProcessError(3,
                                                                self.options.buildCommand.split(
                                                                    ",") if self.options.initialBuildCommand == "***dummy***" else getCommand(self.options.initialBuildCommand),
                                                                run_output_test,
                                                                )
                        else:
                            row = row - 1
                            column = len(lines[row])
                            startPos = column - 7
                            endPos = column
                    match = re.search(
                        r"MUT(\d+)\s*\*/", lines[row][startPos:endPos]
                    )
                matches.add((l[0], int(match.group(1))))
                startPos = startPos - 2
            for match in matches:
                print(str(match[1]), end="-")
                build_failures.add(match[1])
                targetTextOutputFile = str(
                    os.path.join(
                        os.path.join(self.LittleDarwinResultsPath, os.path.relpath(
                            match[0], options.sourcePath)), str(match[1]) + ".txt"
                    )
                )
                with open(targetTextOutputFile, "w") as contentFile:
                    contentFile.write(" ".join(build_command) + "\n\r")
                    contentFile.write(str(run_output_test))
                # find the nodes that have the mutation
                tree = 0
                nodes_ = findNodesWithMutationID(
                    trees_dict[os.path.abspath(match[0])], str(match[1]))
                if debug:
                    for node_ in nodes_:
                        print(node_.getText())
                for node_ in nodes_:
                    if (hasattr(node_, "hom")):
                        # if its a hom node, reverse mutate the mutation which caused the build failure
                        node_.hom.return_original_node(mutated_tree=node_, mutationList=[
                                                       file_mutations_dict[os.path.abspath(match[0])][match[1]]])
                        mutationIDs = str(node_.mutationID).split(",")
                        mutationIDs_ = ""
                        for child_mutationID in mutationIDs:
                            if (child_mutationID == str(match[1])):
                                mutationIDs_ += str(match[1]) + \
                                    "," if mutationIDs_ != "" else str(
                                        match[1])
                        node_.mutationID = mutationIDs_
                    else:
                        # if its a FOM node, reverse mutate the mutation
                        file_mutations_dict[os.path.abspath(match[0])][match[1]].apply_reverse_mutation_in_place(
                            mutated_tree=node_)
                # ? for debugging purposes
                if (debug):
                    print(
                        repr(l)
                        + " : "
                        + str(match[1])
                    )
            # write the schemata file without the build failure causing mutations
            for match in matches:
                with open(
                    match[0],
                    "w",
                ) as f:
                    f.write(java_parse.getText(
                        trees_dict[os.path.abspath(match[0])]))

        for file in java_io.fileList:
            targetDir = os.path.join(
                self.LittleDarwinResultsPath,
                os.path.relpath(file, options.sourcePath),
            )
            if not os.path.exists(targetDir):
                os.makedirs(targetDir, exist_ok=True)
            shutil.copyfile(file, os.path.join(
                targetDir, "mutant_schemata.java"))
            if not os.path.abspath(file) in trees_dict.keys():
                continue
            json_string = java_parse.tree2JSON_DFS(
                trees_dict[os.path.abspath(file)])
            mutation_database.update_file_json(file, json_string)
            shutil.copyfile(os.path.join(targetDir, "original.java"), file)

        print("-------------------------------------")
        print("\nTotal mutations found: ", sum(mutantTypes_project.values()))
        print("Build failure causing mutations found: ", len(build_failures))
        print("Compile time mutations found: ", len(compile_mutations_files))
        for mutantType in mutantTypes_project.keys():
            if mutantTypes_project[mutantType] > 0:
                print("---->", mutantType, ":",
                      mutantTypes_project[mutantType])
        print("-------------------------------------")
        return (
            build_failures,
            file_mutations_dict
        )

    def print_results(self, res_dict, start_time):

        fileCounter = 0
        totalMutantCount = 0
        totalMutantCounter = 0

        for file in res_dict.keys():
            totalMutantCount += len(res_dict[file]["mutantsList"])
            tmp = set.union(set(res_dict[file]["survivedList"]), set(res_dict[file]["killedList"]), set(
                res_dict[file]["uncoveredList"]), set(res_dict[file]["buildFailureList"]), set(res_dict[file]["testFailureList"]))
            totalMutantCounter += len(tmp)
        line_no = 0
        mvaddstr(line_no, 0, " total: " + str(totalMutantCounter) + "/" + str((totalMutantCount)) + " elapsed: " +
                 str(datetime.timedelta(seconds=int(time.time() - start_time))) + " remaining: " + str(
                     datetime.timedelta(
                         seconds=int(
                                    (float(time.time() - start_time) /
                                     (totalMutantCounter if totalMutantCounter != 0 else 1))
                             * float(totalMutantCount - totalMutantCounter)
                         )
                     )
        ))

        line_no += 1
        for file in res_dict.keys():
            fileCounter += 1
            tmp = set.union(set(res_dict[file]["survivedList"]), set(res_dict[file]["killedList"]), set(
                res_dict[file]["uncoveredList"]), set(res_dict[file]["buildFailureList"]), set(res_dict[file]["testFailureList"]))
            current = len(tmp)
            if (current == len(res_dict[file]["mutantsList"])):
                mvdeleteln(line_no, 0)
                mvdeleteln(line_no+1, 0)
                continue
            mvaddstr(line_no, 0, " (" + str(fileCounter) + "/" + str(len(res_dict)) +
                     ") collecting results for "+file)
            line_no += 1
            mvaddstr(line_no, 0, " current: " + str(current) + "/" +
                     str(len(res_dict[file]["mutantsList"])) + " *** survived: " + str(len(res_dict[file]["survivedList"])) +
                     " - killed: " + str(len(res_dict[file]["killedList"])) + " - uncovered: " + str(
                len(res_dict[file]["uncoveredList"])))
            line_no += 1

    def run_mutant_schemata(
        self,
        mutants_dict,
        # build_failures,
        compile_mutations_files,
        mutation_db: Database,
        options,
        debug=False
    ):

        start_time = time.time()
        res_dict = dict()

        JOBS_NO = options.numberOfJobs
        build_command = getCommand(options.buildCommand)
        clean_command = getCommand(options.cleanUp)
        test_command = getCommand(options.testCommand)

        source_directory = os.path.abspath(options.sourcePath)
        build_directory = os.path.abspath(options.buildPath)

        buildType = ""
        if build_command[0].endswith("mvn"):
            buildType = "mvn"
        elif build_command[0].endswith("ant"):
            buildType = "ant"
        buildFile = return_build_file(" ".join(build_command))
        if buildFile == None:
            if buildType == "ant":
                buildFile = os.path.join(build_directory, "build.xml")
            elif buildType == "mvn":
                buildFile = os.path.join(build_directory, "pom.xml")

        # let's tell the user upfront that this may corrupt the source code.
        print("\n\n!!! CAUTION !!!")
        print("Code can be changed accidentally. Create a backup first.\n")

        if options.alternateDb == "***dummy***":
            databasePath = os.path.abspath(
                os.path.join(
                    options.buildPath, "LittleDarwinResults", "mutationdatabase"
                )
            )
        else:
            databasePath = options.alternateDb

        mutantsPath = os.path.dirname(databasePath)
        assert os.path.isdir(mutantsPath)

        java_parse = JavaParse(options.isVerboseActive)
        java_io = JavaIO(options.isVerboseActive)
        java_io.listFiles(
            targetPath=os.path.abspath(source_directory),
            buildPath=os.path.abspath(build_directory),
        )
        function_calls = list()

        # moving schemata to the main directory
        for file in java_io.fileList:
            targetDir = os.path.join(
                self.LittleDarwinResultsPath,
                os.path.relpath(file, options.sourcePath),
            )
            if os.path.isfile(os.path.join(targetDir, "mutant_schemata.java")):
                shutil.copyfile(os.path.join(
                    targetDir, "mutant_schemata.java"), file)
        print("Running mutants...", end=' ')
        compile_mutations_trees = dict()
        compile_mutations_ = dict()
        if len(compile_mutations_files) > 0:
            print("Running compile time mutants...", end=' ')
            for CTM in compile_mutations_files:
                output = mutation_db.fetch_data(
                    "file", "*", f"name = '{CTM[0]}'")
                # source_code = java_io.getFileContent(CTM[0])
                # tree = java_parse.parse(source_code)
                if (CTM[0] in compile_mutations_trees.keys()):
                    continue
                tree = java_parse.Json2Tree(output[0][2])
                compile_mutations_trees[CTM[0]] = tree
            for CTM in compile_mutations_files:
                tree = compile_mutations_trees[CTM[0]]
                expressionContexts = findNodesWithMutationID(
                    tree, str(CTM[1].mutationID))
                compile_mutations_[CTM[1].mutationID] = list()
                for expression in expressionContexts:
                    compile_mutations_[CTM[1].mutationID].append([
                        CTM[1], expression])
        build_failure_mutants = mutation_db.fetch_build_failure_mutants()
        for file in mutants_dict.keys():

            targetDir = os.path.join(
                self.LittleDarwinResultsPath,
                os.path.relpath(file, options.sourcePath),
            )
            res_dict[file] = {"mutantsList": list(mutants_dict[file].keys()), "survivedList": list(), "killedList": list(
            ), "uncoveredList": list(), "buildFailureList": list(), "testFailureList": list()}
            #! antomology has problem with build failures. It reports them both as killed at build and survived
            for record in build_failure_mutants:
                if (record[0] == file):
                    res_dict[record[0]]["killedList"].append(str(record[1]))
                    res_dict[record[0]]["buildFailureList"].append(
                        str(record[1]))
            for mutant_id in mutants_dict[file].keys():
                if str(mutant_id) in res_dict[file]["buildFailureList"]:
                    continue
                subset = mutants_dict[file][mutant_id]
                compile_again = list()
                for mutation in subset:
                    # if the mutant is in the compile mutations list then compile and run it again
                    if mutation in compile_mutations_.keys():
                        compile_again.append(mutation)
                        for i in range(len(compile_mutations_[mutation])):
                            (app_inds, app_nodes) = compile_mutations_[mutation][i][0].apply_mutation_in_place(
                                compile_mutations_[mutation][i][1]
                            )
                            compile_mutations_[mutation][i] = [
                                compile_mutations_[mutation][i][0], compile_mutations_[mutation][i][1], app_inds, app_nodes]
                        # compile_mutations_[mutation][0].apply_mutation_in_place(
                        #     compile_mutations_[mutation][1])
                if len(compile_again) != 0:
                    print(subset, end=" ")
                    # run mutations that need recompilation
                    for c_a in compile_again:
                        with open(
                            file,
                            "w",
                        ) as f:
                            f.write(
                                java_parse.getText(
                                    compile_mutations_trees[file]
                                )
                            )
                    if options.cleanUp != "***dummy***":
                        s_time = time.time()
                        (
                            process_clean_killed,
                            process_clean_exit_code,
                            run_output_clean,
                            time_delta
                        ) = timeoutAlternative(
                            clean_command,
                            workingDirectory=build_directory,
                            timeout=int(options.timeout),
                            failMessage=options.fail_string,
                        )
                        self.clean_time += time.time() - s_time
                    os.makedirs(
                        os.path.join(
                            targetDir,
                            str(mutant_id) + "-test_reports",
                        ),
                        exist_ok=True,
                    )
                    no_test = False
                    buildFile_ = buildFile
                    if options.isCoverageActive:
                        if (buildType == "mvn"):
                            D_args = return_D_arguments(" ".join(test_command))
                        lines = mutation_db.fetch_file_mutant_by_mutation_ID(
                            mutant_id)
                        test_names = list()
                        for line in lines:
                            test_names.extend(
                                mutation_db.fetch_coverage(file, line[2]))
                        # insturmented but not covered
                        uncovered = False
                        while ("-",) in test_names:
                            uncovered = True
                            test_names.remove(("-",))
                        if uncovered:
                            if len(test_names) == 0:
                                res = (mutant_id, subset,
                                       Database.RES_ID_UNCOVERED, file)
                                msg = "uncovered"
                                res_dict[res[3]]["uncoveredList"].append(
                                    str(res[0]))
                                continue
                        no_test = False
                        while ("?",) in test_names:
                            no_test = True
                            test_names.remove(("?",))
                        if no_test:
                            if len(test_names) == 0:
                                if (buildType == "mvn"):
                                    D_args.append("-DskipTests")
                        if (buildType == "mvn"):
                            if (len(test_names) == 0 and not no_test) or (options.runAllTests == True and not no_test):
                                test_names = [""]

                        if (buildType == "ant"):
                            if (len(test_names) == 0 and not no_test) or (options.runAllTests == True and not no_test):
                                # there are no instrumentations so we read all tests
                                test_names = mutation_db.fetch_all_coverage()
                        if buildType == "ant":
                            buildFile_ = os.path.join(
                                build_directory, "build.xml" + str(mutant_id))
                        elif buildType == "mvn":
                            buildFile_ = os.path.join(
                                build_directory, "pom.xml" + str(mutant_id)
                            )
                        shutil.copy2(buildFile, buildFile_)
                        with resources.as_file(
                            resources.files("mediumdarwin")
                            .joinpath("jar")
                            .joinpath("clover_db_extractor.jar")
                        ) as jar_path:
                            line_coverage = LineCoverage(
                                project_path=build_directory,
                                clover_db_extractor_path=jar_path,
                                build_file_path=buildFile_,
                                build_type=buildType,
                                sqlDB_path=self.sqlDBPath,
                                D_args=D_args,
                                runAllTests=options.runAllTests,
                                timeout=int(options.initial_timeout),
                            )
                        includeFile_ = os.path.join(
                            targetDir, "include" + str(mutant_id)
                        )
                        if buildType == "ant":
                            line_coverage._prepare_build_xml(
                                include_file=includeFile_,
                                junit_target=options.junitTargetName,
                                subsumption=options.isSubsumptionActive,
                            )
                            line_coverage.add_tests_to_build_xml(
                                junit_target=options.junitTargetName,
                                report_path=os.path.join(
                                    targetDir, str(mutant_id) + "-test_reports"
                                ),
                                covered_tests=test_names,
                                subsumption=options.isSubsumptionActive,
                            )
                        elif buildType == "mvn":
                            line_coverage._prepare_pom(
                                include_file_add=includeFile_)
                            line_coverage.add_tests_to_pom_xml(
                                include_tests_file=includeFile_,
                                report_path=os.path.join(
                                    targetDir, str(mutant_id) + "-test_reports"
                                ),
                                covered_tests=test_names,
                                subsumption=options.isSubsumptionActive,
                            )
                    test_command_ = test_command.copy()
                    if (no_test):
                        if (buildType == "mvn"):
                            test_command_.extend(D_args)
                    test_command_ = change_build_file(
                        test_command_.copy(), buildFile_
                    )
                    s_time = time.time()
                    (
                        process_test_killed,
                        process_test_exit_code,
                        run_output_test,
                        time_delta
                    ) = timeoutAlternative(
                        test_command_.copy(),
                        workingDirectory=build_directory,
                        timeout=int(options.timeout),
                        failMessage=options.fail_string,
                        activeMutants=subset,
                    )
                    self.test_time += s_time - time.time()
                    targetTextOutputFile = str(
                        os.path.join(
                            targetDir, str(mutant_id) + ".txt"
                        )
                    )
                    if buildType == "ant":
                        backupFile = os.path.join(
                            targetDir,
                            str(mutant_id) + ".build.xml",
                        )
                    elif buildType == "mvn":
                        backupFile = os.path.join(
                            targetDir,
                            str(mutant_id) + ".pom.xml",
                        )
                    if backupFile == None or buildFile_ == None:
                        print("build file not found no backup is taken")
                    else:
                        if options.isCoverageActive:
                            if debug:
                                print("moving: " + buildFile_ +
                                      " -> " + backupFile)
                            shutil.move(buildFile_, backupFile)
                        else:
                            if debug:
                                print("copying: " + buildFile_ +
                                      " -> " + backupFile)
                            shutil.copy(buildFile_, backupFile)
                    if options.isCoverageActive:
                        os.remove(line_coverage.build_file_path + ".bak")
                        del line_coverage
                    with open(targetTextOutputFile, "w") as contentFile:
                        contentFile.write(" ".join(test_command_) + "\n\r")
                        contentFile.write(str(run_output_test))
                    if process_test_killed or process_test_exit_code:
                        if debug:
                            print("killed: " + str(subset))
                        res = (mutant_id, subset,
                               Database.RES_ID_KILLED_MUTANT, file)
                        res_dict[res[3]]["testFailureList"].append(str(res[0]))
                        res_dict[res[3]]["killedList"].append(str(res[0]))
                        msg = "killed"
                        if not options.isCoverageActive or not options.isSubsumptionActive:
                            mutation_db.insert_data(
                                "mutant_test",
                                "mutant_id, test_id, result, time, message",
                                [
                                    res[0],
                                    # if coverage is not active, I use NO_INFO to just have a record in the table
                                    Database.NO_INFO,
                                    Database.RES_ID_KILLED_MUTANT,
                                    str(time_delta),
                                    msg,
                                ],
                            )
                        else:
                            # if coverage is active then uptade the DB
                            self.updateMutationTestTable(
                                options=options, mutationDatabase=mutation_db, file_name=file, mutant_id=mutant_id)
                    else:
                        if debug:
                            print("Survived: " + str(subset))
                        res = (mutant_id, subset,
                               Database.RES_ID_SURVIVED_MUTANT, file)
                        res_dict[res[3]]["survivedList"].append(str(res[0]))
                        msg = "survived"
                        if not options.isCoverageActive or not options.isSubsumptionActive:
                            mutation_db.insert_data(
                                "mutant_test",
                                "mutant_id, test_id, result, time, message",
                                [
                                    res[0],
                                    Database.NO_INFO,
                                    Database.RES_ID_SURVIVED_MUTANT,
                                    str(time_delta),
                                    msg,
                                ],
                            )
                        else:
                            # if coverage is active then uptade the DB
                            self.updateMutationTestTable(
                                options=options, mutationDatabase=mutation_db, file_name=file, mutant_id=mutant_id)
                    # reverse the mutations after running the compile time mutant
                    for c_a in compile_again:
                        # compile_mutations_[mutation][1].reverse_mutation()
                        for i in range(len(compile_mutations_[c_a])):
                            compile_mutations_[c_a][i][0].apply_reverse_mutation_in_place(
                                compile_mutations_[c_a][i][1],
                                compile_mutations_[c_a][i][2],
                                compile_mutations_[c_a][i][3],)

                    schemataFile = os.path.join(
                        self.LittleDarwinResultsPath,
                        os.path.relpath(file, options.sourcePath),
                        "mutant_schemata.java"
                    )
                    if os.path.isfile(schemataFile):
                        shutil.copyfile(
                            schemataFile, file)
                else:
                    test_command_ = test_command.copy()
                    if options.isCoverageActive:
                        buildFile_ = None
                        if buildType == "mvn":
                            D_args = return_D_arguments(" ".join(test_command))
                            buildFile_ = os.path.join(
                                build_directory, "pom.xml" + str(mutant_id)
                            )
                        elif buildType == "ant":
                            buildFile_ = os.path.join(
                                build_directory, "build.xml" + str(mutant_id)
                            )
                        shutil.copy2(buildFile, buildFile_)
                        lines = mutation_db.fetch_file_mutant_by_mutation_ID(
                            mutant_id)
                        test_names = list()
                        for line in lines:
                            test_names.extend(
                                mutation_db.fetch_coverage(file, line[2]))
                        os.makedirs(
                            os.path.join(targetDir, str(
                                mutant_id) + "-test_reports"),
                            exist_ok=True,
                        )
                        uncovered = False
                        while ("-",) in test_names:
                            uncovered = True
                            test_names.remove(("-",))
                        if uncovered:
                            if len(test_names) == 0:
                                res = (mutant_id, subset,
                                       Database.RES_ID_UNCOVERED, file)
                                msg = "uncovered"
                                res_dict[res[3]]["uncoveredList"].append(
                                    str(res[0]))
                                mutation_db.insert_data(
                                    "mutant_test",
                                    "mutant_id, test_id, result, time, message",
                                    [
                                        res[0],
                                        Database.INSTURMENTED_NOT_COVERED,
                                        Database.RES_ID_UNCOVERED,
                                        "0",
                                        msg,
                                    ],
                                )
                                os.remove(buildFile_)
                                continue
                        no_test = False
                        while ("?",) in test_names:
                            no_test = True
                            test_names.remove(("?",))
                        if no_test:
                            if len(test_names) == 0:
                                if (buildType == "mvn"):
                                    D_args.append("-DskipTests")
                        if (buildType == "mvn"):
                            if (len(test_names) == 0 and not no_test) or (options.runAllTests == True and not no_test):
                                test_names = [""]

                        if (buildType == "ant"):
                            if (len(test_names) == 0 and not no_test) or (options.runAllTests == True and not no_test):
                                # there are no instrumentations so we read all tests
                                test_names = mutation_db.fetch_all_coverage()
                        with resources.as_file(
                            resources.files("mediumdarwin")
                            .joinpath("jar")
                            .joinpath("clover_db_extractor.jar")
                        ) as jar_path:
                            line_coverage = LineCoverage(
                                project_path=build_directory,
                                clover_db_extractor_path=jar_path,
                                build_file_path=buildFile_,
                                build_type=buildType,
                                sqlDB_path=self.sqlDBPath,
                                D_args=D_args,
                                runAllTests=options.runAllTests,
                                timeout=int(options.initial_timeout),
                            )
                        includeFile_ = os.path.join(
                            targetDir, "include" + str(mutant_id)
                        )
                        if buildType == "mvn":
                            line_coverage._prepare_pom(
                                include_file_add=includeFile_)
                            line_coverage.add_tests_to_pom_xml(
                                include_tests_file=includeFile_,
                                report_path=os.path.join(
                                    targetDir, str(mutant_id) + "-test_reports"
                                ),
                                covered_tests=test_names,
                                subsumption=options.isSubsumptionActive,
                            )
                        elif buildType == "ant":
                            line_coverage._prepare_build_xml(
                                include_file=includeFile_,
                                junit_target=options.junitTargetName,
                                subsumption=options.isSubsumptionActive,
                            )
                            line_coverage.add_tests_to_build_xml(
                                junit_target=options.junitTargetName,
                                report_path=os.path.join(
                                    targetDir, str(mutant_id) + "-test_reports"
                                ),
                                covered_tests=test_names,
                                subsumption=options.isSubsumptionActive,
                            )
                        test_command_ = test_command.copy()
                        if (no_test):
                            if (buildType == "mvn"):
                                test_command_.extend(
                                    D_args)
                        test_command_ = change_build_file(
                            test_command_.copy(), buildFile_
                        )
                        os.remove(line_coverage.build_file_path + ".bak")
                        del line_coverage
                    targetTextOutputFile = str(
                        os.path.join(
                            targetDir, str(mutant_id) + ".txt"
                        )
                    )
                    os.makedirs(
                        os.path.join(targetDir, str(
                            mutant_id) + "-test_reports"),
                        exist_ok=True,
                    )
                    function_calls.append(
                        (mutant_id, subset, targetTextOutputFile, test_command_, file)
                    )
        # clean the project once before running tests because of the previous builds (test command is indepndent of the build command)
        if options.cleanUp != "***dummy***":
            s_time = time.time()
            (
                process_clean_killed,
                process_clean_exit_code,
                run_output_clean,
                time_delta
            ) = timeoutAlternative(
                clean_command,
                workingDirectory=build_directory,
                timeout=int(options.timeout),
                failMessage=options.fail_string,
            )
            self.clean_time += time.time() - s_time
        (
            process_build_killed,
            process_build_exit_code,
            run_output_build,
            time_delta
        ) = timeoutAlternative(
            options.buildCommand.split(
                ",") if options.initialBuildCommand == "***dummy***" else getCommand(options.initialBuildCommand),
            workingDirectory=build_directory,
            timeout=int(options.initial_timeout),
            failMessage=options.fail_string,
        )
        # create a parallel execution list of the test commands
        parallel = Parallel(n_jobs=JOBS_NO, return_as="generator_unordered")
        output_generator = parallel(
            delayed(self.run_test)(
                mutation=mutation,
                test_command=test_command,
                source_directory=build_directory,
                mutant_id=mutant_id,
                targetTextOutputFile=targetTextOutputFile,
                coverage=options.isCoverageActive,
                timeout=int(options.timeout),
                fail_message=options.fail_string,
                file=file
            )
            for (
                mutant_id,
                mutation,
                targetTextOutputFile,
                test_command,
                file
            ) in function_calls
        )
        stdscr = initscr()
        s_time = time.time()
        with open(
            os.path.join(mutantsPath, "output.txt"),
            "w",
        ) as f:
            for item in output_generator:
                msg = ""
                if item[2] == Database.RES_ID_SURVIVED_MUTANT:
                    res_dict[item[3]]["survivedList"].append(str(item[0]))
                    msg = "survived"
                elif item[2] == Database.RES_ID_KILLED_MUTANT:
                    res_dict[item[3]]["testFailureList"].append(
                        str(item[0]))
                    res_dict[item[3]]["killedList"].append(str(item[0]))
                    msg = "killed"
                elif item[2] == Database.RES_ID_BUILD_FAILURE:
                    msg = "build failure"
                    res_dict[item[3]]["killedList"].append(str(item[0]))
                    res_dict[item[3]]["buildFailureList"].append(
                        str(item[0]))
                elif item[2] == Database.RES_ID_UNCOVERED:
                    msg = "uncovered"
                    res_dict[item[3]]["uncoveredList"].append(str(item[0]))

                if not options.isCoverageActive or not options.isSubsumptionActive:
                    mutation_db.insert_data(
                        "mutant_test",
                        "mutant_id, test_id, result, time, message",
                        [
                            item[0],
                            Database.NO_INFO,
                            item[2],
                            str(item[4]),
                            msg,
                        ],
                    )
                else:
                    # if coverage is active then uptade the DB
                    self.updateMutationTestTable(
                        options=options, mutationDatabase=mutation_db, file_name=item[3], mutant_id=item[0])
                self.print_results(res_dict, start_time)
                refresh()
                f.write(str(item[0]) + " : " + msg + "\n\r")
            self.test_time += time.time() - s_time
            f.write("clean time : " +
                    str(datetime.timedelta(seconds=int(self.clean_time))) + "\n\r")
            f.write("test time : " +
                    str(datetime.timedelta(seconds=int(self.test_time))) + "\n\r")
        # release the terminal
        endwin()
        print("done")
        # output_generator.extend(resList)
        # read the results from the db and generate the HTML report files
        targetHTMLReportFile = os.path.abspath(
            os.path.join(self.LittleDarwinResultsPath, "index.html"))
        from mediumdarwin.ReportGenerator import ReportGenerator
        reportGenerator = ReportGenerator(self.littleDarwinVersion)
        reportGenerator.initiateDatabase(self.LittleDarwinResultsPath)
        htmlReportData = list()
        print("--> Writing the reports: ")
        for file in res_dict.keys():
            print("----> " + file)
            targetDir = os.path.join(
                self.LittleDarwinResultsPath,
                os.path.relpath(file, options.sourcePath),
            )
            targetHTMLOutputFile = os.path.join(
                targetDir, "index.html"
            )
            with open(targetHTMLOutputFile, "w") as contentFile:
                contentFile.write(
                    reportGenerator.generateHTMLReportPerFile(
                        os.path.relpath(file, options.sourcePath),
                        targetHTMLOutputFile,
                        res_dict[file]["survivedList"],
                        res_dict[file]["killedList"],
                        res_dict[file]["uncoveredList"],
                        res_dict[file]["buildFailureList"],
                        res_dict[file]["testFailureList"],
                        schemata=os.path.relpath(path=os.path.join(
                            self.LittleDarwinResultsPath, os.path.relpath(file, options.sourcePath), "mutant_schemata.java"), start=os.path.join(self.LittleDarwinResultsPath, os.path.relpath(file, options.sourcePath))))
                )
            # append the information for this file to the reports.
            # 0: file name, 1: survived count, 2: uncovered survived count, 3: killed by build command count, 4: killed by test command, 5: html file name
            htmlReportData.append(
                [
                    os.path.relpath(file, options.sourcePath),
                    len(res_dict[file]["survivedList"]),
                    len(res_dict[file]["uncoveredList"]),
                    len(res_dict[file]["buildFailureList"]),
                    len(res_dict[file]["testFailureList"]),
                    targetHTMLOutputFile,
                ]
            )

        # -----------------------------------------------------
        for file in java_io.fileList:
            targetDir = os.path.join(
                self.LittleDarwinResultsPath,
                os.path.relpath(file, options.sourcePath),
            )
            if os.path.isfile(os.path.join(targetDir, "original.java")):
                shutil.copyfile(os.path.join(targetDir, "original.java"), file)
        with open(targetHTMLReportFile, "w") as htmlReportFile:
            htmlReportFile.writelines(
                reportGenerator.generateHTMLFinalReport(
                    htmlReportData, targetHTMLReportFile
                )
            )
        # -----------------------------------------------------
        # write final HTML report.
        return list(output_generator)

    def cleanup_mediumDarwin(self):
        """
        Terminate MediumDarwin        
        """
        print("Cleanup MediumDarwin...")
        java_io = JavaIO(self.options.isVerboseActive)
        java_io.listFiles(
            targetPath=os.path.abspath(self.options.sourcePath),
            buildPath=os.path.abspath(self.options.buildPath),
            filterType=self.filterType,
            filterList=self.filterList,
        )
        for file in java_io.fileList:
            originalFile = os.path.join(
                self.LittleDarwinResultsPath,
                os.path.relpath(file, self.options.sourcePath),
                "original.java"
            )
            if os.path.isfile(originalFile):
                shutil.copyfile(
                    originalFile, file)
                print("Restored " + file)

    def __init__(self, mockArgs: list = None):
        print(r"""
        __       __                  __  __                          _______                                     __            
       |  \     /  \                |  \|  \                        |       \                                   |  \           
       | $$\   /  $$  ______    ____| $$ \$$ __    __  ______ ____  | $$$$$$$\  ______    ______   __   __   __  \$$ _______   
       | $$$\ /  $$$ /      \  /      $$|  \|  \  |  \|      \    \ | $$  | $$ |      \  /      \ |  \ |  \ |  \|  \|       \  
       | $$$$\  $$$$|  $$$$$$\|  $$$$$$$| $$| $$  | $$| $$$$$$\$$$$\| $$  | $$  \$$$$$$\|  $$$$$$\| $$ | $$ | $$| $$| $$$$$$$\ 
       | $$\$$ $$ $$| $$    $$| $$  | $$| $$| $$  | $$| $$ | $$ | $$| $$  | $$ /      $$| $$   \$$| $$ | $$ | $$| $$| $$  | $$ 
       | $$ \$$$| $$| $$$$$$$$| $$__| $$| $$| $$__/ $$| $$ | $$ | $$| $$__/ $$|  $$$$$$$| $$      | $$_/ $$_/ $$| $$| $$  | $$ 
       | $$  \$ | $$ \$$     \ \$$    $$| $$ \$$    $$| $$ | $$ | $$| $$    $$ \$$    $$| $$       \$$   $$   $$| $$| $$  | $$ 
        \$$      \$$  \$$$$$$$  \$$$$$$$ \$$  \$$$$$$  \$$  \$$  \$$ \$$$$$$$   \$$$$$$$ \$$        \$$$$$\$$$$  \$$ \$$   \$$ 
                                                                                                                            
       Copyright (c) 2014 2022 Ali Parsai                                                                                      
       Copyright (c) 2025      MediumDarwin Contributors                                                                       
                                                                                                                            
       This project builds upon the original work of Ali Parsai and the LittleDarwin mutation testing framework.               
       We gratefully acknowledge his foundational contributions, which made this extended version possible.                    
                                                                                                                                
       This program is free software: you can redistribute it and/or modify it under the terms of the GNU                      
       General Public License as published by the Free Software Foundation, version 3  of the License, or                      
       (at your option) any later version.                                                                                     
                                                                                                                            
       This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied       
       warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the  GNU General Public License for more details.   
                                                                                                                                
       You should have received a copy of the GNU General Public License along with this program.                              
       If not, see <https://www.gnu.org/licenses/>.                                                                             
                                                                                                                                
       Original author:                                                                                                         
       Ali Parsai — https://www.parsai.net/                                                                                     
        """)
        optionParser = OptionParser()
        self.options, self.filterType, self.filterList, higherOrder = parseCmdArgs(
            optionParser, mockArgs
        )
        self.LittleDarwinResultsPath = os.path.join(
            self.options.buildPath, "LittleDarwinResults"
        )
        self.sqlDBPath = os.path.join(
            self.LittleDarwinResultsPath, "mutationdatabase.db"
        )
        if not os.path.exists(self.LittleDarwinResultsPath):
            os.makedirs(self.LittleDarwinResultsPath, exist_ok=True)

    def main(self):
        """
        Main LittleDarwin Function
        """

        MUTATION_ORDER = self.options.higherOrder
        mutationDatabase2 = Database(self.sqlDBPath)
        if self.options.isBuildActive or self.options.isMutationActive:
            mutationDatabase2.create_tables()
            java_io = JavaIO(self.options.isVerboseActive)
            java_io.listFiles(targetPath=os.path.abspath(self.options.sourcePath), buildPath=os.path.abspath(
                self.options.buildPath), filterType=self.filterType, filterList=self.filterList)
            for f in java_io.fileList:
                mutationDatabase2.insert_file(f)
            build_command = getCommand(self.options.buildCommand)
            clean_command = getCommand(self.options.cleanUp)
            test_command = getCommand(self.options.testCommand)

            build_directory = os.path.abspath(self.options.buildPath)

            buildType = ""
            if build_command[0].endswith("mvn"):
                buildType = "mvn"
            elif build_command[0].endswith("ant"):
                buildType = "ant"
            buildFile = return_build_file(" ".join(build_command))
            if buildFile == None:
                if buildType == "ant":
                    buildFile = os.path.join(build_directory, "build.xml")
                elif buildType == "mvn":
                    buildFile = os.path.join(build_directory, "pom.xml")
            # initial build check to avoid false results. the system must be able to build cleanly without errors.
            # use build command for the initial build unless it is explicitly provided.
            print("Initial build...", end=" ", flush=True)
            s_time = time.time()
            try:
                processInitialKilled, processInitialExitCode, initialOutput, time_delta = (
                    timeoutAlternative(
                        self.options.buildCommand.split(
                            ",") if self.options.initialBuildCommand == "***dummy***" else getCommand(self.options.initialBuildCommand),
                        workingDirectory=os.path.abspath(
                            self.options.buildPath),
                        timeout=int(self.options.initial_timeout),
                        failMessage=self.options.fail_string,
                    )
                )
                # workaround for older python versions
                if processInitialKilled or processInitialExitCode:
                    raise subprocess.CalledProcessError(
                        1 if processInitialKilled else processInitialExitCode,
                        self.options.buildCommand.split(
                            ",") if self.options.initialBuildCommand == "***dummy***" else getCommand(self.options.initialBuildCommand),
                        initialOutput,
                    )
                with open(
                    os.path.abspath(os.path.join(
                        self.LittleDarwinResultsPath, "initialbuild.txt")), "w"
                ) as contentFile:
                    contentFile.write(str(initialOutput))
                # run line coverage and store the results
                if self.options.isCoverageActive == True:
                    line_coverage = None
                    print("Running clover test coverage collection...",
                          end=" ", flush=True)
                    with resources.as_file(
                        resources.files("mediumdarwin")
                        .joinpath("jar")
                        .joinpath("clover_db_extractor.jar")
                    ) as jar_path:
                        line_coverage = LineCoverage(
                            project_path=build_directory,
                            clover_db_extractor_path=jar_path,
                            build_file_path=buildFile,
                            build_type=buildType,
                            sqlDB_path=self.sqlDBPath,
                            D_args=return_D_arguments(" ".join(test_command)),
                            runAllTests=self.options.runAllTests,
                            timeout=int(self.options.initial_timeout),
                        )
                        line_coverage.run_clover(
                            junit_target=self.options.junitTargetName,
                            test_target=(
                                "test" if build_command[0].endswith(
                                    "mvn") else self.options.testTargetName
                            ),
                        )
                        line_coverage.restore_the_build_file()
                print("done.\n\n")
            except subprocess.CalledProcessError as exception:
                initialOutput = exception.output
                with open(
                    os.path.abspath(os.path.join(
                        self.LittleDarwinResultsPath, "initialbuild.txt")), "w"
                ) as contentFile:
                    initialOutput = initialOutput
                    contentFile.write(
                        str(initialOutput).replace("\\r\\n", "\n")
                        + "\n Command: "
                        + " ".join(exception.cmd)
                    )
                print("failed.\n")
                print(
                    "Initial build failed. Try building the system manually first to make sure it can be built. "
                    + "Take a look at "
                    + os.path.abspath(os.path.join(self.LittleDarwinResultsPath,
                                                   "initialbuild.txt"))
                    + " to find out why this happened."
                )
                sys.exit(3)
            self.compile_time += time.time() - s_time

            if self.options.cleanUp != "***dummy***":
                s_time = time.time()
                (
                    process_clean_killed,
                    process_clean_exit_code,
                    run_output_clean,
                    time_delta
                ) = timeoutAlternative(
                    clean_command,
                    workingDirectory=os.path.abspath(self.options.buildPath),
                    timeout=int(self.options.timeout),
                    failMessage=self.options.fail_string,
                )
                self.clean_time += time.time() - s_time

        # *****************************************************************************************************************
        # ---------------------------------------- mutant generation phase ------------------------------------------------
        # *****************************************************************************************************************
        if self.options.isMutationActive:
            (
                build_failures,
                file_mutations_dict,
            ) = self.mutant_schemata_generation(
                self.options,
                self.filterType,
                self.filterList,
                mutationDatabase2,
                False
            )
            mutant_ID = -1
            print("--> Writing mutant data to the DB: ")
            for file in file_mutations_dict.keys():
                print("----> " + file)
                for L in range(1, (MUTATION_ORDER + 1)):
                    for subset in itertools.combinations(file_mutations_dict[file].keys(), L):
                        mutant_ID += 1
                        my_set = set()
                        for mutation in subset:
                            my_set.add(mutation)
                            mutationDatabase2.insert_mutant(
                                mutant_ID, mutation)
                            if mutation in build_failures:
                                res = (mutant_ID, subset,
                                       Database.RES_ID_BUILD_FAILURE, file)
                                msg = "build failure"
                                mutationDatabase2.insert_data(
                                    "mutant_test",
                                    "mutant_id, test_id, result, time, message",
                                    [
                                        res[0],
                                        Database.NO_TEST,
                                        Database.RES_ID_BUILD_FAILURE,
                                        "0",
                                        msg,
                                    ],
                                )
                                break
            print("-------------------------------------")
        if self.options.isBuildActive:
            results = mutationDatabase2.fetch_mutations()
            java_parse = JavaParse(False)
            Mutation.reverse_mutation_dict = dict()
            Mutation.mutation_dict = dict()
            for res in results:
                Mutation.mutation_dict[int(res[0])] = (
                    eval(res[9]), eval(res[8]), eval(res[10]))
                for i in range(len(Mutation.mutation_dict[int(res[0])][0])):
                    Mutation.mutation_dict[int(res[0])][1][i] = java_parse.Json2Tree(
                        Mutation.mutation_dict[int(res[0])][1][i])

                    Mutation.mutation_dict[int(res[0])][0][i] = int(
                        Mutation.mutation_dict[int(res[0])][0][i])
                    Mutation.mutation_dict[int(
                        res[0])][2][i] = Mutation.mutation_dict[int(res[0])][2][i]

            mutants_dict_ = mutationDatabase2.construct_mutant_dict()
            compile_mutations_files = mutationDatabase2.construct_compile_mutations()
            output_generator = self.run_mutant_schemata(
                mutants_dict_,
                # de_pickled_build_failures,
                compile_mutations_files,
                mutationDatabase2,
                self.options,
            )
            count = 0
            for item in output_generator:
                count += item[2]
            print(str(count) + "/" + str(len(output_generator)))

        if self.options.isSubsumptionActive:
            self.subsumptionAnalysisPhase(self.options)
        mutationDatabase2.close_connection()
