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

    async def test_fetch_member_safely_success(self) -> None:
        mock_guild = MagicMock(spec=discord.Guild)
        mock_member = MagicMock(spec=discord.Member)
        mock_guild.get_member.return_value = mock_member
        
        member = await bot.fetch_member_safely(mock_guild, 12345)
        self.assertEqual(member, mock_member)
        mock_guild.get_member.assert_called_with(12345)

    async def test_fetch_member_safely_not_found(self) -> None:
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = None
        # fetch_member raises NotFound
        mock_response = MagicMock()
        mock_response.status = 404
        mock_guild.fetch_member.side_effect = discord.NotFound(mock_response, "Not Found")
        
        member = await bot.fetch_member_safely(mock_guild, 12345)
        self.assertIsNone(member)

    async def test_in_flight_dm_locking(self) -> None:
        # If user is in processing_users, on_message should reject immediately
        bot.bot.processing_users.add(999) # Add user 999 to active set of global bot
        
        mock_message = AsyncMock(spec=discord.Message)
        mock_message.author = MagicMock()
        mock_message.author.bot = False
        mock_message.author.id = 999
        mock_message.guild = None
        mock_message.attachments = [MagicMock()]
        
        await bot.on_message(mock_message)
        
        # Check that it replied with the in-flight lock message
        mock_message.reply.assert_called_with("❌ Please wait until your current document analysis completes.")
        
        # Clean up
        bot.bot.processing_users.discard(999)

if __name__ == "__main__":
    unittest.main()
