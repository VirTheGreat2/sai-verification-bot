import os
import io
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

import database
import ai_engine

# Load .env variables from potential locations
load_dotenv(".env")
load_dotenv("reference_images/.env")

class VerificationBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        # Initialize database
        database.init_db()
        
        # Register persistent views
        self.add_view(VerifyDropdownView())
        self.add_view(DMStartCancelView())
        self.add_view(StaffButtonsView())
        
        # Sync slash commands
        await self.tree.sync()
        print("Bot persistent views registered and slash commands synced.")

# ==================== PERSISTENT VIEWS ====================

class VerifyDropdown(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label="Apply for Verification",
                description="Start the student verification process.",
                emoji="🎓",
                value="apply_verification"
            )
        ]
        super().__init__(
            placeholder="Select to verify your student status...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="persistent:verify_dropdown_select"
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        user = interaction.user
        try:
            view = DMStartCancelView()
            embed = discord.Embed(
                title="Student Verification",
                description=(
                    "Welcome to student verification! Please click **Start Verification** to begin. "
                    "You will then be prompted to upload an image of your **Student Assessment Invoice**."
                ),
                color=discord.Color.blue()
            )
            await user.send(embed=embed, view=view)
            await interaction.response.send_message(
                "✅ Verification instructions have been sent to your DMs!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Please enable Direct Messages from server members to apply.",
                ephemeral=True
            )

class VerifyDropdownView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(VerifyDropdown())

class DMStartCancelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Start Verification",
        style=discord.ButtonStyle.success,
        custom_id="persistent:dm_start_btn"
    )
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        embed = discord.Embed(
            title="Upload Document",
            description=(
                "Please upload your **Student Assessment Invoice** (as a JPG, PNG, or WEBP image under 8MB) "
                "directly in this DM channel."
            ),
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.danger,
        custom_id="persistent:dm_cancel_btn"
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("❌ Verification cancelled. You can restart anytime using the dropdown.")

class StaffButtonsView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Accept",
        style=discord.ButtonStyle.success,
        custom_id="persistent:staff_accept_btn"
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        member = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Error: Must be used in a server.", ephemeral=True)
            return
            
        support_role_id = int(os.environ.get("SUPPORT_ROLE_ID", 0))
        if not any(role.id == support_role_id for role in member.roles):
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return
            
        if not interaction.message or not interaction.message.embeds:
            await interaction.response.send_message("❌ Error: Embed message not found.", ephemeral=True)
            return
            
        embed = interaction.message.embeds[0]
        user_id = None
        student_id = None
        for field in embed.fields:
            if field.name == "User ID":
                user_id = int(field.value)
            elif field.name == "Student ID":
                student_id = field.value
                
        if not user_id:
            await interaction.response.send_message("❌ Error: Could not parse User ID.", ephemeral=True)
            return
            
        # Action: Unlock user & verify them
        database.unlock_user(str(user_id))
        if student_id and student_id != "N/A" and student_id.strip():
            database.add_verified_user(str(user_id), student_id)
        else:
            database.add_verified_user(str(user_id), f"STAFF_VERIFIED_{user_id}")
            
        # Assign role
        target_member = guild.get_member(user_id)
        if not target_member:
            try:
                target_member = await guild.fetch_member(user_id)
            except discord.NotFound:
                target_member = None
                
        verified_role_id = int(os.environ.get("VERIFIED_ROLE_ID", 0))
        role_assigned = False
        if target_member:
            role = guild.get_role(verified_role_id)
            if role:
                try:
                    await target_member.add_roles(role)
                    role_assigned = True
                except Exception as e:
                    print(f"Failed to assign role to {user_id}: {e}")
                    
        # Notify user
        if target_member:
            try:
                success_embed = discord.Embed(
                    title="Verification Approved",
                    description="🎉 Congratulations! Your student verification has been approved by staff.",
                    color=discord.Color.green()
                )
                await target_member.send(embed=success_embed)
            except Exception as e:
                print(f"Failed to DM approved user {user_id}: {e}")
                
        # Disable buttons
        for child in self.children:
            child.disabled = True
            
        new_embed = discord.Embed.from_dict(embed.to_dict())
        new_embed.color = discord.Color.green()
        new_embed.add_field(name="Status", value=f"✅ Approved by {member.mention}", inline=False)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        custom_id="persistent:staff_deny_btn"
    )
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        member = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Error: Must be used in a server.", ephemeral=True)
            return
            
        support_role_id = int(os.environ.get("SUPPORT_ROLE_ID", 0))
        if not any(role.id == support_role_id for role in member.roles):
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return
            
        if not interaction.message or not interaction.message.embeds:
            await interaction.response.send_message("❌ Error: Embed message not found.", ephemeral=True)
            return
            
        embed = interaction.message.embeds[0]
        user_id = None
        for field in embed.fields:
            if field.name == "User ID":
                user_id = int(field.value)
                
        if not user_id:
            await interaction.response.send_message("❌ Error: Could not parse User ID.", ephemeral=True)
            return
            
        # Action: Unlock user so they can try again, but do not verify
        database.unlock_user(str(user_id))
        
        # Notify user
        target_member = guild.get_member(user_id)
        if not target_member:
            try:
                target_member = await guild.fetch_member(user_id)
            except discord.NotFound:
                target_member = None
                
        if target_member:
            try:
                deny_embed = discord.Embed(
                    title="Verification Denied",
                    description="❌ Your student verification request was denied by staff. You may try re-submitting your document.",
                    color=discord.Color.red()
                )
                await target_member.send(embed=deny_embed)
            except Exception as e:
                print(f"Failed to DM denied user {user_id}: {e}")
                
        # Disable buttons
        for child in self.children:
            child.disabled = True
            
        new_embed = discord.Embed.from_dict(embed.to_dict())
        new_embed.color = discord.Color.red()
        new_embed.add_field(name="Status", value=f"❌ Denied by {member.mention}", inline=False)
        await interaction.response.edit_message(embed=new_embed, view=self)


bot = VerificationBot()

# ==================== BOT SLASH COMMANDS ====================

@bot.tree.command(name="setup-verify", description="Sets up the student verification channel with the dropdown menu.")
async def setup_verify(interaction: discord.Interaction) -> None:
    # Restrict to Support Role or Admin
    support_role_id = int(os.environ.get("SUPPORT_ROLE_ID", 0))
    if not any(role.id == support_role_id for role in interaction.user.roles) and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You do not have permission to run this command.", ephemeral=True)
        return

    verify_channel_id = int(os.environ.get("VERIFY_CHANNEL_ID", 0))
    channel = bot.get_channel(verify_channel_id)
    if not channel:
        await interaction.response.send_message(
            f"❌ Verification channel with ID {verify_channel_id} not found in cache. Make sure the bot has access.",
            ephemeral=True
        )
        return
        
    embed = discord.Embed(
        title="Student Verification Required",
        description="To access the channels on this server, please verify your student status by choosing an option below.",
        color=discord.Color.blue()
    )
    view = VerifyDropdownView()
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Verification dropdown posted successfully!", ephemeral=True)

# ==================== BOT EVENTS ====================

@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    # Check if DM channel
    if message.guild is not None:
        await bot.process_commands(message)
        return

    # If it's a DM, make sure there is an attachment
    if not message.attachments:
        return

    user_id_str = str(message.author.id)
    user_state = database.get_user_state(user_id_str)
    
    # 3. Image Gatekeeper: Check if is_locked is True
    if user_state is not None:
        strikes, is_locked = user_state
        if is_locked:
            return

    # Process first attachment
    attachment = message.attachments[0]
    
    # Check mime type or filename, and size < 8MB
    is_valid_type = False
    if attachment.content_type:
        is_valid_type = attachment.content_type in ["image/jpeg", "image/png", "image/webp"]
    else:
        ext = os.path.splitext(attachment.filename)[1].lower()
        is_valid_type = ext in [".jpg", ".jpeg", ".png", ".webp"]

    if not is_valid_type or attachment.size >= 8000000:
        await message.reply("❌ Invalid file. Please upload a JPG or PNG under 8MB.")
        return

    # 4. Processing & API Call
    status_msg = await message.reply("⏳ Analyzing...")
    
    try:
        image_bytes = await attachment.read()
        result = ai_engine.verify_document(image_bytes)
    except Exception as e:
        print(f"Error during AI verification: {e}")
        await status_msg.edit(content="❌ An error occurred during verification. Please try again later.")
        return

    verified = result.get("verified", False)
    reason = result.get("reason", "Verification unsuccessful.")
    extracted_id = result.get("extracted_id", "").strip()

    # 5. PASS Logic
    if verified:
        if database.is_student_id_used(extracted_id):
            # Treat as duplicate -> Fail
            verified = False
            reason = f"Duplicate verification: Student ID '{extracted_id}' is already registered to another user."
        else:
            database.add_verified_user(user_id_str, extracted_id)
            
            guild_id = int(os.environ.get("GUILD_ID", 0))
            guild = bot.get_guild(guild_id)
            role_assigned = False
            if guild:
                role = guild.get_role(int(os.environ.get("VERIFIED_ROLE_ID", 0)))
                member = guild.get_member(message.author.id)
                if not member:
                    try:
                        member = await guild.fetch_member(message.author.id)
                    except discord.NotFound:
                        member = None
                if member and role:
                    try:
                        await member.add_roles(role)
                        role_assigned = True
                    except Exception as e:
                        print(f"Failed to assign role to {user_id_str} on success: {e}")

            success_embed = discord.Embed(
                title="Verification Successful",
                description="🎉 Your student verification has been approved automatically!",
                color=discord.Color.green()
            )
            success_embed.add_field(name="Student ID", value=extracted_id, inline=True)
            if role_assigned:
                success_embed.add_field(name="Role Assigned", value="Verified Student", inline=True)
            else:
                success_embed.add_field(name="Role Status", value="Role pending assignment.", inline=True)
                
            await status_msg.edit(content="✅ Analysis complete!")
            await message.reply(embed=success_embed)
            return

    # 6 & 7. FAIL Logic
    database.add_strike(user_id_str)
    updated_state = database.get_user_state(user_id_str)
    strikes = 1
    is_locked = False
    if updated_state:
        strikes, is_locked = updated_state

    if is_locked or strikes >= 2:
        # Strike 2 (Lock user & forward to staff)
        await status_msg.edit(content="❌ Verification failed.")
        
        lock_embed = discord.Embed(
            title="Verification Locked",
            description=(
                "❌ You have accumulated 2 strikes. Your verification has been locked "
                "and forwarded to server staff for manual review. Please wait for assistance."
            ),
            color=discord.Color.red()
        )
        lock_embed.add_field(name="Failure Reason", value=reason, inline=False)
        await message.reply(embed=lock_embed)
        
        # Send to staff pending channel
        pending_channel_id = int(os.environ.get("PENDING_CHANNEL_ID", 0))
        pending_channel = bot.get_channel(pending_channel_id)
        if pending_channel:
            try:
                img_data = await attachment.read()
                file_to_forward = discord.File(io.BytesIO(img_data), filename=attachment.filename)
                
                staff_embed = discord.Embed(
                    title="Manual Verification Required",
                    description="User has accumulated 2 strikes and is locked. Please review the attached document.",
                    color=discord.Color.orange()
                )
                staff_embed.add_field(name="User Mention", value=message.author.mention, inline=True)
                staff_embed.add_field(name="User ID", value=user_id_str, inline=True)
                staff_embed.add_field(name="Student ID", value=extracted_id if extracted_id else "N/A", inline=True)
                staff_embed.add_field(name="Failure Reason", value=reason, inline=False)
                
                view = StaffButtonsView()
                await pending_channel.send(embed=staff_embed, file=file_to_forward, view=view)
            except Exception as e:
                print(f"Failed to forward verification image to staff: {e}")
                
                staff_embed = discord.Embed(
                    title="Manual Verification Required",
                    description="User has accumulated 2 strikes and is locked. (Image download failed)",
                    color=discord.Color.orange()
                )
                staff_embed.add_field(name="User Mention", value=message.author.mention, inline=True)
                staff_embed.add_field(name="User ID", value=user_id_str, inline=True)
                staff_embed.add_field(name="Student ID", value=extracted_id if extracted_id else "N/A", inline=True)
                staff_embed.add_field(name="Failure Reason", value=reason, inline=False)
                
                view = StaffButtonsView()
                await pending_channel.send(embed=staff_embed, view=view)
    else:
        # Strike 1: Warning
        await status_msg.edit(content="❌ Verification failed.")
        
        warn_embed = discord.Embed(
            title="Verification Warning (Strike 1/2)",
            description=(
                "⚠️ Your document verification failed. You have received 1 strike. "
                "You have one remaining attempt before your account is locked and sent to manual review."
            ),
            color=discord.Color.yellow()
        )
        warn_embed.add_field(name="Failure Reason", value=reason, inline=False)
        await message.reply(embed=warn_embed)


if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN environment variable not set.")
