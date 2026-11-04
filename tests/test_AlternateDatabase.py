"""Tests for --use-alternate-database / sqlDBPath resolution."""
import os
import tempfile
import unittest
from argparse import Namespace
from optparse import OptionParser

from mediumdarwin.SharedFunctions import (
    DUMMY_SENTINEL,
    resolve_sql_db_path,
    ensure_sql_db_parent,
)
from mediumdarwin.Schemata import Schemata
from mediumdarwin.MediumDarwin import MediumDarwin


class TestResolveSqlDbPath(unittest.TestCase):
    def test_default_uses_little_darwin_results(self):
        options = Namespace(
            buildPath=os.path.join("proj", "root"),
            alternateDb=DUMMY_SENTINEL,
        )
        expected = os.path.abspath(
            os.path.join("proj", "root", "MediumDarwinResults", "mutationdatabase.db")
        )
        self.assertEqual(resolve_sql_db_path(options), expected)

    def test_alternate_path_is_used_verbatim(self):
        options = Namespace(
            buildPath=os.path.join("proj", "root"),
            alternateDb=os.path.join("experiments", "run-a.db"),
        )
        self.assertEqual(
            resolve_sql_db_path(options),
            os.path.abspath(os.path.join("experiments", "run-a.db")),
        )

    def test_empty_alternate_falls_back_to_default(self):
        options = Namespace(buildPath="proj", alternateDb="   ")
        self.assertEqual(
            resolve_sql_db_path(options),
            os.path.abspath(
                os.path.join("proj", "MediumDarwinResults", "mutationdatabase.db")
            ),
        )


class TestSchemataHonorsAlternateDatabase(unittest.TestCase):
    def test_schemata_sql_db_path_follows_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            alt_dir = os.path.join(tmp, "experiments")
            alt_db = os.path.join(alt_dir, "run-a.db")
            schemata = Schemata(
                mockArgs=[
                    "--quiet",
                    "-p",
                    src,
                    "-t",
                    tmp,
                    "--use-alternate-database",
                    alt_db,
                ]
            )
            self.assertEqual(os.path.abspath(schemata.sqlDBPath), os.path.abspath(alt_db))
            self.assertTrue(os.path.isdir(alt_dir))
            default_db = os.path.join(tmp, "MediumDarwinResults", "mutationdatabase.db")
            self.assertNotEqual(
                os.path.abspath(schemata.sqlDBPath), os.path.abspath(default_db)
            )

    def test_schemata_default_sql_db_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            schemata = Schemata(mockArgs=["--quiet", "-p", src, "-t", tmp])
            expected = os.path.abspath(
                os.path.join(tmp, "MediumDarwinResults", "mutationdatabase.db")
            )
            self.assertEqual(os.path.abspath(schemata.sqlDBPath), expected)


class TestMediumDarwinHonorsAlternateDatabase(unittest.TestCase):
    def test_mediumdarwin_main_sets_alternate_sql_db_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            alt_db = os.path.join(tmp, "experiments", "run-b.db")
            md = MediumDarwin()
            md.main(
                mockArgs=[
                    "--quiet",
                    "-p",
                    src,
                    "-t",
                    tmp,
                    "--use-alternate-database",
                    alt_db,
                ]
            )
            self.assertEqual(os.path.abspath(md.sqlDBPath), os.path.abspath(alt_db))
            self.assertTrue(os.path.isdir(os.path.dirname(alt_db)))

    def test_parse_cmd_args_then_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            alt_db = os.path.join(tmp, "custom.db")
            parser = OptionParser()
            md = MediumDarwin()
            options, _, _, _ = md.parseCmdArgs(
                parser,
                mockArgs=[
                    "--quiet",
                    "-t",
                    tmp,
                    "--use-alternate-database",
                    alt_db,
                ],
            )
            self.assertEqual(resolve_sql_db_path(options), os.path.abspath(alt_db))


class TestEnsureSqlDbParent(unittest.TestCase):
    def test_creates_missing_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "nested", "more", "exp.db")
            ensure_sql_db_parent(db_path)
            self.assertTrue(os.path.isdir(os.path.dirname(db_path)))
            self.assertFalse(os.path.exists(db_path))


if __name__ == "__main__":
    unittest.main()
