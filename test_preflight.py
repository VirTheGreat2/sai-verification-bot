import unittest
from unittest.mock import patch, MagicMock
import os
import sqlite3
import sys
import preflight
import database

class TestPreflight(unittest.TestCase):
    def setUp(self) -> None:
        self.db_name = "test_preflight_verified_students.db"
        database.DB_NAME = self.db_name
        if os.path.exists(self.db_name):
            os.remove(self.db_name)

    def tearDown(self) -> None:
        if os.path.exists(self.db_name):
            os.remove(self.db_name)

    @patch.dict(os.environ, {
        "DISCORD_TOKEN": "mock_token",
        "GEMINI_API_KEY": "mock_gemini_key",
        "GUILD_ID": "123456789",
        "VERIFIED_ROLE_ID": "987654321"
    }, clear=True)
    def test_check_env_variables_success(self) -> None:
        self.assertTrue(preflight.check_env_variables())

    @patch("preflight.load_dotenv")
    @patch.dict(os.environ, {
        "DISCORD_TOKEN": "mock_token",
        "GUILD_ID": "123456789"
    }, clear=True)
    def test_check_env_variables_missing(self, mock_load: MagicMock) -> None:
        self.assertFalse(preflight.check_env_variables())

    @patch.dict(os.environ, {
        "DISCORD_TOKEN": "mock_token",
        "GEMINI_API_KEYS": "key1,key2",
        "GUILD_ID": "123456789",
        "VERIFIED_ROLE_ID": "987654321"
    }, clear=True)
    def test_check_env_variables_fallback_keys(self) -> None:
        self.assertTrue(preflight.check_env_variables())
        self.assertEqual(os.environ.get("GEMINI_API_KEY"), "key1")

    def test_check_database_success(self) -> None:
        self.assertTrue(preflight.check_database())

    @patch("database.init_db")
    def test_check_database_non_wal(self, mock_init_db: MagicMock) -> None:
        # Create non-WAL database
        with sqlite3.connect(self.db_name) as conn:
            conn.execute("PRAGMA journal_mode=DELETE;")
        self.assertFalse(preflight.check_database())

    @patch("google.genai.Client")
    @patch.dict(os.environ, {"GEMINI_API_KEY": "valid_key"})
    def test_check_gemini_api_success(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_model = MagicMock()
        mock_client.models.list.return_value = [mock_model]
        mock_client_cls.return_value = mock_client

        self.assertTrue(preflight.check_gemini_api())

    @patch("google.genai.Client")
    @patch.dict(os.environ, {"GEMINI_API_KEY": "invalid_key"})
    def test_check_gemini_api_failure(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Invalid API key")
        mock_client_cls.return_value = mock_client

        self.assertFalse(preflight.check_gemini_api())

    @patch("preflight.check_env_variables")
    @patch("preflight.check_database")
    @patch("preflight.check_gemini_api")
    def test_main_success(self, mock_gemini: MagicMock, mock_db: MagicMock, mock_env: MagicMock) -> None:
        mock_env.return_value = True
        mock_db.return_value = True
        mock_gemini.return_value = True

        with self.assertRaises(SystemExit) as cm:
            preflight.main()
        self.assertEqual(cm.exception.code, 0)

    @patch("preflight.check_env_variables")
    @patch("preflight.check_database")
    @patch("preflight.check_gemini_api")
    def test_main_failure(self, mock_gemini: MagicMock, mock_db: MagicMock, mock_env: MagicMock) -> None:
        mock_env.return_value = True
        mock_db.return_value = False
        mock_gemini.return_value = True

        with self.assertRaises(SystemExit) as cm:
            preflight.main()
        self.assertEqual(cm.exception.code, 1)

if __name__ == "__main__":
    unittest.main()
