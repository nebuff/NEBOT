import os
import discord
from configuration_module import get_guild_config

def is_admin_or_manager(member: discord.Member) -> bool:
    """Check if the member has Administrator or Manage Server permissions natively or is owner."""
    owner_id_str = os.getenv("OWNER_ID")
    if owner_id_str and owner_id_str.strip().isdigit():
        if hasattr(member, "id") and member.id == int(owner_id_str.strip()):
            return True
    if not hasattr(member, "guild_permissions"):
        return False
    return getattr(member.guild_permissions, "administrator", False) or getattr(member.guild_permissions, "manage_guild", False)

def is_user_or_role_whitelisted(member: discord.Member, cfg: dict) -> bool:
    """Check if the user ID or any of their roles are whitelisted."""
    allowed_users = cfg.get("music_allowed_users", [])
    if hasattr(member, "id") and member.id in allowed_users:
        return True
    allowed_roles = cfg.get("music_allowed_roles", [])
    if allowed_roles and hasattr(member, "roles"):
        member_role_ids = {role.id for role in member.roles if hasattr(role, "id")}
        if member_role_ids.intersection(allowed_roles):
            return True
    return False

def has_voice_channel_access(member: discord.Member, guild: discord.Guild) -> bool:
    """Check if the user has permission to join the target voice channel."""
    if guild.voice_client and guild.voice_client.channel:
        return guild.voice_client.channel.permissions_for(member).connect
    if member.voice and member.voice.channel:
        return member.voice.channel.permissions_for(member).connect
    
    if hasattr(guild, "voice_channels"):
        for channel in guild.voice_channels:
            if channel.permissions_for(member).connect:
                return True
    return False

async def check_command_permissions(interaction: discord.Interaction) -> bool:
    """
    Evaluates slash command permissions.
    Returns True if authorized, False otherwise (and sends ephemeral error embed).
    """
    guild = interaction.guild
    if not guild:
        return True
    member = interaction.user
    if not isinstance(member, discord.Member):
        return True
        
    if is_admin_or_manager(member):
        return True
        
    cfg = get_guild_config(guild.id)
    if not cfg.get("music_role_restriction_enabled", False):
        return True
        
    allowed_roles = cfg.get("music_allowed_roles", [])
    allowed_users = cfg.get("music_allowed_users", [])
    
    if not allowed_roles and not allowed_users:
        if has_voice_channel_access(member, guild):
            return True
        else:
            embed = discord.Embed(
                description="Access Denied: You do not possess the required roles or permissions to use music commands in this server.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
            
    if is_user_or_role_whitelisted(member, cfg):
        return True
        
    embed = discord.Embed(
        description="Access Denied: You do not possess the required roles or permissions to use music commands in this server.",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    return False

async def check_button_permissions(interaction: discord.Interaction, player) -> bool:
    """
    Evaluates button component permissions.
    Returns True if authorized, False otherwise (and sends ephemeral error message).
    """
    guild = interaction.guild
    if not guild:
        return True
    member = interaction.user
    if not isinstance(member, discord.Member):
        return True
        
    if is_admin_or_manager(member):
        return True
        
    cfg = get_guild_config(guild.id)
    if not cfg.get("music_component_restriction_enabled", False):
        return True
        
    if is_user_or_role_whitelisted(member, cfg):
        return True
        
    current_track = player.current if player else None
    added_by = getattr(current_track, "added_by", None)
    if added_by and hasattr(member, "id") and member.id == added_by:
        return True
        
    await interaction.response.send_message(
        "Access Denied: You cannot modify or control the current streaming playback.",
        ephemeral=True
    )
    return False
