import unittest
import os
import sqlite3
import database

class TestDatabase(unittest.TestCase):
    def setUp(self) -> None:
        # Patch the database name to a test database file
        database.DB_NAME = "test_verified_students.db"
        # Ensure a clean database for each test
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)
        database.init_db()

    def tearDown(self) -> None:
        # Clean up test database file after each test
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)

    def test_init_db(self) -> None:
        # init_db is called in setUp, verify that table exists
        with sqlite3.connect(database.DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "users")

    def test_add_verified_user_new(self) -> None:
        database.add_verified_user("discord123", "student456")
        state = database.get_user_state("discord123")
        self.assertIsNotNone(state)
        # strikes, is_locked
        self.assertEqual(state, (0, False))
        
        # Check student id usage
        self.assertTrue(database.is_student_id_used("student456"))
        self.assertFalse(database.is_student_id_used("nonexistent"))

    def test_add_verified_user_existing(self) -> None:
        database.add_verified_user("discord123", "student456")
        database.add_verified_user("discord123", "student789")
        
        # Verify the student ID was updated
        self.assertFalse(database.is_student_id_used("student456"))
        self.assertTrue(database.is_student_id_used("student789"))

    def test_add_strike(self) -> None:
        # Adding strike to new user
        database.add_strike("discord123")
        state = database.get_user_state("discord123")
        self.assertEqual(state, (1, False))

        # Adding second strike should lock the user
        database.add_strike("discord123")
        state = database.get_user_state("discord123")
        self.assertEqual(state, (2, True))

        # Adding third strike should keep it locked
        database.add_strike("discord123")
        state = database.get_user_state("discord123")
        self.assertEqual(state, (3, True))

    def test_unlock_user(self) -> None:
        database.add_strike("discord123")
        database.add_strike("discord123")
        state = database.get_user_state("discord123")
        self.assertEqual(state, (2, True))

        # Unlock user
        database.unlock_user("discord123")
        state = database.get_user_state("discord123")
        self.assertEqual(state, (0, False))

    def test_get_user_state_nonexistent(self) -> None:
        state = database.get_user_state("nonexistent")
        self.assertIsNone(state)

if __name__ == "__main__":
    unittest.main()
