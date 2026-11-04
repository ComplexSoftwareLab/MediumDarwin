"""Tests for per-mutant JUnit report lookup used when recording results."""
import os
import tempfile
import unittest

from mediumdarwin.Database import Database
from mediumdarwin.Schemata import Schemata
from mediumdarwin.SharedFunctions import mutant_test_reports_dir


class TestMutantTestReportsDir(unittest.TestCase):
    def test_source_relative_name_is_joined_not_re_relpathed(self):
        results = os.path.join("proj", "MediumDarwinResults")
        file_name = "java/org/apache/commons/exec/CommandLine.java"
        source = os.path.join("proj", "src", "main")
        got = mutant_test_reports_dir(results, file_name, 0, source)
        expected = os.path.join(
            results,
            "java",
            "org",
            "apache",
            "commons",
            "exec",
            "CommandLine.java",
            "0-test_reports",
        )
        self.assertEqual(os.path.normpath(got), os.path.normpath(expected))

    def test_absolute_name_is_made_source_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "src", "main")
            abs_file = os.path.join(source, "java", "Foo.java")
            results = os.path.join(tmp, "MediumDarwinResults")
            got = mutant_test_reports_dir(results, abs_file, 12, source)
            expected = os.path.join(
                results, "java", "Foo.java", "12-test_reports"
            )
            self.assertEqual(os.path.normpath(got), os.path.normpath(expected))


class TestUpdateMutationTestTableFindsReports(unittest.TestCase):
    def _seed_mutant(self, db, options, build_relative_name="src/main/java/Foo.java"):
        file_id = db.insert_file(build_relative_name, options=options)
        db.insert_mutation(1, file_id, 0, 0, 1, 1, "x", 1)
        db.insert_mutant(0, 1)
        db.insert_data("test", "qualified_name", ["org.example.Bar.testIt"])
        return file_id

    def test_killed_xml_is_not_recorded_as_build_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "src", "main")
            os.makedirs(os.path.join(source, "java"))
            reports = os.path.join(
                tmp, "MediumDarwinResults", "java", "Foo.java", "0-test_reports"
            )
            os.makedirs(reports)
            xml = (
                '<?xml version="1.0"?>\n'
                '<testsuite name="Bar" tests="1" failures="1" errors="0">\n'
                '  <testcase classname="org.example.Bar" name="testIt" time="0.01">\n'
                '    <failure message="assert">expected 1</failure>\n'
                "  </testcase>\n"
                "</testsuite>\n"
            )
            with open(
                os.path.join(reports, "TEST-org.example.Bar.xml"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(xml)

            schemata = Schemata(mockArgs=["--quiet", "-p", source, "-t", tmp])
            db_path = os.path.join(
                tmp, "MediumDarwinResults", "mutationdatabase.db"
            )
            db = Database(db_path)
            db.create_tables()
            self._seed_mutant(db, schemata.options)

            try:
                schemata.updateMutationTestTable(
                    schemata.options, db, file_name="java/Foo.java", mutant_id=0
                )

                rows = db.fetch_data("mutant_test")
                self.assertTrue(rows)
                results = {row[2] for row in rows}
                self.assertNotIn(Database.RES_ID_BUILD_FAILURE, results)
                self.assertIn(Database.RES_ID_KILLED_BY_FAILURE_MUTANT, results)
            finally:
                db.conn.close()

    def test_missing_reports_keep_known_killed_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "src", "main")
            os.makedirs(source)
            schemata = Schemata(mockArgs=["--quiet", "-p", source, "-t", tmp])
            db_path = os.path.join(
                tmp, "MediumDarwinResults", "mutationdatabase.db"
            )
            db = Database(db_path)
            db.create_tables()
            self._seed_mutant(db, schemata.options)

            try:
                schemata.updateMutationTestTable(
                    schemata.options,
                    db,
                    file_name="java/Foo.java",
                    mutant_id=0,
                    fallback_result=Database.RES_ID_KILLED_MUTANT,
                )

                rows = db.fetch_data("mutant_test")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][2], Database.RES_ID_KILLED_MUTANT)
                self.assertNotEqual(rows[0][2], Database.RES_ID_BUILD_FAILURE)
            finally:
                db.conn.close()


if __name__ == "__main__":
    unittest.main()
