import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import os
import discord
import bot

class TestBot(unittest.IsolatedAsyncioTestCase):
    @patch("database.init_db")
    @patch("discord.app_commands.CommandTree.sync")
    async def test_setup_hook(self, mock_sync: AsyncMock, mock_init_db: MagicMock) -> None:
        test_bot = bot.VerificationBot()
        test_bot.add_view = MagicMock()
        
        await test_bot.setup_hook()
        
        mock_init_db.assert_called_once()
        self.assertEqual(test_bot.add_view.call_count, 3)
        mock_sync.assert_called_once()

    async def test_verify_dropdown_forbidden(self) -> None:
        dropdown = bot.VerifyDropdown()
        
        # Mock interaction and user send
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_user = AsyncMock()
        mock_response = MagicMock()
        mock_response.status = 403
        mock_user.send.side_effect = discord.Forbidden(mock_response, "Forbidden")
        mock_interaction.user = mock_user
        mock_interaction.response = AsyncMock()
        
        await dropdown.callback(mock_interaction)
        
        # Verify ephemeral failure message
        mock_interaction.response.send_message.assert_called_with(
            "❌ Please enable Direct Messages from server members to apply.",
            ephemeral=True
        )

    async def test_verify_dropdown_success(self) -> None:
        dropdown = bot.VerifyDropdown()
        
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_user = AsyncMock()
        mock_interaction.user = mock_user
        mock_interaction.response = AsyncMock()
        
        await dropdown.callback(mock_interaction)
        
        mock_user.send.assert_called_once()
        mock_interaction.response.send_message.assert_called_with(
            "✅ Verification instructions have been sent to your DMs!",
            ephemeral=True
        )

    async def test_setup_verify_no_permission(self) -> None:
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user = MagicMock()
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.administrator = False
        mock_interaction.response = AsyncMock()
        
        # Ensure os.environ is empty or has non-matching role
        with patch.dict(os.environ, {"SUPPORT_ROLE_ID": "9999"}):
            # Call the callback of the app command
            await bot.setup_verify.callback(mock_interaction)
            mock_interaction.response.send_message.assert_called_with(
                "❌ You do not have permission to run this command.",
                ephemeral=True
            )

if __name__ == "__main__":
    unittest.main()
