import os
import subprocess
import xml.etree.ElementTree as ET
import re
import shutil
from xml.etree import ElementTree
# from importlib import resources
import importlib_resources as resources
from mediumdarwin.Database import Database
from mediumdarwin.SharedFunctions import timeoutAlternative
from pathlib import Path

from xml.etree import ElementTree as ET_


class LineCoverage:
    """
    This class handels creating a temporary POM file and include code coverage plugin in it.
    It also handels parsing coverage.xml file and checks whether a mutant is covered by a test or not.
    """

    tree_clover = None
    build_type = None  # maven, ant, gradle
    timeout = None
    include_file_add = None
    runAllTests = False
    build_file_path = None
    D_args = []
    report_path = None

    def _prepare_pom(self, include_file_add=None):
        if include_file_add == None:
            self.include_file_add = str(
                os.path.join(
                    self.project_path,
                    "LittleDarwinResults",
                    "include-tests.txt",
                )
            )
        else:
            self.include_file_add = include_file_add
        shutil.copy2(self.build_file_path, str(self.build_file_path) + ".bak")
        # Update the junit version to 4.13.2 because test exclusion is not supported in older versions
        self._update_juint_version_add_clover_pom_xml()

    def _prepare_build_xml(self, junit_target, include_file=None, subsumption=False):
        if include_file == None:
            self.include_file_add = str(
                os.path.join(
                    self.project_path,
                    "LittleDarwinResults",
                    "include-tests.txt",
                )
            )
        else:
            self.include_file_add = include_file
        shutil.copy2(self.build_file_path, str(self.build_file_path) + ".bak")
        self._update_juint_version_add_clover_build_xml(
            junit_target=junit_target, subsumption=subsumption
        )

    def _clean_clover_from_build_xml(self, junit_target):
        with open(self.build_file_path, "r") as f:
            data = f.read()
        data = data.replace("&test_file_for_clover", "test_file_for_clover")
        with open(self.build_file_path, "w") as f:
            f.write(data)

        tree = ET.parse(self.build_file_path)
        root = tree.getroot()
        os.chdir(self.project_path)

        root.remove(root.find('./taskdef[@resource="cloverlib.xml"]'))
        root.remove(root.find('./property[@name="clover.jar"]'))

        test_target_element = root.find(".//*[@name='" + junit_target + "']")
        junit_element = test_target_element.find(".//junit")

        for formatter in junit_element.findall(".//formatter"):
            junit_element.remove(formatter)

        tree.write(self.build_file_path)
        header = (
            '<?xml version="1.0"?><!DOCTYPE project [<!ENTITY test_file_for_clover SYSTEM "'
            + self.include_file_add
            + '">]>'
        )
        with open(self.build_file_path, "r") as f:
            data = f.read()
        data = data.replace("test_file_for_clover", "&test_file_for_clover")
        with open(self.build_file_path, "w") as f:
            f.write(header + data)

    def add_tests_to_pom_xml(
        self, include_tests_file, report_path, covered_tests=[], subsumption=None
    ):
        with open(include_tests_file, "w") as f:
            for test_name in covered_tests:
                if test_name != "":
                    test_name = test_name[0]  # tuple to string
                    # test_name = test_name.split(".")
                    # test_name = test_name[-2] + "#" + test_name[-1]
                f.write(test_name + "\n")
        shutil.rmtree(report_path, ignore_errors=True)
        os.makedirs(report_path, exist_ok=True)

        # ET.register_namespace("", "http://maven.apache.org/POM/4.0.0")
        tree = ET.parse(self.build_file_path)
        root = tree.getroot()
        namespace = self.return_namespace(root)
        ET.register_namespace("", namespace)
        # Find the <build> element
        for build_element in root.findall(f"{{{namespace}}}build"):
            if build_element is None:
                build_element = ElementTree.SubElement(root, "build")
            # Find or create the <plugins> element
            plugins_element = build_element.find(
                f"{{{namespace}}}plugins"
            )
            if plugins_element is None:
                plugins_element = ElementTree.SubElement(
                    build_element, "plugins")
            plugins = plugins_element.findall(
                f"{{{namespace}}}plugin"
            )
            for plugin in plugins:
                artifactId = plugin.find(
                    f"{{{namespace}}}artifactId",
                )

                if (
                    artifactId is not None
                    and artifactId.text == "maven-surefire-plugin"
                ):
                    configuration_element = plugin.find(
                        f"{{{namespace}}}configuration"
                    )
                    if configuration_element is None:
                        configuration_element = ElementTree.SubElement(
                            plugin, "configuration"
                        )

                    if self.runAllTests == False:
                        fast_fail_element = configuration_element.find(
                            f".//{{{namespace}}}failFast"
                        )
                        if fast_fail_element == None:
                            fast_fail_element = ElementTree.SubElement(
                                configuration_element, "failFast"
                            )
                        fast_fail_element.text = "true"

                    includes_file_element = configuration_element.find(
                        f".//{{{namespace}}}includesFile"
                    )
                    if includes_file_element == None:
                        includes_file_element = ElementTree.SubElement(
                            configuration_element, "includesFile"
                        )
                    includes_file_element.text = self.include_file_add

                    reportsDirectory = configuration_element.find(
                        f"{{{namespace}}}reportsDirectory",
                    )
                    if reportsDirectory is None:
                        reportsDirectory = ElementTree.SubElement(
                            configuration_element, "reportsDirectory"
                        )
                    reportsDirectory.text = str(report_path)

        # Save the modified pom.xml file
        tree.write(self.build_file_path)

    def add_tests_to_build_xml(
        self, junit_target, report_path, covered_tests=None, subsumption=False
    ):
        if covered_tests is None:
            covered_tests = []
        os.chdir(self.project_path)
        shutil.rmtree(report_path, ignore_errors=True)
        os.makedirs(report_path, exist_ok=True)

        data_dump = ""
        for test in covered_tests:
            test = test[0]  # tuple to string

            ind = test.rfind("#")
            test_element = ET.Element("test")
            test_element.set("name", test[:ind])
            test_element.set("methods", test[ind + 1:])
            if subsumption:
                os.makedirs(os.path.join(report_path, test), exist_ok=True)
                test_element.set(
                    "todir",
                    os.path.join(report_path, test),
                )
            data_dump += ET.tostring(test_element).decode("utf-8") + "\n"
        with open(
            self.include_file_add,
            "w",
        ) as f:
            f.write(data_dump)

    def _update_juint_version_add_clover_build_xml(
        self, junit_target, subsumption=False
    ):
        """
        update the junit version of the build.xml file to 4.13.2
        """

        tree = ET.parse(self.build_file_path)
        root = tree.getroot()
        os.chdir(self.project_path)
        with resources.as_file(
            resources.files("mediumdarwin").joinpath(
                "jar").joinpath("clover.jar")
        ) as clover_file_path:
            with open(clover_file_path, "rb") as clover_file:
                new_file_path = str(
                    os.path.join(
                        self.project_path, "LittleDarwinResults", "jar", "clover.jar"
                    )
                )
                os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
                with open(new_file_path, "wb") as new_file:
                    new_file.write(clover_file.read())
        with resources.as_file(
            resources.files("mediumdarwin").joinpath(
                "jar").joinpath("junit-4.13.2.jar")
        ) as clover_file_path:
            with open(clover_file_path, "rb") as clover_file:
                new_file_path = str(
                    os.path.join(
                        self.project_path,
                        "LittleDarwinResults",
                        "jar",
                        "junit-4.13.2.jar",
                    )
                )
                os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
                with open(new_file_path, "wb") as new_file:
                    new_file.write(clover_file.read())
        with resources.as_file(
            resources.files("mediumdarwin").joinpath(
                "jar").joinpath("hamcrest-2.2.jar")
        ) as clover_file_path:
            with open(clover_file_path, "rb") as clover_file:
                new_file_path = str(
                    os.path.join(
                        self.project_path,
                        "LittleDarwinResults",
                        "jar",
                        "hamcrest-2.2.jar",
                    )
                )
                os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
                with open(new_file_path, "wb") as new_file:
                    new_file.write(clover_file.read())

        property_element = ElementTree.Element("taskdef")
        property_element.set("resource", "cloverlib.xml")
        property_element.set("classpath", "${clover.jar}")
        root.insert(0, property_element)

        property_element = ElementTree.Element("property")
        property_element.set("name", "clover.jar")
        property_element.set(
            "location",
            str(
                os.path.join(
                    self.project_path, "LittleDarwinResults", "jar", "clover.jar"
                )
            ),
        )
        root.insert(0, property_element)

        property_element = ElementTree.Element("property")
        property_element.set("name", "hamcrest-2.2.jar")
        property_element.set(
            "location",
            str(
                os.path.join(
                    self.project_path, "LittleDarwinResults", "jar", "hamcrest-2.2.jar"
                )
            ),
        )
        root.insert(0, property_element)

        property_element = ElementTree.Element("property")
        property_element.set("name", "junit-4.13.2.jar")
        property_element.set(
            "location",
            str(
                os.path.join(
                    self.project_path, "LittleDarwinResults", "jar", "junit-4.13.2.jar"
                )
            ),
        )

        root.insert(0, property_element)

        classpath_element = ElementTree.Element("classpath")
        pathelement_element = ElementTree.SubElement(
            classpath_element, "pathelement")
        pathelement_element.set("location", "build/classes")
        pathelement_element = ElementTree.SubElement(
            classpath_element, "pathelement")
        pathelement_element.set("location", "${junit-4.13.2.jar}")

        classpath_clover = ElementTree.Element("classpath")
        pathelement_element = ElementTree.SubElement(
            classpath_clover, "pathelement")
        pathelement_element.set("location", "${clover.jar}")

        classpath_hamcrest = ElementTree.Element("classpath")
        pathelement_element = ElementTree.SubElement(
            classpath_hamcrest, "pathelement")
        pathelement_element.set("location", "${hamcrest-2.2.jar}")

        test_target_element = root.find(".//*[@name='" + junit_target + "']")
        junit_element = test_target_element.find(".//junit")
        #! throw an error if junit element is not found
        # add classpath, clover and hamcrest to junit element
        if self.runAllTests:
            junit_element.set("haltonfailure", "no")
            junit_element.set("haltonerror", "no")
        else:
            junit_element.set("haltonfailure", "yes")
            junit_element.set("haltonerror", "yes")
        junit_element.insert(0, classpath_element)
        junit_element.insert(0, classpath_hamcrest)
        junit_element.insert(0, classpath_clover)

        target_with_clover = ElementTree.SubElement(root, "target")
        target_with_clover.set("name", "with.clover.mediumdarwin")
        taskdef_element = ElementTree.SubElement(target_with_clover, "taskdef")
        taskdef_element.set("resource", "cloverlib.xml")
        taskdef_element.set("classpath", "${clover.jar}")
        clover_setup_element = ElementTree.SubElement(
            target_with_clover, "clover-setup"
        )
        clover_setup_element.set(
            "initstring",
            str(os.path.join(self.project_path, "LittleDarwinResults", "clover.db")),
        )

        test_target_element = root.find(".//*[@name='" + junit_target + "']")
        junit_element = test_target_element.find(".//junit")
        dump = junit_element.text

        # remove all batchtest elements
        for batchtest in junit_element.findall(".//batchtest"):
            dump += ET.tostring(batchtest).decode("utf-8")
            junit_element.remove(batchtest)

        # remove all test elements
        for test_tag in junit_element.findall(".//test"):
            dump += ET.tostring(test_tag).decode("utf-8")
            junit_element.remove(test_tag)

        # add a line of text

        junit_element.text = junit_element.text + "test_file_for_clover;"

        for formatter in junit_element.findall(".//formatter"):
            junit_element.remove(formatter)
        if subsumption:
            formatter_element = ElementTree.SubElement(
                junit_element, "formatter")
            formatter_element.set("type", "xml")
        else:
            formatter_element = ElementTree.SubElement(
                junit_element, "formatter")
            formatter_element.set("type", "plain")
            formatter_element.set("usefile", "false")

        tree.write(self.build_file_path)
        # write this header to the file
        header = (
            '<?xml version="1.0"?><!DOCTYPE project [<!ENTITY test_file_for_clover SYSTEM "'
            + self.include_file_add
            + '">]>'
        )
        with open(self.build_file_path, "r") as f:
            data = f.read()
        data = data.replace("test_file_for_clover", "&test_file_for_clover")
        with open(self.build_file_path, "w") as f:
            f.write(header + data)

        with open(
            self.include_file_add,
            "w",
        ) as f:
            f.write(dump)

    def return_namespace(self, element):
        m = re.match(r'\{(.*)\}', element.tag)
        return m.group(1) if m else ''

    def _update_juint_version_add_clover_pom_xml(self):
        # ET.register_namespace("", "http://maven.apache.org/POM/4.0.0")
        tree = ET.parse(self.build_file_path)
        root = tree.getroot()
        namespace = self.return_namespace(root)
        ET.register_namespace("", namespace)

        # update junit version
        junit_exists = False
        for dependency in root.findall(
            f".//{{{namespace}}}dependency"
        ):
            artifact_id = dependency.find(
                f"{{{namespace}}}artifactId"
            ).text
            if artifact_id == "junit":
                junit_exists = True
                version = dependency.find(
                    f"{{{namespace}}}version"
                )
                if version is None:
                    version = ET.SubElement(
                        dependency, f"{{{namespace}}}version"
                    )
                    version.text = "4.13.2"
                version = version.text
                if version <= "4.13.2":
                    dependency.find(
                        f"{{{namespace}}}version"
                    ).text = "4.13.2"
            if artifact_id == "junit-jupiter-engine":
                junit_exists = True
        if not junit_exists:
            dependencies = root.find(
                f".//{{{namespace}}}dependencies"
            )
            if dependencies is None:
                dependencies = ET.SubElement(
                    root, f"{{{namespace}}}dependencies"
                )
            junit_dependency = ET.SubElement(
                dependencies, f"{{{namespace}}}dependency"
            )
            ET.SubElement(
                junit_dependency, f"{{{namespace}}}groupId"
            ).text = "junit"
            ET.SubElement(
                junit_dependency, f"{{{namespace}}}artifactId"
            ).text = "junit"
            ET.SubElement(
                junit_dependency, f"{{{namespace}}}version"
            ).text = "4.13.2"

        # check if a build element exists
        build_element = root.find(f"{{{namespace}}}build")
        if build_element is None:
            build_element = ET.SubElement(
                root, f"{{{namespace}}}build"
            )
        # Find the <build> element
        for build_element in root.findall(f"{{{namespace}}}build"):
            if build_element is None:
                build_element = ElementTree.SubElement(root, "build")
            # Find or create the <plugins> element
            plugins_element = build_element.find(
                f"{{{namespace}}}plugins"
            )
            if plugins_element is None:
                plugins_element = ElementTree.SubElement(
                    build_element, "plugins")

            no_surefire = True
            no_compiler = True
            # Search for the surefire plugin
            for plugin in plugins_element.findall(
                f".//{{{namespace}}}plugin"
            ):
                artifact_id = plugin.find(
                    f".//{{{namespace}}}artifactId"
                )
                if (
                    artifact_id is not None
                    and artifact_id.text == "maven-compiler-plugin"
                ):
                    no_compiler = False
                    configuration_element = plugin.find(
                        f".//{{{namespace}}}configuration"
                    )
                    source_element = configuration_element.find(
                        f".//{{{namespace}}}source"
                    )
                    if source_element is None:
                        source_element = ElementTree.SubElement(
                            configuration_element, "source"
                        )
                    source_element.text = "1.8"
                    target_element = configuration_element.find(
                        f".//{{{namespace}}}target"
                    )
                    if target_element is None:
                        target_element = ElementTree.SubElement(
                            configuration_element, "target"
                        )
                    target_element.text = "1.8"
                    # update version
                    version = plugin.find(
                        f"{{{namespace}}}version")
                    if version is None:
                        version = ElementTree.SubElement(plugin, "version")
                    version.text = "3.8.1"

                if artifact_id != None and artifact_id.text == "maven-surefire-plugin":
                    no_surefire = False
                    # Create a new <plugin> element for the surefire plugin
                    plugin_surefire_element = plugin
                    # Add the necessary child elements to the <plugin> element
                    version_element = plugin_surefire_element.find(
                        f".//{{{namespace}}}version"
                    )
                    if version_element == None:
                        version_element = ElementTree.SubElement(
                            plugin_surefire_element, "version"
                        )
                    version_element.text = "3.0.0"
                    configuration_element = plugin_surefire_element.find(
                        f".//{{{namespace}}}configuration"
                    )
                    if configuration_element == None:
                        configuration_element = ElementTree.SubElement(
                            plugin_surefire_element, "configuration"
                        )
                    if self.runAllTests == False:
                        fast_fail_element = configuration_element.find(
                            f".//{{{namespace}}}failFast"
                        )
                        if fast_fail_element == None:
                            fast_fail_element = ElementTree.SubElement(
                                configuration_element, "failFast"
                            )
                        fast_fail_element.text = "true"

                    includes_file_element = configuration_element.find(
                        f".//{{{namespace}}}includesFile"
                    )
                    if includes_file_element == None:
                        includes_file_element = ElementTree.SubElement(
                            configuration_element, "includesFile"
                        )

                    includes_file_element.text = self.include_file_add
                    report_element = configuration_element.find(
                        f".//{{{namespace}}}reportsDirectory"
                    )
                    if report_element == None:
                        report_element = ElementTree.SubElement(
                            configuration_element, "reportsDirectory"
                        )
                    report_element.text = str(
                        os.path.join(
                            self.project_path, "LittleDarwinResults", "test-reports"
                        )
                    )
            if no_surefire:
                # Create a new <plugin> element for the surefire plugin
                plugin_surefire_element = ElementTree.SubElement(
                    plugins_element, "plugin"
                )
                # Add the necessary child elements to the <plugin> element
                group_id_element = ElementTree.SubElement(
                    plugin_surefire_element, "groupId"
                )
                group_id_element.text = "org.apache.maven.plugins"
                artifact_id_element = ElementTree.SubElement(
                    plugin_surefire_element, "artifactId"
                )
                artifact_id_element.text = "maven-surefire-plugin"
                version_element = ElementTree.SubElement(
                    plugin_surefire_element, "version"
                )
                version_element.text = "3.0.0"
                configuration_element = ElementTree.SubElement(
                    plugin_surefire_element, "configuration"
                )
                if self.runAllTests == False:
                    fast_fail_element = ElementTree.SubElement(
                        configuration_element, "failFast"
                    )
                    fast_fail_element.text = "true"
                includes_file_element = ElementTree.SubElement(
                    configuration_element, "includesFile"
                )

                includes_file_element.text = self.include_file_add
                report_element = ElementTree.SubElement(
                    configuration_element, "reportsDirectory"
                )
                report_element.text = str(
                    os.path.join(
                        self.project_path, "LittleDarwinResults", "test-reports"
                    )
                )
            # Create a new <plugin> element for the Clover plugin
            plugin_clover_element = ElementTree.SubElement(
                plugins_element, "plugin")
            # Add the necessary child elements to the <plugin> element
            group_id_element = ElementTree.SubElement(
                plugin_clover_element, "groupId")
            group_id_element.text = "org.openclover"
            artifact_id_element = ElementTree.SubElement(
                plugin_clover_element, "artifactId"
            )
            artifact_id_element.text = "clover-maven-plugin"
            version_element = ElementTree.SubElement(
                plugin_clover_element, "version")
            version_element.text = "4.5.2"

            clover_configuration_element = ElementTree.SubElement(
                plugin_clover_element, "configuration"
            )
            generate_pdf_element = ElementTree.SubElement(
                clover_configuration_element, "generatePdf"
            )
            generate_pdf_element.text = "false"
            generateXmlElement = ElementTree.SubElement(
                clover_configuration_element, "generateXml"
            )
            generateXmlElement.text = "false"
            generateHtmlElement = ElementTree.SubElement(
                clover_configuration_element, "generateHtml"
            )
            generateHtmlElement.text = "false"
            generateJsonElement = ElementTree.SubElement(
                clover_configuration_element, "generateJson"
            )
            generateJsonElement.text = "false"

            # ? I don't know why this is necessary, but after adding the clover plugin, the build fails unless this is added
            if no_compiler:
                # Create a new <plugin> element for the maven compiler
                plugin_maven_element = ElementTree.SubElement(
                    plugins_element, "plugin")
                # Add the necessary child elements to the <plugin> element
                group_id_element = ElementTree.SubElement(
                    plugin_maven_element, "groupId"
                )
                group_id_element.text = "org.apache.maven.plugins"
                artifact_id_element = ElementTree.SubElement(
                    plugin_maven_element, "artifactId"
                )
                artifact_id_element.text = "maven-compiler-plugin"
                version_element = ElementTree.SubElement(
                    plugin_maven_element, "version"
                )
                version_element.text = "3.8.1"
                configuration_element = ElementTree.SubElement(
                    plugin_maven_element, "configuration"
                )
                source_element = ElementTree.SubElement(
                    configuration_element, "source")
                source_element.text = "1.8"
                target_element = ElementTree.SubElement(
                    configuration_element, "target")
                target_element.text = "1.8"

        Path(self.include_file_add).touch()
        # Save the modified pom.xml file
        tree.write(self.build_file_path)

    def __init__(
        self,
        project_path,
        clover_db_extractor_path,
        build_file_path,
        build_type,
        sqlDB_path,
        D_args=[],
        runAllTests=False,
        timeout=60,
    ) -> None:
        self.runAllTests = runAllTests
        self.project_path = project_path
        self.clover_db_extractor_path = str(clover_db_extractor_path)
        self.timeout = timeout
        self.build_type = build_type
        self.build_file_path = build_file_path
        self.D_args = D_args
        self.sqlDB_path = sqlDB_path
        # If the build type is maven, and the build file path is not specified, set it to the default
        if self.build_type.endswith("mvn") and self.build_file_path is None:
            self.build_file_path = str(
                os.path.join(self.project_path, "pom.xml"))
        # If the build type is ant, and the build file path is not specified, set it to the default
        elif self.build_type.endswith("ant") and self.build_file_path is None:
            self.build_file_path = str(
                os.path.join(self.project_path, "build.xml"))
        # If the build type is gradle, and the build file path is not specified, set it to the default
        elif self.build_type.endswith("gradle") and self.build_file_path is None:
            self.build_file_path = str(os.path.join(
                self.project_path, "build.gradle"))
        # the path to the coverage.xml file

    def search_coverage_XML(self, file_name, line_number):
        file_name = os.path.realpath(file_name)
        if self.tree_clover == None:
            self.__read_coverage_XML()
        test_names = []
        test_names_1 = []
        found = False
        for file in self.tree_clover:
            if os.path.realpath(file["path"]) == file_name:
                for line in file["lines"]:
                    if line["number"] == str(line_number):
                        found = True
                        test_names = line["tests"]
                        break
                    elif line["number"] == "-1":
                        test_names_1 = line["tests"]
                if found == True:
                    break
        if found == False:
            return test_names_1
        return test_names

    def search_line_numbers(
        self, filename, regex=r"line number in original file:\s?(\d+)\s?"
    ):
        """
        docstring
        """
        with open(filename, "r") as file:
            text = file.read()
        line_numbers = []
        matches = re.findall(regex, text)
        for match in matches:
            line_numbers.append(int(match))
        return line_numbers

    def restore_the_build_file(self):
        shutil.move(self.build_file_path + ".bak", self.build_file_path)

    def __del__(self):
        # ! I moved restoring the original file to another function because of parallel run (I have to test this modification later)
        if self.tree_clover != None:
            del self.tree_clover

    def run_clover(self, test_target, junit_target):
        if self.build_type.endswith("mvn"):
            self._prepare_pom()
            #! **************
            self.clover_db_path = str(
                os.path.join(self.project_path,
                             "LittleDarwinResults", "clover.db")
            )
            self.clover_tmp_db_path = str(
                os.path.join(
                    self.project_path, "LittleDarwinResults", "tmp", "clover.db"
                )
            )
            commandString = [self.build_type, "-f",
                             self.build_file_path, "clean"]
            commandString.extend(self.D_args)
            commandString += [
                "org.openclover:clover-maven-plugin:setup",
                test_target,
                "org.openclover:clover-maven-plugin:clover",
                "-Dmaven.clover.singleCloverDatabase=true",
                "-Dmaven.clover.cloverDatabase=" + self.clover_tmp_db_path,
            ]

            processKilled, processExitCode, runOutput, time_delta = timeoutAlternative(
                commandString,
                workingDirectory=self.project_path,
                timeout=int(self.timeout),
            )

            if processKilled or processExitCode:
                raise subprocess.CalledProcessError(
                    1 if processKilled else processExitCode,
                    commandString,
                    runOutput,
                )

            commandString = [
                self.build_type,
                "-f",
                self.build_file_path,
            ]
            commandString.extend(self.D_args)
            commandString += [
                "org.openclover:clover-maven-plugin:merge",
                "-Dmaven.clover.cloverMergeDatabase=" + self.clover_db_path,
                "-Dmaven.clover.merge.basedir="
                + str(os.path.join(self.project_path,
                      "LittleDarwinResults", "tmp")),
                "clover:clean",
            ]
            processKilled, processExitCode, runOutput, time_delta = timeoutAlternative(
                commandString,
                workingDirectory=self.project_path,
                timeout=int(self.timeout),
            )

            if processKilled or processExitCode:
                raise subprocess.CalledProcessError(
                    1 if processKilled else processExitCode,
                    commandString,
                    runOutput,
                )

            # I moved restoring the pom.xml to the destuctor because some of the plugins were necessary to exclude tests
            # the path to the clover.db file
            commandString = [
                "java",
                "-jar",
                self.clover_db_extractor_path,
                "-f",
                self.clover_db_path,
                "-output_db",
                self.sqlDB_path,
            ]
            processKilled, processExitCode, runOutput, time_delta = timeoutAlternative(
                commandString,
                workingDirectory=self.project_path,
                timeout=int(self.timeout),
            )
            if processKilled or processExitCode:
                raise subprocess.CalledProcessError(
                    1 if processKilled else processExitCode,
                    commandString,
                    runOutput,
                )
        elif self.build_type.endswith("ant"):
            self._prepare_build_xml(junit_target=junit_target)
            # Run Clover code coverage
            #! **************
            commandString = [
                self.build_type,
                "-lib",
                str(
                    os.path.join(
                        self.project_path, "LittleDarwinResults", "jar", "clover.jar"
                    )
                ),
                "-f",
                self.build_file_path,
                "clean",
                "with.clover.mediumdarwin",
                test_target,
                "clean",
            ]
            commandString.extend(self.D_args)

            processKilled, processExitCode, runOutput, time_delta = timeoutAlternative(
                commandString,
                workingDirectory=self.project_path,
                timeout=int(self.timeout),
            )

            if processKilled or processExitCode:
                raise subprocess.CalledProcessError(
                    1 if processKilled else processExitCode,
                    commandString,
                    runOutput,
                )
            # I moved restoring the pom.xml to the destuctor because some of the plugins were necessary to exclude tests
            # the path to the clover.db file
            self.clover_db_path = str(
                os.path.join(self.project_path,
                             "LittleDarwinResults", "clover.db")
            )

            processKilled, processExitCode, runOutput, time_delta = timeoutAlternative(
                [
                    "java",
                    "-jar",
                    str(self.clover_db_extractor_path),
                    "-f",
                    self.clover_db_path,
                    "-output_db",
                    self.sqlDB_path,
                ],
                workingDirectory=self.project_path,
                timeout=int(self.timeout),
            )
            if processKilled or processExitCode:
                raise subprocess.CalledProcessError(
                    1 if processKilled else processExitCode,
                    commandString,
                    runOutput,
                )
            self._clean_clover_from_build_xml(junit_target=junit_target)
