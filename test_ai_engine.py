import unittest
from unittest.mock import patch, MagicMock
import os
import io
from PIL import Image
import ai_engine

class TestAIEngine(unittest.TestCase):
    def test_load_env_keys(self) -> None:
        # Create a temporary .env file for testing
        test_env_path = "test_temp.env"
        with open(test_env_path, "w", encoding="utf-8") as f:
            f.write("GEMINI_API_KEYS=mock_key1,mock_key2,mock_key3\n")
            
        try:
            keys = ai_engine.load_env_keys(test_env_path)
            self.assertEqual(keys, ["mock_key1", "mock_key2", "mock_key3"])
        finally:
            if os.path.exists(test_env_path):
                os.remove(test_env_path)

    def test_key_rotation(self) -> None:
        # Patch the key pool in ai_engine
        import itertools
        ai_engine.api_keys = ["k1", "k2"]
        ai_engine.key_pool = itertools.cycle(["k1", "k2"])
        
        with patch("google.generativeai.configure") as mock_configure:
            key1 = ai_engine.rotate_api_key()
            self.assertEqual(key1, "k1")
            mock_configure.assert_called_with(api_key="k1")
            
            key2 = ai_engine.rotate_api_key()
            self.assertEqual(key2, "k2")
            mock_configure.assert_called_with(api_key="k2")
            
            key3 = ai_engine.rotate_api_key()
            self.assertEqual(key3, "k1")
            mock_configure.assert_called_with(api_key="k1")

    def test_load_reference_images_empty(self) -> None:
        # folder_path does not exist
        images = ai_engine.load_reference_images("nonexistent_folder_abc")
        self.assertEqual(images, [])

    @patch("google.generativeai.list_models")
    def test_get_active_flash_models(self, mock_list_models: MagicMock) -> None:
        # Mock returned models
        m1 = MagicMock()
        m1.name = "models/gemini-1.5-flash"
        m1.supported_generation_methods = ["generateContent"]
        
        m2 = MagicMock()
        m2.name = "models/gemini-1.5-pro"
        m2.supported_generation_methods = ["generateContent"]
        
        m3 = MagicMock()
        m3.name = "models/gemini-1.0-flash-latest"
        m3.supported_generation_methods = ["generateContent"]
        
        mock_list_models.return_value = [m1, m2, m3]
        
        models = ai_engine.get_active_flash_models()
        self.assertIn("models/gemini-1.5-flash", models)
        self.assertIn("models/gemini-1.0-flash-latest", models)
        self.assertNotIn("models/gemini-1.5-pro", models)
        self.assertEqual(models, ["models/gemini-1.5-flash", "models/gemini-1.0-flash-latest"])

    @patch("google.generativeai.GenerativeModel")
    @patch("ai_engine.get_active_flash_models")
    def test_verify_document_success(self, mock_get_models: MagicMock, mock_gen_model_class: MagicMock) -> None:
        mock_get_models.return_value = ["models/gemini-1.5-flash"]
        
        # Mock model response
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"verified": true, "reason": "Looks good", "extracted_id": "12345"}'
        mock_model_instance.generate_content.return_value = mock_response
        mock_gen_model_class.return_value = mock_model_instance
        
        # Create a dummy 1x1 black pixel image bytes
        img = Image.new("RGB", (1, 1), color="black")
        img_bytes_io = io.BytesIO()
        img.save(img_bytes_io, format="PNG")
        img_bytes = img_bytes_io.getvalue()
        
        result = ai_engine.verify_document(img_bytes)
        self.assertTrue(result["verified"])
        self.assertEqual(result["reason"], "Looks good")
        self.assertEqual(result["extracted_id"], "12345")

    @patch("google.generativeai.GenerativeModel")
    @patch("ai_engine.get_active_flash_models")
    @patch("ai_engine.rotate_api_key")
    def test_verify_document_retry_on_429(self, mock_rotate_key: MagicMock, mock_get_models: MagicMock, mock_gen_model_class: MagicMock) -> None:
        mock_get_models.return_value = ["models/gemini-1.5-flash"]
        
        mock_model_instance = MagicMock()
        
        import google.api_core.exceptions
        ex_429 = google.api_core.exceptions.ResourceExhausted("Rate limit exceeded")
        
        mock_response = MagicMock()
        mock_response.text = '{"verified": false, "reason": "Invalid ID", "extracted_id": ""}'
        
        mock_model_instance.generate_content.side_effect = [ex_429, mock_response]
        mock_gen_model_class.return_value = mock_model_instance
        
        img = Image.new("RGB", (1, 1), color="black")
        img_bytes_io = io.BytesIO()
        img.save(img_bytes_io, format="PNG")
        img_bytes = img_bytes_io.getvalue()
        
        result = ai_engine.verify_document(img_bytes)
        
        mock_rotate_key.assert_called_once()
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "Invalid ID")

if __name__ == "__main__":
    unittest.main()
