import signal
import platform
import sys
import threading
import re
from shutil import which
import os
import shutil
import subprocess
from mediumdarwin.JavaParser import JavaParser
from mediumdarwin.JavaParse import JavaParse
import psutil
import xml.etree.ElementTree as ET
import time
import shlex


class MutationOperator(object):
    """ """

    instantiable = True
    metaTypes = ["Generic"]

    def __init__(
        self,
        sourceTree: JavaParser.CompilationUnitContext,
        sourceCode: str,
        javaParseObject: JavaParse,
        generateMutants=False,
        generateMutations=True,
    ):
        self.sourceTree = sourceTree
        self.sourceCode = sourceCode
        self.color = "#FFFFF0"
        self.mutatorType = "GenericMutationOperator"
        self.allNodes = list()  # populated by findNodes
        self.mutableNodes = list()  # populated by filterCriteria
        self.mutations = list()  # populated by generateMutations
        self.mutants = list()  # populated by generateMutants
        self.generateMutants_ = generateMutants
        self.generateMutations_ = generateMutations
        self.mutations_searched = False
        if self.generateMutants_:
            self.generateMutations_ = True
        self.javaParseObject = javaParseObject

    def findNodes(self):
        """
        Finds all nodes that match the search criteria
        """
        pass

    def filterCriteria(self):
        """
        Filters out the nodes that do not match the input critera
        """
        pass

    def generateMutations(self):
        pass

    def generateMutants(self):
        """
        Generates the mutants
        """
        pass

    @property
    def cssClass(self):
        """
        Returns CSS Class for the mutation operator

        :return: CSS Class
        :rtype: str
        """

        return ".{classname} {{ background: {color}; }} ".format(
            classname=self.mutatorType, color=self.color
        )


def return_build_file(command):
    args = shlex.split(command)
    file = None
    i = 0
    while i < len(args):
        if args[i] in ["-f", "--file", "-buildfile"]:
            return args[i + 1]
        i += 1
    return file


def change_build_file(command, new_buildFile: str):
    new_command = []
    i = 0
    found = False
    while i < len(command):
        new_buildFile = new_buildFile.replace("\\", "/")
        new_command.append(command[i])
        if command[i] in ["-f", "--file", "-buildfile"]:
            found = True
            i += 1
            new_command.append(new_buildFile)
        i += 1
    if not found:
        new_command.append("-f")
        new_command.append(new_buildFile)
    return new_command


def return_D_arguments(command):
    args = shlex.split(command)
    D_args = []
    i = 0
    while i < len(args):
        if args[i].startswith("-D"):
            D_args.append(args[i])
        i += 1
    return D_args


def getCommand(commandString: str):
    """Turns comma separated string to executable string. Use \\f for "," in your command

    Args:
        commandString (str): _description_

    Returns:
        _type_: _description_
    """
    commandString_ = commandString.replace(",", " ")
    commandString_ = commandString_.replace("\f", ",")
    return commandString_.split(" ")


def getAllInstantiableSubclasses(parentClass):
    """

    :param parentClass: the class that all its subclasses must be returned
    :type parentClass: Type[MutationOperator]
    :return: set of MutationOperator instantiable subclasses
    :rtype: set
    """
    allInstantiableSubclasses = set()
    subClasses = parentClass.__subclasses__()
    # subClasses.append(parentClass)
    for subClass in subClasses:
        if subClass.instantiable:
            allInstantiableSubclasses.add(subClass)
        allInstantiableSubclasses.update(
            getAllInstantiableSubclasses(subClass))
    allInstantiableSubclasses.update({parentClass})
    return allInstantiableSubclasses


def parse_junit_xml(xml_file):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        results = []
        for testcase in root.findall("testcase"):
            name = testcase.get("classname") + "." + testcase.get("name")
            if "(" in name:
                name = name[:name.find("(")]
            failures = testcase.findall("failure")
            failureMessage = ""
            if len(failures) > 0:
                failureMessage = failures[0].text
            errors = testcase.findall("error")
            errorMessage = ""
            if len(errors) > 0:
                errorMessage = errors[0].text
            time = testcase.get("time")
            results.append((name, time, failureMessage, errorMessage))
    except Exception as e:
        return []
    return results


def timeoutAlternative(
    commandString,
    workingDirectory,
    timeout,
    failMessage=None,
    inputData=None,
    activeMutants=list([]), buffer_size=1024
):
    """

    :param commandString: command to run
    :param workingDirectory: the directory that the command is supposed to run in
    :param timeout: timeout in seconds
    :param inputData: the data that the run process may need. defaults to None.
    :return: returns kill status, process return code and the output of the system
    """

    killCheck = threading.Event()

    # this method is run in another thread when the timeout is expired to kill the process.
    def killProcess(pipe):
        """

        :param pipe:
        :type pipe:
        """
        assert isinstance(pipe, subprocess.Popen)

        # there is no support for os.killpg on windows, neither does it have SIGKILL.
        if platform.system() == "Windows":
            # this utility is not included in windows XP Home edition, however, there is no other alternative either.
            # therefore, don't run MediumDarwin on windows XP Home edition; he gets sad.
            subprocess.Popen("taskkill /F /T /PID %i" % pipe.pid, shell=True)
        else:
            # posix systems all support this call.
            # pipe.terminate()
            try:
                os.killpg(os.getpgid(pipe.pid), signal.SIGTERM)
            except:
                os.kill(pipe.pid, signal.SIGTERM)

        # we just killed the process. let everyone know.
        killCheck.set()

    # timeout must be int, otherwise problems arise.
    assert isinstance(timeout, int)

    reliableCommandString = shutil.which(os.path.abspath(commandString[0]))

    reliableCommandString = shutil.which(os.path.abspath(os.path.join(workingDirectory, commandString[0]))) \
        if reliableCommandString is None else reliableCommandString

    reliableCommandString = shutil.which(commandString[0]) \
        if reliableCommandString is None else reliableCommandString

    if reliableCommandString is None:
        print(
            "\nBuild command not correct. Cannot find the executable: " + commandString[0])
        sys.exit(5)

    commandString[0] = reliableCommandString
    my_env = os.environ.copy()
    for activeMutant in activeMutants:
        my_env["MUT" + str(activeMutant)] = "true"
    # starting the process with the given parameters.
    if platform.system() != "Windows":
        process = subprocess.Popen(commandString, cwd=workingDirectory, stdin=subprocess.PIPE, env=my_env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    else:  # in Windows
        process = subprocess.Popen(commandString, cwd=workingDirectory, stdin=subprocess.PIPE, env=my_env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    timeStarted = time.time()
    # passing the process and timeout references to threading's timer method, so that it kills the process
    # if timeout expires.
    timerWatchdog = threading.Timer(timeout, killProcess, args=[process])
    timerWatchdog.start()

    buffer_size = 1024
    output_max_reached = False
    output_max_size = 1024 * 1024 * 100  # 100MB
    output_size = 0
    # getting the output of the process.
    stdout_str = ""
    stderr_str = ""
    output = process.stdout.read(buffer_size)
    output_err = ""
    output_err = process.stderr.read(
        buffer_size) if process.stderr is not None else output_err
    while process.poll() is None or output != b"":
        if output and output_max_reached is False:
            output_size += len(output)
            stdout_str += output.decode("utf-8", errors="ignore").strip()
        if output_size > output_max_size:
            output_max_reached = True
        output = process.stdout.read(buffer_size)
        output_err = process.stderr.read(
            buffer_size) if process.stderr is not None else output_err
        stderr_str += output_err.decode(
            "utf-8", errors="ignore").strip() if output_err != "" else output_err

    # do the stuff in the process.
    process.wait()
    # if the process is done, no need to kill it.
    timerWatchdog.cancel()

    isKilled = killCheck.is_set()
    killCheck.clear()
    try:
        process.kill()
        process.terminate()
        process.wait()
    except:
        print("error killing process")

    if failMessage != None:
        if failMessage in stdout_str:
            isKilled = True
    timeDelta = time.time() - timeStarted

    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    stdout_str += "\n ================================================ STDERR ================================================ \n"
    stdout_str += stderr_str
    stdout_str = ansi_escape.sub('', stdout_str)
    return isKilled, process.returncode, stdout_str, timeDelta
