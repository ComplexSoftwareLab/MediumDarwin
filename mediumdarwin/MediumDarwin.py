

####################################################################################################################################
##        __       __                  __  __                          _______                                     __             ##
##       |  \     /  \                |  \|  \                        |       \                                   |  \            ##
##       | $$\   /  $$  ______    ____| $$ \$$ __    __  ______ ____  | $$$$$$$\  ______    ______   __   __   __  \$$ _______    ##
##       | $$$\ /  $$$ /      \  /      $$|  \|  \  |  \|      \    \ | $$  | $$ |      \  /      \ |  \ |  \ |  \|  \|       \   ##
##       | $$$$\  $$$$|  $$$$$$\|  $$$$$$$| $$| $$  | $$| $$$$$$\$$$$\| $$  | $$  \$$$$$$\|  $$$$$$\| $$ | $$ | $$| $$| $$$$$$$\  ##
##       | $$\$$ $$ $$| $$    $$| $$  | $$| $$| $$  | $$| $$ | $$ | $$| $$  | $$ /      $$| $$   \$$| $$ | $$ | $$| $$| $$  | $$  ##
##       | $$ \$$$| $$| $$$$$$$$| $$__| $$| $$| $$__/ $$| $$ | $$ | $$| $$__/ $$|  $$$$$$$| $$      | $$_/ $$_/ $$| $$| $$  | $$  ##
##       | $$  \$ | $$ \$$     \ \$$    $$| $$ \$$    $$| $$ | $$ | $$| $$    $$ \$$    $$| $$       \$$   $$   $$| $$| $$  | $$  ##
##        \$$      \$$  \$$$$$$$  \$$$$$$$ \$$  \$$$$$$  \$$  \$$  \$$ \$$$$$$$   \$$$$$$$ \$$        \$$$$$\$$$$  \$$ \$$   \$$  ##
##                                                                                                                                ##
##       Copyright (c) 2014–2022 Ali Parsai                                                                                       ##
##       Copyright (c) 2025–     MediumDarwin Contributors                                                                        ##
##                                                                                                                                ##
##       This project builds upon the original work of Ali Parsai and the LittleDarwin mutation testing framework.                ##
##       We gratefully acknowledge his foundational contributions, which made this extended version possible.                     ##
##                                                                                                                                ##
##       This program is free software: you can redistribute it and/or modify it under the terms of the GNU                       ##
##       General Public License as published by the Free Software Foundation, version 3  of the License, or                       ##
##       (at your option) any later version.                                                                                      ##
##                                                                                                                                ##
##       This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied       ##
##       warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the  GNU General Public License for more details.   ##
##                                                                                                                                ##
##       You should have received a copy of the GNU General Public License along with this program.                               ##
##       If not, see <https://www.gnu.org/licenses/>.                                                                             ##
##                                                                                                                                ##
##       Original author:                                                                                                         ##
##       Ali Parsai — https://www.parsai.net/                                                                                     ##
####################################################################################################################################


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
from mediumdarwin.original.JavaMutate_test_selection import JavaMutate
from mediumdarwin.SharedFunctions import return_build_file
from mediumdarwin.SharedFunctions import return_D_arguments, getCommand
from mediumdarwin.Database import Database

import networkx as nx
import matplotlib.pyplot as plt
from colorama import Fore, Style

# LittleDarwin modules
from mediumdarwin.JavaParse import JavaParse
from mediumdarwin.ReportGenerator import ReportGenerator

import re


class MediumDarwin:
    littleDarwinVersion = "0.10.7"
    sqlDBPath = ""
    LittleDarwinResultsPath = ""

    def find_tests_run(text):
        pattern = r"Tests run: (\d+)"
        matches = re.findall(pattern, text)
        return matches

    def main(self, mockArgs: list = None):
        """
        Main MediumDarwin Function
        """
        print(
            r"""
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
        """
        )

        optionParser = OptionParser(
            prog="mediumdarwin")
        options, filterType, filterList, higherOrder = self.parseCmdArgs(
            optionParser, mockArgs
        )
        self.LittleDarwinResultsPath = os.path.join(
            options.buildPath, "LittleDarwinResults"
        )
        self.sqlDBPath = os.path.join(
            self.LittleDarwinResultsPath, "mutationdatabase.db"
        )
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
            print(
                "\nExample:\n  MediumDarwin -m -b -t ./ -p ./src/main -c mvn,clean,test --timeout=120\n\n"
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
        # creating our module objects.
        javaIO = JavaIO(options.isVerboseActive)
        javaParse = JavaParse(options.isVerboseActive)
        totalMutantCount = 0
        totalMutationCount = 0

        try:
            assert os.path.isdir(options.sourcePath)
        except AssertionError as exception:
            print("Source path must be a directory.")
            sys.exit(1)
        # getting the list of files.
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
        databasePath = os.path.join(javaIO.targetDirectory, "mutationdatabase")

        densityResultsPath = os.path.join(
            javaIO.targetDirectory, "ProjectDensityReport.csv"
        )
        print("Source Path: ", javaIO.sourceDirectory)
        print("Target Path: ", javaIO.targetDirectory)
        print("Creating Mutation Database: ", databasePath)
        # mutationDatabase = shelve.open(databasePath, "c")

        mutationDatabase2 = Database(self.sqlDBPath)
        mutationDatabase2.create_tables()

        mutantTypeDatabase = dict()
        averageDensityDict = dict()
        if mutationDatabase2 is not None:
            mutationDatabase2.delete_data("mutant")
            mutationDatabase2.delete_data("mutation")
        # go through each file, parse it, calculate all mutations, and generate files accordingly.
        mutants = dict()
        for srcFile in javaIO.fileList:
            print(
                "\n(" + str(fileCounter + 1) + "/" +
                str(fileCount) + ") Source file: ",
                srcFile,
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
                print("Error in parsing Java code, skipping the file.")
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
            print("--> Mutations found: ", len(javaMutate.mutations))
            for mutantType in mutantTypes.keys():
                if mutantTypes[mutantType] > 0:
                    print("---->", mutantType, ":", mutantTypes[mutantType])
                mutantTypeDatabase[mutantType] = mutantTypes[
                    mutantType
                ] + mutantTypeDatabase.get(mutantType, 0)
            totalMutationCount += len(javaMutate.mutations)
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
        print("\nTotal mutations found: ", totalMutationCount)
        print("Total mutant found: ", totalMutantCount)
        if totalMutantCount == 0:
            print("No mutants generated? Something must be wrong.")
            sys.exit(6)

        with open(densityResultsPath, "w") as densityReportHandle:
            for key in averageDensityDict.keys():
                densityReportHandle.write(
                    key + "," + str(averageDensityDict[key]) + "\n"
                )

        for mutantType in list(mutantTypeDatabase.keys()):
            if mutantTypeDatabase[mutantType] > 0:
                print("-->", mutantType + ":", mutantTypeDatabase[mutantType])

    def buildPhase(self, options):
        """

        :param options:
        :type options:
        """
        # let's tell the user upfront that this may corrupt the source code.
        print("\n\n!!! CAUTION !!!")
        print("Code can be changed accidentally. Create a backup first.\n")

        reportGenerator = ReportGenerator(self.littleDarwinVersion)
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
            print("Build system working directory should be a directory.")
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
                    print(
                        "Test project build system working directory should be a directory."
                    )

        else:
            separateTestSuite = False
        # try to open the database. if it can't be opened, it means that it does not exist or it is corrupt.
        try:
            # mutationDatabase = shelve.open(databasePath, "r")
            mutationDatabase2 = Database(self.sqlDBPath)
        except:
            print(
                "Cannot open mutation database. It may be corrupted or unavailable. Delete all generated files and run the mutant generation phase again."
            )
            sys.exit(2)

        databaseKeys = mutationDatabase2.fetch_mutated_files()

        mutationDatabaseLength = len(databaseKeys)
        textReportData = list()
        htmlReportData = list()
        fileCounter = 0

        compile_time = 0
        # initial build check to avoid false results. the system must be able to build cleanly without errors.
        # use build command for the initial build unless it is explicitly provided.
        if options.initialBuildCommand == "***dummy***":
            commandString = getCommand(options.buildCommand)

        else:
            commandString = getCommand(options.initialBuildCommand)
        print("Initial build...", end=" ", flush=True)
        try:
            s_time = time.time()
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
            # run line coverage and store the results
            line_coverage = None
            if options.isCoverageActive == True:
                with resources.as_file(
                    resources.files("mediumdarwin")
                    .joinpath("jar")
                    .joinpath("clover_db_extractor.jar")
                ) as jar_path:
                    buildFile = return_build_file(
                        options.buildCommand.replace(",", " ")
                    )
                    buildType = ""
                    if getCommand(options.buildCommand)[0].endswith("mvn"):
                        buildType = "mvn"
                    elif getCommand(options.buildCommand)[0].endswith("ant"):
                        buildType = "ant"
                    line_coverage = LineCoverage(
                        project_path=options.buildPath,
                        clover_db_extractor_path=jar_path,
                        build_file_path=buildFile,
                        build_type=buildType,
                        sqlDB_path=self.sqlDBPath,
                        D_args=return_D_arguments(
                            " ".join(getCommand(options.testCommand))
                        ),
                        runAllTests=options.runAllTests,
                        timeout=int(options.initial_timeout),
                    )
                    # pass
                    line_coverage.run_clover(
                        junit_target=options.junitTargetName,
                        test_target=(
                            "test"
                            if getCommand(options.buildCommand)[0].endswith("mvn")
                            else options.testTargetName
                        ),
                    )
            print("done.\n\n")
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
            print("failed.\n")
            print(
                "Initial build failed. Try building the system manually first to make sure it can be built. "
                + "Take a look at "
                + os.path.abspath(os.path.join(mutantsPath,
                                  "initialbuild.txt"))
                + " to find out why this happened."
            )
            sys.exit(3)
        totalMutantCount = 0
        totalMutantCounter = 0
        totalMutantCount = mutationDatabase2.fetch_mutated_files_count()

        startTime = time.time()
        # running the build system for each mutant.
        search_time = 0
        prepare_build_time = 0
        tests_run_dict = dict()
        for key in databaseKeys:
            fileCounter += 1

            print(
                "("
                + str(fileCounter)
                + "/"
                + str(mutationDatabaseLength)
                + ") collecting results for ",
                key[0],
                flush=True,
            )

            mutantCount = key[1]
            mutantCounter = 0

            survivedList = list()
            killedList = list()
            uncoveredList = list()
            buildFailureList = list()
            testFailureList = list()

            mutants = mutationDatabase2.fetch_file_mutant(key[0])

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
                            if getCommand(options.buildCommand)[0].endswith("mvn"):
                                commandString.append("-DfailIfNoTests=false")
                                s_time = time.time()
                                line_coverage.add_tests_to_pom_xml(
                                    include_tests_file=line_coverage.include_file_add,
                                    report_path=replacementFile + "-test_reports",
                                    covered_tests=test_names,
                                    subsumption=options.isSubsumptionActive,
                                )
                                prepare_build_time += time.time() - s_time

                            elif getCommand(options.buildCommand)[0].endswith("ant"):
                                test_names = mutationDatabase2.fetch_all_coverage()
                                s_time = time.time()
                                line_coverage.add_tests_to_build_xml(
                                    junit_target=options.junitTargetName,
                                    report_path=replacementFile + "-test_reports",
                                    covered_tests=test_names,
                                    subsumption=options.isSubsumptionActive,
                                )
                                prepare_build_time += time.time() - s_time
                            # TODO to be implemented for gradle
                            # elif(options.buildCommand.split(",")[0] == "gradle"):
                            #     line_coverage.add_tests_to_gradle(
                            #         build_gradle_file=os.path.join(options.buildPath, "build.gradle"),
                            #         junit_target=options.junitTargetName,
                            #         covered_tests=test_names,
                            #     )
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
                        else:
                            processTestKilled = False
                            processTestExitCode = 0
                            runOutput = "not covered"
                            uncoveredList.append(
                                os.path.basename(replacementFile))
                    # raise the same exception as the original check_output.
                    if processBuildKilled or processBuildExitCode:
                        buildFailureList.append(
                            os.path.basename(replacementFile))
                        raise subprocess.CalledProcessError(
                            1 if processBuildKilled else processBuildExitCode,
                            commandString,
                            runOutput,
                        )

                    if separateTestSuite and options.isCoverageActive == False:
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
                            if getCommand(options.buildCommand)[0].endswith("mvn"):
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
                            elif getCommand(options.buildCommand)[0].endswith("ant"):
                                test_names = mutationDatabase2.fetch_all_coverage()
                                s_time = time.time()
                                line_coverage.add_tests_to_build_xml(
                                    junit_target=options.junitTargetName,
                                    report_path=replacementFile + "-test_reports",
                                    covered_tests=test_names,
                                    subsumption=options.isSubsumptionActive,
                                )
                                prepare_build_time += time.time() - s_time
                            # TODO to be implemented for gradle
                            # elif(options.buildCommand.split(",")[0] == "gradle"):
                            #     line_coverage.add_tests_to_gradle(
                            #         build_gradle_file=os.path.join(options.buildPath, "build.gradle"),
                            #         junit_target=options.junitTargetName,
                            #         covered_tests=test_names,
                            #     )
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
                            shutil.copy2(line_coverage.include_file_add,
                                         os.path.join(mutantsPath,  os.path.relpath(os.path.relpath(mutant_file[0]), options.sourcePath), str(mutant_file[1])+".include"))
                            compile_time += time.time() - s_time
                            if processTestKilled or processTestExitCode:
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
                            uncoveredList.append(
                                os.path.basename(replacementFile))
                    # if we are here, it means no exceptions happened, so lets add this to our success list.
                    runOutput = (
                        runOutput
                        + "\n ----------------------------------------- \n"
                        + runOutputTest
                    )
                    if uncoveredList == []:
                        survivedList.append(os.path.basename(replacementFile))
                    elif uncoveredList[-1] != os.path.basename(replacementFile):
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

                print(
                    "elapsed: "
                    + str(datetime.timedelta(seconds=int(time.time() - startTime)))
                    + " remaining: "
                    + str(
                        datetime.timedelta(
                            seconds=int(
                                (float(time.time() - startTime) / totalMutantCounter)
                                * float(totalMutantCount - totalMutantCounter)
                            )
                        )
                    )
                    + " total: "
                    + str(totalMutantCounter)
                    + "/"
                    + str(totalMutantCount)
                    + " current: "
                    + str(mutantCounter)
                    + "/"
                    + str(mutantCount)
                    + " *** survived: "
                    + str(len(survivedList))
                    + " - killed: "
                    + str(len(killedList))
                    + " - uncovered: "
                    + str(len(uncoveredList))
                    + "         \r",
                    end="\r",
                    flush=True,
                )

                # writing the build output to disk.
                with open(targetTextOutputFile, "w") as contentFile:
                    contentFile.write(str(runOutput))
                if options.isCoverageActive == True:
                    shutil.copyfile(
                        line_coverage.build_file_path, targetXMLOutputFile)
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
                        uncoveredList,
                        buildFailureList,
                        testFailureList,
                    )
                )
            # append the information for this file to the reports.
            # 0: file name, 1: survived count, 2: uncovered survived count, 3: killed by build command count, 4: killed by test command, 5: html file name
            htmlReportData.append(
                [
                    key[0],
                    len(survivedList),
                    len(uncoveredList),
                    len(buildFailureList),
                    len(testFailureList),
                    targetHTMLOutputFile,
                ]
            )

            print("\n\n")
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
                    str(file_mutant[1]) + ".java-test_reports",
                )
            )
            xml_files = []
            if os.path.exists(directory):
                values = []
                for xml_file in glob.glob(str(os.path.join(directory, "**", "*.xml")), recursive=True):
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
        if mockArgs is None:
            (options, args) = optionParser.parse_args()
        else:
            (options, args) = optionParser.parse_args(args=mockArgs)

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
