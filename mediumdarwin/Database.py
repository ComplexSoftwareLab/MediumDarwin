import sqlite3
import dill
from mediumdarwin.SharedFunctions import getAllInstantiableSubclasses
from mediumdarwin.SharedFunctions import MutationOperator


class Database:
    NO_TEST = -1
    INSTURMENTED_NOT_COVERED = -2
    NO_INFO = -3

    RES_ID_BUILD_FAILURE = -1
    RES_ID_KILLED_MUTANT = 0
    RES_ID_KILLED_BY_FAILURE_MUTANT = 0
    RES_ID_KILLED_BY_ERROR_MUTANT = 2
    RES_ID_SURVIVED_MUTANT = 1
    RES_ID_UNCOVERED = -2

    def insert_file(self, file_name):
        return self.insert_data("file", "name", [file_name])

    def insert_mutation(
        self,
        id,
        file_id,
        node_id,
        startPos,
        endPos,
        lineNo,
        replacementText,
        mutation_operator_id,
        node_json=[],
        new_node_id=[],
        new_node_type=[],
        is_compile_time=0,
        object_=None
    ):
        return self.insert_data(
            "mutation",
            "id, file_id, node_id, startPos, endPos, lineNo, replacementText, mutation_operator_id, new_node_json, new_node_id, new_node_type, compile_time, object",
            [
                id,
                file_id,
                node_id,
                startPos,
                endPos,
                lineNo,
                replacementText,
                mutation_operator_id,
                repr(node_json),
                repr(new_node_id),
                repr(new_node_type),
                str(is_compile_time),
                "NULL" if object_ is None else object_,
            ],
        )

    def insert_mutant(self, mutant_id, mutation_id):
        return self.insert_data("mutant", "id, mutation_id", [mutant_id, mutation_id])

    def __init__(self, db_name):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()

    def create_tables(self):
        self.create_table("mutation_operator",
                          "id INTEGER PRIMARY KEY, name TEXT")
        # self.create_trigger_for_mutantion_operator()
        subclasses = getAllInstantiableSubclasses(MutationOperator)
        for subclass in subclasses:
            self.insert_data("mutation_operator", "name", [subclass.__name__])

        self.create_table(
            "mutant",
            "id INTEGER, mutation_id INTEGER, FOREIGN KEY (mutation_id) REFERENCES mutation(id)",
        )
        self.create_table(
            "test_coverage",
            "file_id INTEGER, line_no INTEGER, test_id TEXT",
        )
        self.create_table(
            "test",
            "id INTEGER PRIMARY KEY, qualified_name TEXT",
        )
        self.insert_data("test", "id,qualified_name", [
                         self.INSTURMENTED_NOT_COVERED, "-"])
        self.insert_data("test", "id,qualified_name", [self.NO_TEST, "?"])
        self.insert_data("test", "id,qualified_name", [self.NO_INFO, "*"])

        self.create_table(
            "file",
            "name TEXT, id INTEGER PRIMARY KEY, json TEXT",
        )
        # self.create_trigger_for_file()

        self.create_table(
            "mutation",
            "id INTEGER PRIMARY KEY, file_id INTEGER, startPos INTEGER, endPos INTEGER, lineNo INTEGER, node_id INTEGER, mutation_operator_id INTEGER, replacementText TEXT, new_node_json TEXT, new_node_id TEXT, new_node_type TEXT, compile_time BOOL, object BLOB",
        )
        self.create_table(
            "mutant_test",
            "mutant_id INTEGER, test_id INTEGER, result INTEGER, time TEXT,message TEXT",
        )

    def create_table(self, table_name, columns):
        query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})"
        self.cursor.execute(query)

    def insert_data(self, table_name, columns, values):
        value_holder = ",".join(["?"] * len(values))
        query = f"INSERT INTO {table_name} ({columns}) VALUES({value_holder})"
        try:
            self.cursor.execute(query, (values))
            self.conn.commit()
        except Exception as e:
            print(str(e) + " in " + query)
            return False
        if self.cursor.rowcount > 0:
            return self.cursor.lastrowid
        else:
            return False

    def insert_many(self, table_name, columns, values):
        if len(values) == 0:
            return
        value_holder = ",".join(["?"] * len(values[0]))
        query = f"INSERT INTO {table_name} ({columns}) VALUES({value_holder})"
        try:
            self.cursor.executemany(query, values)
            self.conn.commit()
        except Exception as e:
            print(e)
            return False
        if self.cursor.rowcount > 0:
            return self.cursor.lastrowid
        else:
            return False

    def construct_compile_mutations(self):
        compile_mutations = []
        query = "SELECT name as file_name, object from mutation JOIN mutant on mutant.mutation_id=mutation.id JOIN file on mutation.file_id=file.id WHERE mutation.compile_time=1"
        self.cursor.execute(query)
        results = self.cursor.fetchall()
        for res in results:
            compile_mutations.append((res[0], dill.loads(res[1])))
        return compile_mutations

    def construct_mutant_dict(self):
        query = "SELECT file.name as file_name, mutant.id as mutant_id, mutation.id as mutation_id, GROUP_CONCAT(mutation.id, ', ') as mutation_list FROM mutation JOIN mutant on mutant.mutation_id=mutation.id JOIN file on mutation.file_id=file.id GROUP BY mutant.id"
        self.cursor.execute(query)
        results = self.cursor.fetchall()

        mutants_dict = dict()
        for res in results:
            if res[0] not in mutants_dict.keys():
                mutants_dict[res[0]] = dict()
            mutants_dict[res[0]][res[1]] = eval("set([" + res[3] + "])")

        return mutants_dict

    def fetch_build_failure_mutants(self):
        query = "SELECT file.name as name, mutant.id as mutant_id FROM mutant_test JOIN mutant ON mutant.id = mutant_test.mutant_id JOIN mutation ON mutation.id = mutant.mutation_id JOIN file ON mutation.file_id = file.id WHERE result = -1"
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def fetch_data(self, table_name, columns="*", condition=None):
        query = f"SELECT {columns} FROM {table_name}"
        if condition:
            query += f" WHERE {condition}"
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def fetch_coverage(self, file_name, line_no):
        query = f"SELECT test.qualified_name from test_coverage JOIN file on file.id=test_coverage.file_id JOIN test on test.id=test_coverage.test_id WHERE file.name='{file_name}' AND test_coverage.line_no IN ({line_no})"
        self.cursor.execute(query)
        file_coverage = self.cursor.fetchall()
        return file_coverage

    def fetch_all_coverage(self):
        query = f"SELECT test.qualified_name from test where test.id!=-2"
        self.cursor.execute(query)
        file_coverage = self.cursor.fetchall()
        return file_coverage

    def fetch_mutated_files_count(self):
        query = "SELECT DISTINCT SUM(COUNT(*)) OVER() AS total_count FROM file JOIN mutation ON file.id = mutation.file_id GROUP BY file.name ORDER BY file.name"
        self.cursor.execute(query)
        return int(self.cursor.fetchall()[0][0])

    def fetch_mutated_files(self):
        query = "SELECT DISTINCT file.name as name, COUNT(*) as number_of_mutants FROM file JOIN mutation ON file.id = mutation.file_id GROUP BY file.name ORDER BY file.name"
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def fetch_mutations(self):
        query = "SELECT * FROM mutation"
        self.cursor.execute(query)
        results = self.cursor.fetchall()
        return results

    def fetch_last_mutant_ID(self):
        query = "SELECT max(id) FROM mutant"
        self.cursor.execute(query)
        res = self.cursor.fetchall()
        if res is not []:
            res = res[0][0]
        else:
            res = 0
        return res

    def fetch_mutants(self):
        query = 'SELECT file.name as name, mutant.id as id, group_concat(mutation.lineNo , ",") as lineNo FROM file JOIN mutation ON file.id = mutation.file_id JOIN mutant ON mutant.mutation_id = mutation.id GROUP BY mutant.id ORDER BY file.name'
        self.cursor.execute(query)
        mutants = self.cursor.fetchall()
        return mutants

    def fetch_file_mutant_by_mutation_ID(self, mutation_id):
        query = f"SELECT file.name as name, mutant.id as id, group_concat(mutation.lineNo , ',') as lineNo FROM file JOIN mutation ON file.id = mutation.file_id JOIN mutant ON mutant.mutation_id = mutation.id WHERE mutation_id= '{mutation_id}' GROUP BY mutant.id ORDER BY file.name"
        self.cursor.execute(query)
        sqlLiteDB_File_Mutant = self.cursor.fetchall()
        return sqlLiteDB_File_Mutant

    def fetch_file_mutant(self, file_name):
        query = f"SELECT file.name as name, mutant.id as id, group_concat(mutation.lineNo , ',') as lineNo FROM file JOIN mutation ON file.id = mutation.file_id JOIN mutant ON mutant.mutation_id = mutation.id WHERE file.name = '{file_name}' GROUP BY mutant.id ORDER BY file.name"
        self.cursor.execute(query)
        sqlLiteDB_File_Mutant = self.cursor.fetchall()
        return sqlLiteDB_File_Mutant

    def fetch_file_mutant_with_id(self, file_name, mutant_id):
        query = f"SELECT file.name as name, mutant.id as id, group_concat(mutation.lineNo , ',') as lineNo FROM file JOIN mutation ON file.id = mutation.file_id JOIN mutant ON mutant.mutation_id = mutation.id WHERE file.name = '{file_name}' and mutant.id = '{mutant_id}'GROUP BY mutant.id ORDER BY file.name"
        self.cursor.execute(query)
        sqlLiteDB_File_Mutant = self.cursor.fetchall()
        return sqlLiteDB_File_Mutant

    def update_file_json(self, file_name, json):
        query = f"UPDATE file SET json = ? WHERE name = ?"
        self.cursor.execute(query, (json, file_name))
        self.conn.commit()

        if self.cursor.rowcount > 0:
            return True
        else:
            return False

    def update_data(self, table_name, set_values, condition=None):
        query = f"UPDATE {table_name} SET {set_values}"
        if condition:
            query += f" WHERE {condition}"
        try:
            self.cursor.execute(query)
            self.conn.commit()
        except Exception as e:
            print(e)
            return False
        if self.cursor.rowcount > 0:
            return True
        else:
            return False

    def delete_data(self, table_name, condition=None):
        query = f"DELETE FROM {table_name}"
        if condition:
            query += f" WHERE {condition}"
        try:
            self.cursor.execute(query)
            self.conn.commit()
        except:
            return False

        if self.cursor.rowcount > 0:
            return True
        else:
            return False

    def close_connection(self):
        self.conn.close()
