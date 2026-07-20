import discord
from discord import app_commands, ui
from configuration_module import get_guild_config, save_config, is_admin, is_mod, SESSION_TIMEOUT_SECONDS, DEFAULT_PREFIX, DEFAULT_CMD, FG_CYAN, FG_GREEN, FG_RED, FG_BRIGHT_BLACK, BOLD, RESET
import configuration_module
from utility_module import ansi_block

class SendMessageModal(ui.Modal, title='Send Message'):
    content = ui.TextInput(label='Message content', style=discord.TextStyle.paragraph, placeholder='Type your message here...', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(self.content.value)
        await interaction.response.send_message("Message sent", ephemeral=True)

class ConfigValueModal(ui.Modal):
    def __init__(self, guild_id, key, view=None):
        self.guild_id = guild_id
        self.key = key
        self.view = view
        super().__init__(title=f"Update {key}")
        self.input = ui.TextInput(label="New Value", placeholder="Enter value (or 'none' to clear)", required=True)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        val = self.input.value
        if val.lower() == "none":
            cfg[self.key] = None
        elif self.key in ("admin_role_id", "mod_role_id", "channel_id", "shared_channel_id", "global_log_channel_id"):
            try:
                cfg[self.key] = int(val.strip("<@&#>! "))
            except ValueError:
                return await interaction.response.send_message("Invalid ID format", ephemeral=True)
        else:
            cfg[self.key] = val
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated setting `{self.key}` to `{val}`")
        if self.view:
            await interaction.response.defer(ephemeral=True)
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Updated {self.key}", ephemeral=True)

class NeOSAdminChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Admin Channel...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text], row=2)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["channel_id"] = channel.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Admin Channel to {channel.mention}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Admin channel set to <#{channel.id}>", ephemeral=True)

class NeOSSharedChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Shared Channel...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text], row=3)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["shared_channel_id"] = channel.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Shared Channel to {channel.mention}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Shared channel set to <#{channel.id}>", ephemeral=True)

class NeOSConfigSelect(ui.Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label="Prefix", value="prefix"),
            discord.SelectOption(label="Trigger Word", value="cmd"),
        ]
        super().__init__(placeholder="Choose a shell setting...", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ConfigValueModal(self.guild_id, self.values[0], view=self.view))

class NeOSConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(NeOSConfigSelect(guild_id))
        self.add_item(NeOSAdminChannelSelect(guild_id))
        self.add_item(NeOSSharedChannelSelect(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        embed = discord.Embed(
            title="Nebot Module: Ne-OS Shell",
            description="Management for the virtual shell environment",
            color=discord.Color.blue()
        )
        ne_os_en = cfg.get("ne_os_enabled", False)
        priv_en = cfg.get("private_sessions_enabled", False)
        sh_en = cfg.get("shared_enabled", False)
        prefix = cfg.get("prefix", DEFAULT_PREFIX)
        cmd = cfg.get("cmd", DEFAULT_CMD)
        
        ch_id = cfg.get("channel_id")
        ch_str = f"<#{ch_id}>" if ch_id else "Any Channel"
        
        sh_ch_id = cfg.get("shared_channel_id")
        sh_chan_str = f"<#{sh_ch_id}>" if sh_ch_id else "None"
        
        embed.add_field(name="Status", value="[ENABLED]" if ne_os_en else "[DISABLED]", inline=True)
        embed.add_field(name="Private Sessions", value="[ENABLED]" if priv_en else "[DISABLED]", inline=True)
        embed.add_field(name="Shared Mode", value="[ENABLED]" if sh_en else "[DISABLED]", inline=True)
        embed.add_field(name="Trigger", value=f"{prefix}{cmd}", inline=True)
        embed.add_field(name="Admin Channel", value=ch_str, inline=True)
        embed.add_field(name="Shared Channel", value=sh_chan_str, inline=True)
        return embed

    @ui.button(label="Toggle Ne-OS Module", style=discord.ButtonStyle.primary, row=0)
    async def toggle_neos(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["ne_os_enabled"] = not cfg.get("ne_os_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Ne-OS Shell module state to `{'enabled' if cfg['ne_os_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Toggle Private SESS", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_private(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["private_sessions_enabled"] = not cfg.get("private_sessions_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled private sessions to `{'enabled' if cfg['private_sessions_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Toggle Shared Mode", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_shared(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["shared_enabled"] = not cfg.get("shared_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled prefixless shared session mode to `{'enabled' if cfg['shared_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Clear Admin Channel", style=discord.ButtonStyle.secondary, row=0)
    async def clear_admin_channel(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["channel_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Admin Channel restriction")
        await self.refresh(interaction)

    @ui.button(label="Clear Shared Channel", style=discord.ButtonStyle.secondary, row=0)
    async def clear_shared_channel(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["shared_channel_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Shared Channel configuration")
        await self.refresh(interaction)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=4)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class AdminRoleSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Admin Role...", min_values=1, max_values=1, row=1)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["admin_role_id"] = role.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Admin Role to @{role.name}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Admin role set to @{role.name}", ephemeral=True)

class ModeratorRoleSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Moderator Role...", min_values=1, max_values=1, row=2)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["mod_role_id"] = role.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Moderator Role to @{role.name}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Moderator role set to @{role.name}", ephemeral=True)

class GlobalLogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Global Log Channel...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text], row=3)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["global_log_channel_id"] = channel.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Global Log Channel to {channel.mention}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Global log channel set to <#{channel.id}>", ephemeral=True)

class ToolsView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Nebot Administrative Tools",
            description="Access and run on-demand server utility tools.",
            color=discord.Color.dark_teal()
        )
        embed.add_field(
            name="Auto Channel Namer",
            value="Configure channel prefix, suffix, and font styles, and run bulk renaming on demand.",
            inline=False
        )
        embed.add_field(
            name="Bulk Role Manager",
            value="Perform bulk role assignments or removals on server members using custom filters.",
            inline=False
        )
        return embed

    @ui.button(label="Auto Channel Namer", style=discord.ButtonStyle.primary, row=0)
    async def config_autochannelnamer(self, interaction: discord.Interaction, button: ui.Button):
        from auto_channel_namer_module import AutoChannelNamerDashboard
        dashboard = AutoChannelNamerDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Bulk Role Manager", style=discord.ButtonStyle.primary, row=0)
    async def config_bulkrole(self, interaction: discord.Interaction, button: ui.Button):
        from bulk_role_module import BulkRoleDashboard
        dashboard = BulkRoleDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

class GlobalConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(AdminRoleSelect(guild_id))
        self.add_item(ModeratorRoleSelect(guild_id))
        self.add_item(GlobalLogChannelSelect(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        role_id = cfg.get("admin_role_id")
        mod_role_id = cfg.get("mod_role_id")
        global_log = cfg.get("global_log_channel_id")
        admin_role_str = f"<@&{role_id}>" if role_id else "None"
        mod_role_str = f"<@&{mod_role_id}>" if mod_role_id else "None"
        global_log_str = f"<#{global_log}>" if global_log else "None"
        embed = discord.Embed(title="Nebot Global System Settings", color=discord.Color.dark_grey())
        embed.description = "Bot-wide plugin management and permissions"
        embed.add_field(name="Admin Role", value=admin_role_str, inline=True)
        embed.add_field(name="Moderator Role", value=mod_role_str, inline=True)
        embed.add_field(name="Global Log Channel", value=global_log_str, inline=True)
        return embed

    @ui.button(label="Clear Admin Role", style=discord.ButtonStyle.secondary, row=0)
    async def clear_admin_role(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["admin_role_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Admin Role configuration")
        await self.refresh(interaction)

    @ui.button(label="Clear Moderator Role", style=discord.ButtonStyle.secondary, row=0)
    async def clear_mod_role(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["mod_role_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Moderator Role configuration")
        await self.refresh(interaction)

    @ui.button(label="Clear Global Log Channel", style=discord.ButtonStyle.secondary, row=0)
    async def clear_global_log(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["global_log_channel_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Global Log Channel configuration")
        await self.refresh(interaction)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=4)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class QuickUserWarningSelect(discord.ui.UserSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Discord Member to Warn...", min_values=1, max_values=1, row=1)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        from warning_tracker_module import make_discord_target, get_user_warnings, WizardConfirmView
        cfg = get_guild_config(self.guild_id)
        targets = [make_discord_target(member)]
        past_warnings = await get_user_warnings(self.guild_id, targets)
        
        target_str = f"Discord: {member.display_name} (ID: {member.id})"
        if past_warnings:
            total_pts = sum(r.get("points", 0) for r in past_warnings)
            embed = discord.Embed(
                title="Is this the user? Active historical warnings found.",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Warning Targets", value=target_str, inline=False)
            embed.add_field(name="Warning Count", value=f"{len(past_warnings)} warnings")
            embed.add_field(name="Total Historical Points", value=f"{total_pts} points")
            recent = []
            for r in past_warnings[:3]:
                ts = r.get("timestamp", "").split("T")[0]
                recent.append(f"`{ts}` [{r.get('severity')}]: {r.get('details')}")
            embed.add_field(name="Recent Violations", value="\n".join(recent) if recent else "None", inline=False)
        else:
            embed = discord.Embed(
                title="Is this the user? No active historical warnings found.",
                description=f"Proceed to log a new infraction for targets:\n**{target_str}**?",
                color=discord.Color.light_grey()
            )
        
        view = WizardConfirmView(targets, self.guild_id, interaction.user.id, cfg)
        await interaction.response.edit_message(content=None, embed=embed, view=view)

class QuickUserViewSelect(discord.ui.UserSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Discord Member to View Warnings...", min_values=1, max_values=1, row=2)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        from warning_tracker_module import make_discord_target, get_user_warnings
        targets = [make_discord_target(member)]
        past_warnings = await get_user_warnings(self.guild_id, targets)
        
        if not past_warnings:
            await interaction.response.send_message(f"No warnings found for {member.mention}.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Warning History: {member.display_name}", color=discord.Color.blue())
        for r in past_warnings:
            ts = r.get("timestamp", "").split("T")[0]
            accounts = ", ".join(f"{acc['platform']}:{acc['display_name']}" for acc in r.get("linked_accounts", []))
            val = (
                f"**Date**: {ts}\n"
                f"**Points**: {r.get('points')} ({r.get('severity')})\n"
                f"**Accounts**: {accounts}\n"
                f"**Details**: {r.get('details')}\n"
                f"**Action**: {r.get('action_taken')}"
            )
            embed.add_field(name=f"Warning ID: {r.get('id')[:8]}...", value=val, inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

class QuickTwitchWarningModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Quick Twitch Warning Creator")
        self.twitch_input = ui.TextInput(label="Twitch Username", placeholder="e.g. twitch_user", required=True)
        self.add_item(self.twitch_input)

    async def on_submit(self, interaction: discord.Interaction):
        target_str = self.twitch_input.value.strip()
        cfg = get_guild_config(self.guild_id)
        from warning_tracker_module import make_twitch_target, get_user_warnings, WizardConfirmView
        
        targets = [make_twitch_target(target_str)]
        past_warnings = await get_user_warnings(self.guild_id, targets)
        target_names = f"Twitch: {target_str}"
        
        if past_warnings:
            total_pts = sum(r.get("points", 0) for r in past_warnings)
            embed = discord.Embed(
                title="Is this the user? Active historical warnings found.",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Warning Targets", value=target_names, inline=False)
            embed.add_field(name="Warning Count", value=f"{len(past_warnings)} warnings")
            embed.add_field(name="Total Historical Points", value=f"{total_pts} points")
            recent = []
            for r in past_warnings[:3]:
                ts = r.get("timestamp", "").split("T")[0]
                recent.append(f"`{ts}` [{r.get('severity')}]: {r.get('details')}")
            embed.add_field(name="Recent Violations", value="\n".join(recent) if recent else "None", inline=False)
        else:
            embed = discord.Embed(
                title="Is this the user? No active historical warnings found.",
                description=f"Proceed to log a new infraction for targets:\n**{target_names}**?",
                color=discord.Color.light_grey()
            )
        
        view = WizardConfirmView(targets, self.guild_id, interaction.user.id, cfg)
        await interaction.response.edit_message(content=None, embed=embed, view=view)

class QuickTwitchViewWarningsModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Quick Twitch View Warnings")
        self.twitch_input = ui.TextInput(label="Twitch Username", placeholder="e.g. twitch_user", required=True)
        self.add_item(self.twitch_input)

    async def on_submit(self, interaction: discord.Interaction):
        target_str = self.twitch_input.value.strip()
        from warning_tracker_module import make_twitch_target, get_user_warnings
        
        targets = [make_twitch_target(target_str)]
        past_warnings = await get_user_warnings(self.guild_id, targets)
        if not past_warnings:
            return await interaction.response.send_message(f"No warnings found for Twitch user '{target_str}'.", ephemeral=True)

        embed = discord.Embed(title=f"Warning History: {target_str}", color=discord.Color.blue())
        for r in past_warnings:
            ts = r.get("timestamp", "").split("T")[0]
            accounts = ", ".join(f"{acc['platform']}:{acc['display_name']}" for acc in r.get("linked_accounts", []))
            val = (
                f"**Date**: {ts}\n"
                f"**Points**: {r.get('points')} ({r.get('severity')})\n"
                f"**Accounts**: {accounts}\n"
                f"**Details**: {r.get('details')}\n"
                f"**Action**: {r.get('action_taken')}"
            )
            embed.add_field(name=f"Warning ID: {r.get('id')[:8]}...", value=val, inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

class QuickActionsView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(QuickUserWarningSelect(guild_id))
        self.add_item(QuickUserViewSelect(guild_id))

    @ui.button(label="Send Message", style=discord.ButtonStyle.primary, row=0)
    async def send_msg(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SendMessageModal())

    @ui.button(label="Jump to Shell", style=discord.ButtonStyle.success, row=0)
    async def jump(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        targets = []
        ch = cfg.get("channel_id")
        sh = cfg.get("shared_channel_id")
        if ch: targets.append(f"Admin restricted: <#{ch}>")
        if sh: targets.append(f"Shared session: <#{sh}>")
        text = "Ne-OS Entry Points:\n" + ("\n".join(targets) if targets else "Available globally")
        await interaction.response.send_message(text, ephemeral=True)

    @ui.button(label="Warn Twitch User", style=discord.ButtonStyle.primary, row=0)
    async def warn_twitch(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(QuickTwitchWarningModal(self.guild_id))

    @ui.button(label="View Twitch Warnings", style=discord.ButtonStyle.secondary, row=0)
    async def view_twitch_warnings(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(QuickTwitchViewWarningsModal(self.guild_id))

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=3)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

class BattleConfigModal(ui.Modal):
    def __init__(self, guild_id: int, key: str, title_str: str):
        self.guild_id = guild_id
        self.key = key
        super().__init__(title=title_str[:45])
        self.input = ui.TextInput(label="New Value", placeholder="Enter value", required=True)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        val = self.input.value.strip()
        
        if self.key in ("battle_default_hp", "battle_timeout"):
            try:
                cfg[self.key] = int(val)
                if cfg[self.key] <= 0:
                    raise ValueError()
            except ValueError:
                return await interaction.response.send_message("Must be a positive integer.", ephemeral=True)
        elif self.key == "battle_damage_range":
            if "-" in val:
                parts = val.split("-")
                if len(parts) != 2:
                    return await interaction.response.send_message("Invalid format. Use A-B (e.g. 10-100).", ephemeral=True)
                try:
                    a = int(parts[0])
                    b = int(parts[1])
                    if a < 0 or b < 0 or a > b:
                        raise ValueError()
                except ValueError:
                    return await interaction.response.send_message("Invalid range. Must be positive integers and A <= B.", ephemeral=True)
            else:
                try:
                    a = int(val)
                    if a < 0:
                        raise ValueError()
                except ValueError:
                    return await interaction.response.send_message("Must be a positive integer or range A-B.", ephemeral=True)
            cfg[self.key] = val
            
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Battle game setting `{self.key}` to `{val}`")
        await interaction.response.defer(ephemeral=True)
        dashboard = BattleConfigDashboard(self.guild_id)
        await dashboard.refresh(interaction)

class BattleConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        battle_en = cfg.get("battle_enabled", False)
        hp = cfg.get("battle_default_hp", 500)
        dmg = cfg.get("battle_damage_range", "0-100")
        timeout = cfg.get("battle_timeout", 180)
        
        embed = discord.Embed(title="Nebot Module Configuration: Battle Game", color=discord.Color.red())
        embed.add_field(name="Status", value="[ENABLED]" if battle_en else "[DISABLED]")
        embed.add_field(name="Default HP", value=f"{hp}")
        embed.add_field(name="Damage Range", value=f"{dmg}")
        embed.add_field(name="Timeout", value=f"{timeout}s")
        return embed

    @ui.button(label="Toggle Battle System", style=discord.ButtonStyle.primary)
    async def toggle_battle(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["battle_enabled"] = not cfg.get("battle_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Battle Game module state to `{'enabled' if cfg['battle_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Set Default HP", style=discord.ButtonStyle.secondary)
    async def set_hp(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BattleConfigModal(self.guild_id, "battle_default_hp", "Default HP (e.g. 500)"))

    @ui.button(label="Set Damage Range", style=discord.ButtonStyle.secondary)
    async def set_dmg(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BattleConfigModal(self.guild_id, "battle_damage_range", "Damage Range (e.g. 0-100 or 10)"))

    @ui.button(label="Set Timeout", style=discord.ButtonStyle.secondary)
    async def set_timeout(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BattleConfigModal(self.guild_id, "battle_timeout", "Timeout in Seconds (e.g. 180)"))

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class MinesweeperConfigModal(ui.Modal):
    def __init__(self, guild_id: int, key: str, title_str: str):
        self.guild_id = guild_id
        self.key = key
        super().__init__(title=title_str[:45])
        self.input = ui.TextInput(label="New Value", placeholder="Enter value", required=True)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        val = self.input.value.strip()
        
        if self.key == "minesweeper_default_mines":
            try:
                mines = int(val)
                if not (1 <= mines <= 8):
                    raise ValueError()
                cfg[self.key] = mines
            except ValueError:
                return await interaction.response.send_message("Must be an integer between 1 and 8.", ephemeral=True)
            
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Minesweeper game setting `{self.key}` to `{val}`")
        await interaction.response.defer(ephemeral=True)
        dashboard = MinesweeperConfigDashboard(self.guild_id)
        await dashboard.refresh(interaction)

class MinesweeperConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        minesweeper_en = cfg.get("minesweeper_enabled", False)
        minesweeper_mines = cfg.get("minesweeper_default_mines", 4)
        
        embed = discord.Embed(title="Nebot Module Configuration: Minesweeper Game", color=discord.Color.blue())
        embed.add_field(name="Status", value="[ENABLED]" if minesweeper_en else "[DISABLED]")
        embed.add_field(name="Default Mines", value=f"{minesweeper_mines}")
        return embed

    @ui.button(label="Toggle Minesweeper", style=discord.ButtonStyle.primary)
    async def toggle_minesweeper(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["minesweeper_enabled"] = not cfg.get("minesweeper_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Minesweeper Game module state to `{'enabled' if cfg['minesweeper_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Set Default Mines", style=discord.ButtonStyle.secondary)
    async def set_mines(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(MinesweeperConfigModal(self.guild_id, "minesweeper_default_mines", "Default Mines (1-8)"))

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class MusicConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        music_en = cfg.get("music_enabled", False)
        
        embed = discord.Embed(title="Nebot Module Configuration: Music", color=discord.Color.teal())
        embed.add_field(name="Status", value="[ENABLED]" if music_en else "[DISABLED]")
        return embed

    @ui.button(label="Toggle Music Module", style=discord.ButtonStyle.primary)
    async def toggle_music(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["music_enabled"] = not cfg.get("music_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Music module state to `{'enabled' if cfg['music_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Permissions Settings", style=discord.ButtonStyle.secondary)
    async def permissions_settings(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = MusicPermissionsConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class WhitelistRolesModal(ui.Modal):
    def __init__(self, guild_id: int, view):
        self.guild_id = guild_id
        self.view = view
        super().__init__(title="Whitelist Roles")
        cfg = get_guild_config(guild_id)
        roles = cfg.get("music_allowed_roles", [])
        self.input = ui.TextInput(
            label="Allowed Roles (IDs/Mentions comma-sep)",
            default=", ".join(str(r) for r in roles),
            placeholder="e.g. 123456789, <@&987654321>",
            required=True
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        val = self.input.value.strip()
        if not val or val.lower() == "none":
            cfg["music_allowed_roles"] = []
            save_config()
            from configuration_module import log_setting_change_task
            log_setting_change_task(interaction.guild, interaction.user, "Cleared Whitelisted Music Roles")
            await interaction.response.defer()
            return await self.view.refresh(interaction)
            
        role_ids = []
        for r in val.split(","):
            cleaned = r.strip("<@&#>! ")
            if cleaned:
                try:
                    role_ids.append(int(cleaned))
                except ValueError:
                    role = discord.utils.get(interaction.guild.roles, name=r.strip())
                    if role:
                        role_ids.append(role.id)
                    else:
                        return await interaction.response.send_message(f"Invalid Role ID or name: {r.strip()}", ephemeral=True)
        cfg["music_allowed_roles"] = role_ids
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Whitelisted Music Roles to: {role_ids}")
        await interaction.response.defer()
        await self.view.refresh(interaction)

class WhitelistUsersModal(ui.Modal):
    def __init__(self, guild_id: int, view):
        self.guild_id = guild_id
        self.view = view
        super().__init__(title="Whitelist Users")
        cfg = get_guild_config(guild_id)
        users = cfg.get("music_allowed_users", [])
        self.input = ui.TextInput(
            label="Allowed Users (IDs/Mentions comma-sep)",
            default=", ".join(str(u) for u in users),
            placeholder="e.g. 123456789, <@987654321>",
            required=True
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        val = self.input.value.strip()
        if not val or val.lower() == "none":
            cfg["music_allowed_users"] = []
            save_config()
            from configuration_module import log_setting_change_task
            log_setting_change_task(interaction.guild, interaction.user, "Cleared Whitelisted Music Users")
            await interaction.response.defer()
            return await self.view.refresh(interaction)
            
        user_ids = []
        for u in val.split(","):
            cleaned = u.strip("<@&#>! ")
            if cleaned:
                try:
                    user_ids.append(int(cleaned))
                except ValueError:
                    member = discord.utils.get(interaction.guild.members, name=u.strip())
                    if member:
                        user_ids.append(member.id)
                    else:
                        return await interaction.response.send_message(f"Invalid User ID or name: {u.strip()}", ephemeral=True)
        cfg["music_allowed_users"] = user_ids
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Whitelisted Music Users to: {user_ids}")
        await interaction.response.defer()
        await self.view.refresh(interaction)

class MusicPermissionsConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        role_restrict = cfg.get("music_role_restriction_enabled", False)
        comp_restrict = cfg.get("music_component_restriction_enabled", False)
        roles = cfg.get("music_allowed_roles", [])
        users = cfg.get("music_allowed_users", [])

        embed = discord.Embed(
            title="Nebot Module: Music Permissions Configuration",
            description="Restrict access to music commands, playback components, and voice channel control features to specific roles or users.",
            color=discord.Color.teal()
        )
        
        role_restrict_str = "Enabled" if role_restrict else "Disabled"
        comp_restrict_str = "Enabled" if comp_restrict else "Disabled"
        
        if roles:
            roles_str = ", ".join(f"<@&{r}>" for r in roles)
        else:
            roles_str = "None"

        if users:
            users_str = ", ".join(f"<@{u}>" for u in users)
        else:
            users_str = "None"

        embed.add_field(name="Role Restriction", value=role_restrict_str, inline=True)
        embed.add_field(name="Restrict Components", value=comp_restrict_str, inline=True)
        embed.add_field(name="Whitelisted Roles", value=roles_str, inline=False)
        embed.add_field(name="Whitelisted Users", value=users_str, inline=False)
        
        return embed

    @ui.button(label="Toggle Role Restriction", style=discord.ButtonStyle.primary, row=0)
    async def toggle_role_restriction(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["music_role_restriction_enabled"] = not cfg.get("music_role_restriction_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Music role restriction to `{'enabled' if cfg['music_role_restriction_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Whitelist Roles", style=discord.ButtonStyle.secondary, row=0)
    async def whitelist_roles(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(WhitelistRolesModal(self.guild_id, self))

    @ui.button(label="Whitelist Users", style=discord.ButtonStyle.secondary, row=0)
    async def whitelist_users(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(WhitelistUsersModal(self.guild_id, self))

    @ui.button(label="Restrict Components", style=discord.ButtonStyle.secondary, row=1)
    async def restrict_components(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["music_component_restriction_enabled"] = not cfg.get("music_component_restriction_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Music component restriction to `{'enabled' if cfg['music_component_restriction_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Back to Music Settings", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = MusicConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class WarningTypesModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Warning Platforms")
        cfg = get_guild_config(guild_id)
        platforms = cfg.get("warning_platforms", ["Discord"])
        self.input = ui.TextInput(
            label="Active Platforms (comma-separated)",
            default=", ".join(platforms),
            placeholder="e.g. Discord, Twitch",
            required=True
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        platforms = [p.strip() for p in self.input.value.split(",") if p.strip()]
        if not platforms:
            return await interaction.response.send_message("At least one platform is required.", ephemeral=True)
        cfg["warning_platforms"] = platforms
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Warning platforms to: {', '.join(platforms)}")
        await interaction.response.defer()
        dashboard = WarningTrackerDashboard(self.guild_id)
        await dashboard.refresh(interaction)

class SeveritySettingsModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Severity Settings")
        cfg = get_guild_config(self.guild_id)
        sev_pts = cfg.get("warning_severity_points", {"Low": 1, "Medium": 2, "High": 3})
        
        self.low_input = ui.TextInput(label="Low Severity Points", default=str(sev_pts.get("Low", 1)), required=True)
        self.med_input = ui.TextInput(label="Medium Severity Points", default=str(sev_pts.get("Medium", 2)), required=True)
        self.high_input = ui.TextInput(label="High Severity Points", default=str(sev_pts.get("High", 3)), required=True)
        
        self.add_item(self.low_input)
        self.add_item(self.med_input)
        self.add_item(self.high_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            low = int(self.low_input.value.strip())
            med = int(self.med_input.value.strip())
            high = int(self.high_input.value.strip())
            if low < 0 or med < 0 or high < 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("Points must be non-negative integers.", ephemeral=True)
        
        cfg = get_guild_config(self.guild_id)
        cfg["warning_severity_points"] = {"Low": low, "Medium": med, "High": high}
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Warning severity points to: Low={low}, Medium={med}, High={high}")
        await interaction.response.defer()
        dashboard = WarningTrackerDashboard(self.guild_id)
        await dashboard.refresh(interaction)

class RollingDaysModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Rolling Window Days")
        cfg = get_guild_config(self.guild_id)
        days = cfg.get("warning_rolling_window_days", 90)
        self.input = ui.TextInput(label="Rolling Days Expiration", default=str(days), placeholder="e.g. 90", required=True)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.input.value.strip())
            if days <= 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("Must be a positive integer.", ephemeral=True)
        
        cfg = get_guild_config(self.guild_id)
        cfg["warning_rolling_window_days"] = days
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Warning rolling window days expiration to {days}")
        await interaction.response.defer()
        dashboard = ConfigureLadderDashboard(self.guild_id)
        await dashboard.refresh(interaction)

class AddLadderRuleModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Add/Edit Escalation Rule")
        self.pts_input = ui.TextInput(label="Points Threshold", placeholder="e.g. 3", required=True)
        self.action_input = ui.TextInput(
            label="Action",
            placeholder="e.g. 5-minute timeout, Permanent ban, kick, None",
            default="10-minute timeout",
            required=True
        )
        self.add_item(self.pts_input)
        self.add_item(self.action_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            pts = int(self.pts_input.value.strip())
            if pts <= 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("Threshold must be a positive integer.", ephemeral=True)
        
        action = self.action_input.value.strip()
        cfg = get_guild_config(self.guild_id)
        if "warning_ladder" not in cfg:
            cfg["warning_ladder"] = {}
        
        if not action or action.lower() == "none":
            cfg["warning_ladder"].pop(str(pts), None)
        else:
            cfg["warning_ladder"][str(pts)] = action
        
        save_config()
        from configuration_module import log_setting_change_task
        if not action or action.lower() == "none":
            desc = f"Removed Warning escalation rule for {pts} points"
        else:
            desc = f"Updated Warning escalation rule for {pts} points to action: `{action}`"
        log_setting_change_task(interaction.guild, interaction.user, desc)
        await interaction.response.defer()
        dashboard = ConfigureLadderDashboard(self.guild_id)
        await dashboard.refresh(interaction)

class WarningLogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Warning Log Channel...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text], row=1)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["warning_log_channel_id"] = channel.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Warning Log Channel to {channel.mention}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Warning log channel set to <#{channel.id}>", ephemeral=True)

class WarningTrackerDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(WarningLogChannelSelect(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        enabled = cfg.get("warning_tracker_enabled", False)
        platforms = cfg.get("warning_platforms", ["Discord"])
        sev_pts = cfg.get("warning_severity_points", {"Low": 1, "Medium": 2, "High": 3})
        mode = cfg.get("warning_escalation_mode", "static")
        days = cfg.get("warning_rolling_window_days", 90)
        ladder = cfg.get("warning_ladder", {})
        log_ch = cfg.get("warning_log_channel_id")
        global_log = cfg.get("global_log_channel_id")
        if log_ch:
            log_ch_str = f"<#{log_ch}>"
        elif global_log:
            log_ch_str = f"<#{global_log}> (Global fallback)"
        else:
            log_ch_str = "None"
        dm_alert = cfg.get("warning_dm_enabled", False)
        dm_alert_str = "[ENABLED]" if dm_alert else "[DISABLED]"

        embed = discord.Embed(
            title="Nebot Module: Warning Tracker",
            description="Management and configuration for multi-platform moderation ladders and active infractions.",
            color=discord.Color.purple()
        )
        embed.add_field(name="Status", value="[ENABLED]" if enabled else "[DISABLED]", inline=True)
        embed.add_field(name="Active Platforms", value=", ".join(platforms), inline=True)
        embed.add_field(name="Escalation Mode", value=f"{mode.upper()}" + (f" ({days}d rolling)" if mode == "rolling" else ""), inline=True)
        
        # Show severity points
        sev_str = "\n".join([f"- {k}: {v} pt(s)" for k, v in sev_pts.items()])
        embed.add_field(name="Severity Point Weights", value=sev_str or "None", inline=True)
        embed.add_field(name="Warning Log Channel", value=log_ch_str, inline=True)
        embed.add_field(name="DM Warned Users", value=dm_alert_str, inline=True)

        # Show escalation ladder
        ladder_sorted = sorted(ladder.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
        ladder_str = "\n".join([f"- {pts} pts: {act}" for pts, act in ladder_sorted])
        embed.add_field(name="Escalation Ladder", value=ladder_str or "No actions configured", inline=False)
        
        return embed

    @ui.button(label="Toggle Warning Tracker", style=discord.ButtonStyle.primary, row=0)
    async def toggle_warning_tracker(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["warning_tracker_enabled"] = not cfg.get("warning_tracker_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Warning Tracker module state to `{'enabled' if cfg['warning_tracker_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Configure Ladder", style=discord.ButtonStyle.secondary, row=0)
    async def configure_ladder(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = ConfigureLadderDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Warning Types", style=discord.ButtonStyle.secondary, row=0)
    async def warning_types(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(WarningTypesModal(self.guild_id))

    @ui.button(label="Severity Settings", style=discord.ButtonStyle.secondary, row=0)
    async def severity_settings(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SeveritySettingsModal(self.guild_id))

    @ui.button(label="Clear Log Channel", style=discord.ButtonStyle.secondary, row=0)
    async def clear_log_channel(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["warning_log_channel_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Warning Log Channel configuration")
        await self.refresh(interaction)

    @ui.button(label="Toggle DM Alert", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_dm_alert(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["warning_dm_enabled"] = not cfg.get("warning_dm_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Warning DM alerts to `{'enabled' if cfg['warning_dm_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class ConfigureLadderDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        mode = cfg.get("warning_escalation_mode", "static")
        days = cfg.get("warning_rolling_window_days", 90)
        ladder = cfg.get("warning_ladder", {})

        embed = discord.Embed(
            title="Warning Tracker: Ladder Configuration",
            description="Define progression rules and how infractions escalate.",
            color=discord.Color.dark_purple()
        )
        embed.add_field(name="Escalation Mode", value="STATIC" if mode == "static" else f"ROLLING ({days}-day window)", inline=False)
        
        # Show escalation ladder
        ladder_sorted = sorted(ladder.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
        ladder_str = "\n".join([f"- {pts} pts: {act}" for pts, act in ladder_sorted])
        embed.add_field(name="Escalation Ladder Mappings", value=ladder_str or "No actions configured", inline=False)
        
        return embed

    @ui.button(label="Toggle Mode", style=discord.ButtonStyle.primary)
    async def toggle_mode(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        mode = cfg.get("warning_escalation_mode", "static")
        cfg["warning_escalation_mode"] = "rolling" if mode == "static" else "static"
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Warning escalation mode to `{cfg.get('warning_escalation_mode', 'static').upper()}`")
        await self.refresh(interaction)

    @ui.button(label="Set Rolling Days", style=discord.ButtonStyle.secondary)
    async def set_rolling_days(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RollingDaysModal(self.guild_id))

    @ui.button(label="Add/Edit Rule", style=discord.ButtonStyle.secondary)
    async def add_rule(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AddLadderRuleModal(self.guild_id))

    @ui.button(label="Back to Warning Tracker", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = WarningTrackerDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)



class BattleUserModal(ui.Modal, title="Battle User"):
    user_input = ui.TextInput(label="User ID or Mention or Username", placeholder="e.g. 123456789012345678 or @username", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        user = await resolve_user(interaction.guild, interaction.client, self.user_input.value)
        if not user:
            return await interaction.response.send_message("User not found.", ephemeral=True)

        if not isinstance(user, discord.Member):
            member = interaction.guild.get_member(user.id)
            if not member:
                return await interaction.response.send_message("User is not in this server.", ephemeral=True)
            user = member

        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("battle_enabled", False):
            await interaction.response.send_message("The battle system is disabled on this server.", ephemeral=True)
            return

        from battle_module import active_battles, pending_challenges, players_in_battle, BattleChallengeView

        if user.id == interaction.user.id:
            await interaction.response.send_message("You cannot battle yourself.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("hey silly you cant battle a bot", ephemeral=True)
            return

        if interaction.channel_id in active_battles:
            await interaction.response.send_message("There is already an active battle in this channel.", ephemeral=True)
            return

        if interaction.channel_id in pending_challenges:
            await interaction.response.send_message("There is already a pending challenge in this channel.", ephemeral=True)
            return

        if interaction.user.id in players_in_battle:
            await interaction.response.send_message("You are already in an active battle.", ephemeral=True)
            return
        if user.id in players_in_battle:
            await interaction.response.send_message(f"{user.display_name} is already in an active battle.", ephemeral=True)
            return

        # Register pending challenge
        pending_challenges.add(interaction.channel_id)

        battle_hp = cfg.get("battle_default_hp", 500)

        view = BattleChallengeView(interaction.user, user, interaction.channel_id)
        embed = discord.Embed(
            title="BATTLE CHALLENGE",
            description=(
                f"{interaction.user.mention} has challenged {user.mention} to a BATTLE!! "
                f"Both players start with {battle_hp} HP.\n\n"
                f"{user.mention}, click Accept to start the battle."
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(content=user.mention, embed=embed, view=view)
        view.message = await interaction.original_response()

class PlayMusicModal(ui.Modal, title="Play Music"):
    query_input = ui.TextInput(label="Search Query or URL", placeholder="e.g. Never Gonna Give You Up", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("music_enabled", False):
            await interaction.response.send_message("The Music module is disabled on this server.", ephemeral=True)
            return

        from music_permissions_handler import check_command_permissions
        if not await check_command_permissions(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.followup.send("You must be in a voice channel to use this command.", ephemeral=True)
            return

        author_channel = member.voice.channel
        import wavelink
        from music_module import NebotPlayer, DEFAULT_VOLUME, prepare_query, update_play_window, process_play_request

        if not interaction.guild.voice_client:
            try:
                player = await author_channel.connect(cls=NebotPlayer)
                await player.set_volume(DEFAULT_VOLUME)
            except Exception as e:
                await interaction.followup.send(f"Failed to connect to voice channel: {e}", ephemeral=True)
                return
        else:
            player = interaction.guild.voice_client
            if not isinstance(player, NebotPlayer):
                await player.disconnect()
                player = await author_channel.connect(cls=NebotPlayer)
                await player.set_volume(DEFAULT_VOLUME)
            elif player.channel.id != author_channel.id:
                try:
                    await player.move_to(author_channel)
                except Exception as e:
                    await interaction.followup.send(f"Failed to move to voice channel: {e}", ephemeral=True)
                    return

        player.text_channel = author_channel

        query = self.query_input.value
        await process_play_request(interaction, query, member, player)


class MemberAnalyticsDashboardView(ui.View):
    def __init__(self, guild_id: int, user: discord.Member, window: str = "24h"):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.window = window
        self.refresh_buttons()

    def refresh_buttons(self):
        self.clear_items()
        cfg = get_guild_config(self.guild_id)
        if cfg.get("analytics_enabled", False):
            label = "Switch to 7 Days" if self.window == "24h" else "Switch to 24 Hours"
            btn_toggle = ui.Button(label=label, style=discord.ButtonStyle.primary, row=0)
            btn_toggle.callback = self.toggle_window
            self.add_item(btn_toggle)
            
        btn_back = ui.Button(label="Back to Dashboard", style=discord.ButtonStyle.danger, row=0)
        btn_back.callback = self.back_to_dashboard
        self.add_item(btn_back)

    async def toggle_window(self, interaction: discord.Interaction):
        self.window = "7d" if self.window == "24h" else "24h"
        self.refresh_buttons()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def back_to_dashboard(self, interaction: discord.Interaction):
        dashboard = UserDashboardView(self.guild_id, self.user)
        embed = await dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        if not cfg.get("analytics_enabled", False):
            embed = discord.Embed(
                title="Server Analytics",
                description="Server Activity Analytics collection is currently disabled on this server.",
                color=discord.Color.red()
            )
            return embed

        from analytics_module import load_analytics_records
        import datetime
        g_str = str(self.guild_id)
        records = await load_analytics_records()
        guild_data = records.get(g_str, {})
        
        now = datetime.datetime.utcnow()
        if self.window == "24h":
            cutoff = now - datetime.timedelta(hours=24)
        else:
            cutoff = now - datetime.timedelta(days=7)
            
        cutoff_ts = cutoff.timestamp()
        
        messages_data = guild_data.get("messages", {})
        total_messages = 0
        hourly_totals = {}
        channel_totals = {}
        
        for ch_id_str, hours in messages_data.items():
            for hr_str, count in hours.items():
                try:
                    dt = datetime.datetime.fromisoformat(hr_str.replace("Z", "+00:00"))
                    if dt.replace(tzinfo=None) >= cutoff:
                        total_messages += count
                        hourly_totals[hr_str] = hourly_totals.get(hr_str, 0) + count
                        channel_totals[ch_id_str] = channel_totals.get(ch_id_str, 0) + count
                except Exception:
                    pass
                    
        if hourly_totals:
            peak_hr_str = max(hourly_totals, key=hourly_totals.get)
            peak_count = hourly_totals[peak_hr_str]
            try:
                dt = datetime.datetime.fromisoformat(peak_hr_str.replace("Z", "+00:00"))
                peak_hour_formatted = dt.strftime("%H:00 UTC")
            except Exception:
                peak_hour_formatted = "Unknown"
        else:
            peak_hour_formatted = "None"
            peak_count = 0
            
        if channel_totals:
            most_active_id = max(channel_totals, key=channel_totals.get)
            most_active_cnt = channel_totals[most_active_id]
            pct = (most_active_cnt / total_messages * 100) if total_messages > 0 else 0.0
            most_active_channel_str = f"<#{most_active_id}> ({pct:.1f}% of total volume)"
        else:
            most_active_channel_str = "None (0.0% of total volume)"
            
        churn_data = guild_data.get("churn", [])
        joins = 0
        leaves = 0
        for event in churn_data:
            if event.get("timestamp", 0) >= cutoff_ts:
                if event.get("event") == "join":
                    joins += 1
                elif event.get("event") == "leave":
                    leaves += 1
        net_growth = joins - leaves
        
        voice_data = guild_data.get("voice", [])
        voice_counts = []
        for pt in voice_data:
            if pt.get("timestamp", 0) >= cutoff_ts:
                voice_counts.append(pt.get("count", 0))
                
        if voice_counts:
            peak_voice = max(voice_counts)
            avg_voice = sum(voice_counts) / len(voice_counts)
        else:
            peak_voice = 0
            avg_voice = 0.0
            
        embed = discord.Embed(
            title=f"Server Analytics Report — {self.window.upper()} Window",
            description=f"Activity metrics and user churn trends for **{self.user.guild.name}**.",
            color=discord.Color.blue()
        )
        
        chat_val = (
            f"Total Messages Processed: **{total_messages}**\n"
            f"Peak Message Hour: **{peak_hour_formatted}** ({peak_count} messages)\n"
            f"Most Active Channel: {most_active_channel_str}"
        )
        embed.add_field(name="Chat Activity Metrics", value=chat_val, inline=False)
        
        churn_val = (
            f"Members Joined: **{joins}**\n"
            f"Members Left: **{leaves}**\n"
            f"Net Growth: **{net_growth}**"
        )
        embed.add_field(name="Member Churn Trends", value=churn_val, inline=False)
        
        voice_val = (
            f"Peak Voice Concurrency: **{peak_voice}** members\n"
            f"Average Voice Concurrency: **{avg_voice:.1f}** members"
        )
        embed.add_field(name="Voice Activity Metrics", value=voice_val, inline=False)
        
        return embed

class MemberMusicDashboardView(ui.View):
    def __init__(self, guild_id: int, user: discord.Member):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.refresh_buttons()

    def refresh_buttons(self):
        self.clear_items()
        cfg = get_guild_config(self.guild_id)
        music_enabled = cfg.get("music_enabled", False)
        
        if music_enabled:
            btn_play = ui.Button(label="Play Song", style=discord.ButtonStyle.primary, row=0)
            btn_play.callback = self.play_song
            self.add_item(btn_play)
            
            guild = self.user.guild
            if guild and guild.voice_client:
                player = guild.voice_client
                btn_skip = ui.Button(label="Skip", style=discord.ButtonStyle.secondary, row=0)
                btn_skip.callback = self.skip_song
                self.add_item(btn_skip)
                
                paused = getattr(player, "paused", False)
                label = "Resume" if paused else "Pause"
                btn_pause = ui.Button(label=label, style=discord.ButtonStyle.secondary, row=0)
                btn_pause.callback = self.pause_resume
                self.add_item(btn_pause)
                
                btn_stop = ui.Button(label="Stop", style=discord.ButtonStyle.danger, row=0)
                btn_stop.callback = self.stop_music
                self.add_item(btn_stop)
                
        btn_back = ui.Button(label="Back to Dashboard", style=discord.ButtonStyle.danger, row=1)
        btn_back.callback = self.back_to_dashboard
        self.add_item(btn_back)

    async def play_song(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PlayMusicModal())

    async def skip_song(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild and guild.voice_client:
            player = guild.voice_client
            if interaction.user.voice and interaction.user.voice.channel.id == player.channel.id:
                if not player.queue.is_empty:
                    next_track = player.queue.get()
                    await player.play(next_track)
                    await interaction.response.send_message(f"Skipped to **{next_track.title}**.", ephemeral=True)
                else:
                    await player.skip()
                    await interaction.response.send_message("Skipped track. Queue is empty.", ephemeral=True)
                self.refresh_buttons()
                embed = await self.build_embed()
                await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
            else:
                await interaction.response.send_message("You must be in the same voice channel to skip.", ephemeral=True)
        else:
            await interaction.response.send_message("No music is playing.", ephemeral=True)

    async def pause_resume(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild and guild.voice_client:
            player = guild.voice_client
            if interaction.user.voice and interaction.user.voice.channel.id == player.channel.id:
                paused = getattr(player, "paused", False)
                await player.pause(not paused)
                await interaction.response.send_message("Paused playback." if not paused else "Resumed playback.", ephemeral=True)
                self.refresh_buttons()
                embed = await self.build_embed()
                await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
            else:
                await interaction.response.send_message("You must be in the same voice channel to pause/resume.", ephemeral=True)
        else:
            await interaction.response.send_message("No music is playing.", ephemeral=True)

    async def stop_music(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild and guild.voice_client:
            player = guild.voice_client
            if interaction.user.voice and interaction.user.voice.channel.id == player.channel.id:
                player.queue.clear()
                await player.disconnect()
                await interaction.response.send_message("Stopped playback and disconnected.", ephemeral=True)
                self.refresh_buttons()
                embed = await self.build_embed()
                await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
            else:
                await interaction.response.send_message("You must be in the same voice channel to stop.", ephemeral=True)
        else:
            await interaction.response.send_message("No music is playing.", ephemeral=True)

    async def back_to_dashboard(self, interaction: discord.Interaction):
        dashboard = UserDashboardView(self.guild_id, self.user)
        embed = await dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        if not cfg.get("music_enabled", False):
            return discord.Embed(
                title="Music Player",
                description="Music streaming is currently disabled on this server.",
                color=discord.Color.red()
            )
            
        embed = discord.Embed(
            title="Nebot Music Player",
            color=discord.Color.blue()
        )
        
        guild = self.user.guild
        if guild and guild.voice_client:
            player = guild.voice_client
            current = getattr(player, "current", None)
            
            if current:
                status = "Paused" if getattr(player, "paused", False) else "Playing"
                dur = getattr(current, "length", 0) // 1000
                m, s = divmod(dur, 60)
                dur_str = f"{m}:{s:02d}"
                
                desc = (
                    f"**Now {status}:** [{current.title}]({current.uri if hasattr(current, 'uri') else ''})\n"
                    f"**Duration:** `{dur_str}`\n"
                    f"**Connected to VC:** {player.channel.mention}\n"
                )
                
                q_len = len(player.queue)
                if q_len > 0:
                    desc += f"\n**Queue ({q_len} tracks enqueued):**\n"
                    tracks = list(player.queue)
                    for i, t in enumerate(tracks[:5]):
                        td = getattr(t, "length", 0) // 1000
                        tm, ts = divmod(td, 60)
                        desc += f"{i+1}. {t.title} (`{tm}:{ts:02d}`)\n"
                    if q_len > 5:
                        desc += f"*and {q_len - 5} more...*"
                else:
                    desc += "\n*Queue is empty.*"
                embed.description = desc
            else:
                embed.description = f"Connected to {player.channel.mention} but currently idle."
        else:
            embed.description = "No music is currently playing in this server. Click **Play Song** below to begin streaming!"
            
        return embed

class MemberGamesView(ui.View):
    def __init__(self, guild_id: int, user: discord.Member):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.refresh_buttons()

    def refresh_buttons(self):
        self.clear_items()
        cfg = get_guild_config(self.guild_id)
        ms_en = cfg.get("minesweeper_enabled", False)
        bt_en = cfg.get("battle_enabled", False)

        btn_minesweeper = ui.Button(
            label="Play Minesweeper",
            style=discord.ButtonStyle.success if ms_en else discord.ButtonStyle.danger,
            row=0
        )
        btn_minesweeper.callback = self.play_minesweeper
        self.add_item(btn_minesweeper)

        btn_battle = ui.Button(
            label="Battle User",
            style=discord.ButtonStyle.success if bt_en else discord.ButtonStyle.danger,
            row=0
        )
        btn_battle.callback = self.battle_user
        self.add_item(btn_battle)

        btn_back = ui.Button(label="Back to Dashboard", style=discord.ButtonStyle.danger, row=1)
        btn_back.callback = self.back
        self.add_item(btn_back)

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        ms_en = cfg.get("minesweeper_enabled", False)
        bt_en = cfg.get("battle_enabled", False)
        
        embed = discord.Embed(
            title="Nebot Game Zone",
            description="Challenge yourself or others with our inbuilt interactive games!",
            color=discord.Color.green()
        )
        embed.add_field(name="Minesweeper", value="[ENABLED]" if ms_en else "[DISABLED]", inline=True)
        embed.add_field(name="Battle Arena", value="[ENABLED]" if bt_en else "[DISABLED]", inline=True)
        return embed

    async def play_minesweeper(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        if not cfg.get("minesweeper_enabled", False):
            await interaction.response.send_message("Minesweeper is disabled on this server.", ephemeral=True)
            return
        actual_mines = cfg.get("minesweeper_default_mines", 4)
        from minesweeper_module import MinesweeperView
        view = MinesweeperView(interaction.user, num_mines=actual_mines)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def battle_user(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        if not cfg.get("battle_enabled", False):
            await interaction.response.send_message("Battle module is disabled on this server.", ephemeral=True)
            return
        await interaction.response.send_modal(BattleUserModal())

    async def back(self, interaction: discord.Interaction):
        dashboard = UserDashboardView(self.guild_id, self.user)
        embed = await dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

class MemberStatsView(ui.View):
    def __init__(self, guild_id: int, user: discord.Member):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user

    @ui.button(label="Back to Dashboard", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = UserDashboardView(self.guild_id, self.user)
        embed = await dashboard.build_embed()
        await interaction.response.edit_message(embeds=[embed], view=dashboard)

class UserDashboardView(ui.View):
    def __init__(self, guild_id: int, user: discord.Member):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.refresh_items()

    def refresh_items(self):
        self.clear_items()
        
        btn_plurality = ui.Button(label="Plurality Settings", style=discord.ButtonStyle.primary, row=0)
        btn_plurality.callback = self.go_plurality
        self.add_item(btn_plurality)
        
        btn_analytics = ui.Button(label="Server Analytics", style=discord.ButtonStyle.secondary, row=0)
        btn_analytics.callback = self.go_analytics
        self.add_item(btn_analytics)
        
        btn_music = ui.Button(label="Music Player", style=discord.ButtonStyle.secondary, row=0)
        btn_music.callback = self.go_music
        self.add_item(btn_music)
        
        btn_games = ui.Button(label="Play Games", style=discord.ButtonStyle.success, row=1)
        btn_games.callback = self.go_games
        self.add_item(btn_games)
        
        btn_stats = ui.Button(label="My Statistics", style=discord.ButtonStyle.secondary, row=1)
        btn_stats.callback = self.go_stats
        self.add_item(btn_stats)

    async def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        from plurality_module import plurality_data
        
        user_id = str(self.user.id)
        system = plurality_data.get(user_id, {})
        sys_name = system.get("system_name", None)
        system_tag = system.get("system_tag", None)
        alters_count = len(system.get("members", {}))
        fronting_short = system.get("fronting_member")
        
        fronting_str = ""
        if fronting_short and fronting_short in system.get("members", {}):
            fronting_name = system["members"][fronting_short].get("display_name", fronting_short)
            fronting_str = f" | Fronting: {fronting_name}"
            
        tag_str = f" [{system_tag}]" if system_tag else ""
        
        pl_status = f"System: **{sys_name}**{tag_str}{fronting_str} ({alters_count} members)" if sys_name else "System: Not Registered"
        
        guild = self.user.guild
        if guild and guild.voice_client:
            player = guild.voice_client
            current = getattr(player, "current", None)
            if current:
                music_status = f"Playing: **{current.title}**"
            else:
                music_status = "Connected / Idle"
        else:
            music_status = "Not Connected"
            
        embed = discord.Embed(
            title="Nebot Member Control Panel",
            description=f"Welcome, {self.user.mention}! Here are your quick configuration panels and activities on **{self.user.guild.name}**.",
            color=discord.Color.blue()
        )
        try:
            avatar_url = self.user.display_avatar.url if self.user.display_avatar else None
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
        except Exception:
            pass
        
        embed.add_field(name="Your Profiles", value=f"{pl_status}", inline=False)
        embed.add_field(name="Current Server Stream", value=f"{music_status}", inline=False)
        
        pl_enabled = cfg.get("plurality_enabled", False)
        an_enabled = cfg.get("analytics_enabled", False)
        ms_enabled = cfg.get("minesweeper_enabled", False)
        bt_enabled = cfg.get("battle_enabled", False)
        mu_enabled = cfg.get("music_enabled", False)
        
        mods = []
        if pl_enabled: mods.append("Plurality")
        if an_enabled: mods.append("Analytics")
        if ms_enabled or bt_enabled: mods.append("Games")
        if mu_enabled: mods.append("Music")
        
        embed.add_field(name="Available Modules", value=", ".join(mods) if mods else "None", inline=False)
        
        return embed

    async def go_plurality(self, interaction: discord.Interaction):
        from plurality_module import PluralityConfigUserView
        view = PluralityConfigUserView(self.guild_id, self.user)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def go_analytics(self, interaction: discord.Interaction):
        view = MemberAnalyticsDashboardView(self.guild_id, self.user)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def go_music(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PlayMusicModal())

    async def go_games(self, interaction: discord.Interaction):
        view = MemberGamesView(self.guild_id, self.user)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def go_stats(self, interaction: discord.Interaction):
        from battle_module import build_user_stats_embeds
        embeds = await build_user_stats_embeds(self.guild_id, self.user)
        view = MemberStatsView(self.guild_id, self.user)
        await interaction.response.edit_message(embeds=embeds, view=view)

class ModuleSelectView(ui.View):

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
        cfg = get_guild_config(guild_id)
        
        # Style row 0 buttons (Global Settings, Quick Actions & Tools are always grey/secondary)
        self.config_global.style = discord.ButtonStyle.secondary
        self.config_global.label = "Global Settings"
        
        self.quick_actions.style = discord.ButtonStyle.secondary
        self.quick_actions.label = "Quick Options"
        
        self.tools_page.style = discord.ButtonStyle.secondary
        self.tools_page.label = "Tools"
        
        # Style module buttons based on enable status
        ne_os_en = cfg.get("ne_os_enabled", False)
        self.config_neos.style = discord.ButtonStyle.success if ne_os_en else discord.ButtonStyle.danger
        self.config_neos.label = "Ne-OS Shell Module"
        
        battle_en = cfg.get("battle_enabled", False)
        self.config_battle.style = discord.ButtonStyle.success if battle_en else discord.ButtonStyle.danger
        self.config_battle.label = "Battle Game Module"
        
        mines_en = cfg.get("minesweeper_enabled", False)
        self.config_minesweeper.style = discord.ButtonStyle.success if mines_en else discord.ButtonStyle.danger
        self.config_minesweeper.label = "Minesweeper Module"
        
        warning_en = cfg.get("warning_tracker_enabled", False)
        self.config_warning_tracker.style = discord.ButtonStyle.success if warning_en else discord.ButtonStyle.danger
        self.config_warning_tracker.label = "Warning Tracker Module"
        
        nebuff_en = cfg.get("nebuff_module_enabled", False)
        self.config_nebuff_module.style = discord.ButtonStyle.success if nebuff_en else discord.ButtonStyle.danger
        self.config_nebuff_module.label = "Nebuff Funny Module"

        verification_en = cfg.get("verification_enabled", False)
        self.config_verification.style = discord.ButtonStyle.success if verification_en else discord.ButtonStyle.danger
        self.config_verification.label = "Verification Module"

        auto_roller_en = cfg.get("auto_roller_enabled", False)
        self.config_autoroller.style = discord.ButtonStyle.success if auto_roller_en else discord.ButtonStyle.danger
        self.config_autoroller.label = "Auto-Roller Module"

        automod_en = cfg.get("automod_enabled", False)
        self.config_automod.style = discord.ButtonStyle.success if automod_en else discord.ButtonStyle.danger
        self.config_automod.label = "AutoMod Module"

        music_en = cfg.get("music_enabled", False)
        self.config_music.style = discord.ButtonStyle.success if music_en else discord.ButtonStyle.danger
        self.config_music.label = "Music Module"

        vc_wr_en = cfg.get("vc_wr_enabled", False)
        self.config_vcwr.style = discord.ButtonStyle.success if vc_wr_en else discord.ButtonStyle.danger
        self.config_vcwr.label = "VC WR Module"

        analytics_en = cfg.get("analytics_enabled", False)
        self.config_analytics.style = discord.ButtonStyle.success if analytics_en else discord.ButtonStyle.danger
        self.config_analytics.label = "Server Analytics Module"

        join_filter_en = cfg.get("join_filter_enabled", False)
        self.config_join_filtering.style = discord.ButtonStyle.success if join_filter_en else discord.ButtonStyle.danger
        self.config_join_filtering.label = "Configure Join Filter"

        plurality_en = cfg.get("plurality_enabled", False)
        self.config_plurality.style = discord.ButtonStyle.success if plurality_en else discord.ButtonStyle.danger
        self.config_plurality.label = "Plurality Module"

        self_roles_en = cfg.get("self_roles_enabled", False)
        self.config_self_roles.style = discord.ButtonStyle.success if self_roles_en else discord.ButtonStyle.danger
        self.config_self_roles.label = "Self Roles Module"


    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        ne_os_en = cfg.get("ne_os_enabled", False)
        battle_en = cfg.get("battle_enabled", False)
        mines_en = cfg.get("minesweeper_enabled", False)
        warning_en = cfg.get("warning_tracker_enabled", False)
        verification_en = cfg.get("verification_enabled", False)
        auto_roller_en = cfg.get("auto_roller_enabled", False)
        automod_en = cfg.get("automod_enabled", False)
        music_en = cfg.get("music_enabled", False)
        vc_wr_en = cfg.get("vc_wr_enabled", False)
        analytics_en = cfg.get("analytics_enabled", False)
        join_filter_en = cfg.get("join_filter_enabled", False)
        nebuff_en = cfg.get("nebuff_module_enabled", False)
        plurality_en = cfg.get("plurality_enabled", False)
        self_roles_en = cfg.get("self_roles_enabled", False)

        embed = discord.Embed(
            title="Nebot Module Manager",
            description="Status overview of all server modules. Enabled modules are highlighted in green, disabled in red.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Ne-OS Shell Module", value="[ENABLED]" if ne_os_en else "[DISABLED]", inline=True)
        embed.add_field(name="Battle Game Module", value="[ENABLED]" if battle_en else "[DISABLED]", inline=True)
        embed.add_field(name="Minesweeper Module", value="[ENABLED]" if mines_en else "[DISABLED]", inline=True)
        embed.add_field(name="Warning Tracker Module", value="[ENABLED]" if warning_en else "[DISABLED]", inline=True)
        embed.add_field(name="Verification Module", value="[ENABLED]" if verification_en else "[DISABLED]", inline=True)
        embed.add_field(name="Auto-Roller Module", value="[ENABLED]" if auto_roller_en else "[DISABLED]", inline=True)
        embed.add_field(name="AutoMod Module", value="[ENABLED]" if automod_en else "[DISABLED]", inline=True)
        embed.add_field(name="Music Module", value="[ENABLED]" if music_en else "[DISABLED]", inline=True)
        embed.add_field(name="VC WR Module", value="[ENABLED]" if vc_wr_en else "[DISABLED]", inline=True)
        embed.add_field(name="Server Analytics Module", value="[ENABLED]" if analytics_en else "[DISABLED]", inline=True)
        embed.add_field(name="Join Filtering Module", value="[ENABLED]" if join_filter_en else "[DISABLED]", inline=True)
        embed.add_field(name="Nebuff Funny Module", value="[ENABLED]" if nebuff_en else "[DISABLED]", inline=True)
        embed.add_field(name="Plurality Module", value="[ENABLED]" if plurality_en else "[DISABLED]", inline=True)
        embed.add_field(name="Self Roles Module", value="[ENABLED]" if self_roles_en else "[DISABLED]", inline=True)
        return embed

    @ui.button(label="Global Settings", style=discord.ButtonStyle.secondary, row=0)
    async def config_global(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = GlobalConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Quick Actions", style=discord.ButtonStyle.secondary, row=0)
    async def quick_actions(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="**Nebot Quick Administrative Actions**", embed=None, view=QuickActionsView(self.guild_id))

    @ui.button(label="Tools", style=discord.ButtonStyle.secondary, row=0)
    async def tools_page(self, interaction: discord.Interaction, button: ui.Button):
        view = ToolsView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @ui.button(label="Configure Ne-OS Module", style=discord.ButtonStyle.secondary, row=1)
    async def config_neos(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = NeOSConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Plurality Module", style=discord.ButtonStyle.secondary, row=4)
    async def config_plurality(self, interaction: discord.Interaction, button: ui.Button):
        from plurality_module import PluralityConfigDashboard
        dashboard = PluralityConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Self Roles Module", style=discord.ButtonStyle.secondary, row=4)
    async def config_self_roles(self, interaction: discord.Interaction, button: ui.Button):
        from self_assignable_roles_module import SelfRolesConfigDashboard
        dashboard = SelfRolesConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure Battle Module", style=discord.ButtonStyle.secondary, row=1)
    async def config_battle(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = BattleConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure Minesweeper Module", style=discord.ButtonStyle.secondary, row=1)
    async def config_minesweeper(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = MinesweeperConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure Warning Tracker", style=discord.ButtonStyle.secondary, row=2)
    async def config_warning_tracker(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = WarningTrackerDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure Verification", style=discord.ButtonStyle.secondary, row=2)
    async def config_verification(self, interaction: discord.Interaction, button: ui.Button):
        from verification_module import VerificationConfigDashboard
        dashboard = VerificationConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure Auto-Roller", style=discord.ButtonStyle.secondary, row=2)
    async def config_autoroller(self, interaction: discord.Interaction, button: ui.Button):
        from auto_roller_module import AutoRollerConfigDashboard
        dashboard = AutoRollerConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure AutoMod", style=discord.ButtonStyle.secondary, row=3)
    async def config_automod(self, interaction: discord.Interaction, button: ui.Button):
        from automod_module import AutoModConfigDashboard
        dashboard = AutoModConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure Music Module", style=discord.ButtonStyle.secondary, row=3)
    async def config_music(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = MusicConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure VC WR Module", style=discord.ButtonStyle.secondary, row=3)
    async def config_vcwr(self, interaction: discord.Interaction, button: ui.Button):
        from vc_wr_module import VCWRConfigDashboard
        dashboard = VCWRConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure Server Analytics", style=discord.ButtonStyle.secondary, row=4)
    async def config_analytics(self, interaction: discord.Interaction, button: ui.Button):
        from analytics_module import AnalyticsConfigDashboard
        dashboard = AnalyticsConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Configure Join Filtering", style=discord.ButtonStyle.secondary, row=4)
    async def config_join_filtering(self, interaction: discord.Interaction, button: ui.Button):
        from join_filtering_module import JoinFilteringConfigDashboard
        dashboard = JoinFilteringConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=dashboard)

    @ui.button(label="Toggle Nebuff Module", style=discord.ButtonStyle.secondary, row=4)
    async def config_nebuff_module(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["nebuff_module_enabled"] = not cfg.get("nebuff_module_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Nebuff module state to `{'enabled' if cfg['nebuff_module_enabled'] else 'disabled'}`")

        # Update button visual
        nebuff_en = cfg.get("nebuff_module_enabled", False)
        self.config_nebuff_module.style = discord.ButtonStyle.success if nebuff_en else discord.ButtonStyle.danger
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    # Auto-Namer configuration is now accessed via the Tools panel
import os

async def resolve_user(guild: discord.Guild, client: discord.Client, input_str: str) -> discord.User | discord.Member | None:
    input_str = input_str.strip()
    user_id_str = input_str
    if user_id_str.startswith("<@") and user_id_str.endswith(">"):
        user_id_str = user_id_str.strip("<@!>")
    
    if user_id_str.isdigit():
        member = guild.get_member(int(user_id_str))
        if member:
            return member
        try:
            user = await client.fetch_user(int(user_id_str))
            if user:
                return user
        except Exception:
            pass
            
    # Try resolving by username or Nickname in guild
    for member in guild.members:
        if member.name.lower() == input_str.lower() or (member.nick and member.nick.lower() == input_str.lower()):
            return member
            
    return None

class ModBanModal(ui.Modal, title="Ban User"):
    user_input = ui.TextInput(label="User ID or Mention or Username", placeholder="e.g. 123456789012345678 or @username", required=True)
    reason_input = ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, placeholder="Reason for ban", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        if not is_mod(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        user = await resolve_user(interaction.guild, interaction.client, self.user_input.value)
        if not user:
            return await interaction.response.send_message("User not found.", ephemeral=True)
        
        reason = self.reason_input.value or "No reason provided"
        from warning_tracker_module import make_discord_target, execute_moderation_action
        target = make_discord_target(user)
        msg = await execute_moderation_action(interaction.guild, [target], "ban", reason, moderator=interaction.user)
        await interaction.response.send_message(msg, ephemeral=True)

class ModKickModal(ui.Modal, title="Kick User"):
    user_input = ui.TextInput(label="User ID or Mention or Username", placeholder="e.g. 123456789012345678 or @username", required=True)
    reason_input = ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, placeholder="Reason for kick", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        if not is_mod(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        user = await resolve_user(interaction.guild, interaction.client, self.user_input.value)
        if not user:
            return await interaction.response.send_message("User not found.", ephemeral=True)
        
        if not isinstance(user, discord.Member):
            member = interaction.guild.get_member(user.id)
            if not member:
                return await interaction.response.send_message("User is not in this server, cannot kick.", ephemeral=True)
            user = member

        reason = self.reason_input.value or "No reason provided"
        from warning_tracker_module import make_discord_target, execute_moderation_action
        target = make_discord_target(user)
        msg = await execute_moderation_action(interaction.guild, [target], "kick", reason, moderator=interaction.user)
        await interaction.response.send_message(msg, ephemeral=True)

class ModSendWarningModal(ui.Modal, title="Send Warning"):
    user_input = ui.TextInput(label="User ID or Mention or Username", placeholder="e.g. @username", required=True)

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        if not is_mod(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        if not cfg.get("warning_tracker_enabled", False):
            return await interaction.response.send_message("The Warning Tracker module is disabled on this server.", ephemeral=True)

        user = await resolve_user(interaction.guild, interaction.client, self.user_input.value)
        targets = []
        if user:
            from warning_tracker_module import make_discord_target
            targets.append(make_discord_target(user))
            targets_str = f"Discord: {user.name} (ID: {user.id})"
        else:
            val = self.user_input.value.strip()
            if val.lower().startswith("twitch:"):
                from warning_tracker_module import make_twitch_target
                twitch_user = val[7:].strip()
                targets.append(make_twitch_target(twitch_user))
                targets_str = f"Twitch: {twitch_user}"
            else:
                from warning_tracker_module import make_discord_id_target
                user_id_str = val
                if user_id_str.startswith("<@") and user_id_str.endswith(">"):
                    user_id_str = user_id_str.strip("<@!>")
                targets.append(await make_discord_id_target(interaction.guild, interaction.client, user_id_str))
                targets_str = f"ID: {user_id_str}"

        from warning_tracker_module import get_user_warnings, WizardConfirmView
        past_warnings = await get_user_warnings(self.guild_id, targets)
        
        if past_warnings:
            total_pts = sum(r.get("points", 0) for r in past_warnings)
            embed = discord.Embed(
                title="Is this the user? Active historical warnings found.",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Warning Targets", value=targets_str, inline=False)
            embed.add_field(name="Warning Count", value=f"{len(past_warnings)} warnings")
            embed.add_field(name="Total Historical Points", value=f"{total_pts} points")
            
            recent = []
            for r in past_warnings[:3]:
                ts = r.get("timestamp", "").split("T")[0]
                recent.append(f"`{ts}` [{r.get('severity')}]: {r.get('details')}")
            embed.add_field(name="Recent Violations", value="\n".join(recent) if recent else "None", inline=False)
            
            view = WizardConfirmView(targets, self.guild_id, interaction.user.id, cfg)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            embed = discord.Embed(
                title="Is this the user? No active historical warnings found.",
                description=f"Proceed to log a new infraction for targets:\n**{targets_str}**?",
                color=discord.Color.light_grey()
            )
            view = WizardConfirmView(targets, self.guild_id, interaction.user.id, cfg)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ModViewWarningModal(ui.Modal, title="View Warnings"):
    user_input = ui.TextInput(label="User ID or Mention or Username", placeholder="e.g. 123456789012345678 or @username", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        if not is_mod(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        input_val = self.user_input.value.strip()
        targets = []
        search_name = ""
        
        from warning_tracker_module import make_twitch_target, make_discord_target, make_discord_id_target
        if input_val.lower().startswith("twitch:"):
            twitch_user = input_val[7:].strip()
            targets.append(make_twitch_target(twitch_user))
            search_name = f"Twitch: {twitch_user}"
        else:
            user = await resolve_user(interaction.guild, interaction.client, input_val)
            if user:
                targets.append(make_discord_target(user))
                search_name = user.name
            else:
                user_id_str = input_val
                if user_id_str.startswith("<@") and user_id_str.endswith(">"):
                    user_id_str = user_id_str.strip("<@!>")
                targets.append(await make_discord_id_target(interaction.guild, interaction.client, user_id_str))
                search_name = f"ID/User: {input_val}"

        from warning_tracker_module import get_user_warnings
        past_warnings = await get_user_warnings(interaction.guild_id, targets)
        if not past_warnings:
            return await interaction.response.send_message(f"No warnings found for '{search_name}'.", ephemeral=True)

        embed = discord.Embed(title=f"Warning History: {search_name}", color=discord.Color.blue())
        for r in past_warnings:
            ts = r.get("timestamp", "").split("T")[0]
            accounts = ", ".join(f"{acc['platform']}:{acc['display_name']}" for acc in r.get("linked_accounts", []))
            val = (
                f"**Date**: {ts}\n"
                f"**Points**: {r.get('points')} ({r.get('severity')})\n"
                f"**Accounts**: {accounts}\n"
                f"**Details**: {r.get('details')}\n"
                f"**Action**: {r.get('action_taken')}"
            )
            embed.add_field(name=f"Warning ID: {r.get('id')[:8]}...", value=val, inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ModDeleteWarningModal(ui.Modal, title="Delete Warning"):
    warning_id_input = ui.TextInput(label="Warning ID", placeholder="Enter the exact Warning ID", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        if not is_mod(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        warning_id = self.warning_id_input.value.strip()
        from warning_tracker_module import load_warnings, delete_warning_record, handle_warning_deletion_log
        db = await load_warnings()
        guild_str = str(interaction.guild_id)
        record = None
        if guild_str in db:
            for r in db[guild_str]:
                if r.get("id") == warning_id:
                    record = r
                    break
        
        if not record:
            return await interaction.response.send_message(f"Warning ID '{warning_id}' not found.", ephemeral=True)

        success, msg = await delete_warning_record(interaction.guild_id, warning_id)
        if success:
            await handle_warning_deletion_log(interaction, record)
        await interaction.response.send_message(msg, ephemeral=True)

class ModeratorDashboardView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Nebot Moderator Dashboard",
            description="Quick access to moderation tools. Select an action below.",
            color=discord.Color.red()
        )
        return embed

    @ui.button(label="Ban User", style=discord.ButtonStyle.danger, row=0)
    async def ban_user(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModBanModal())

    @ui.button(label="Kick User", style=discord.ButtonStyle.danger, row=0)
    async def kick_user(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModKickModal())

    @ui.button(label="Send Warning", style=discord.ButtonStyle.primary, row=1)
    async def send_warning(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        if not cfg.get("warning_tracker_enabled", False):
            return await interaction.response.send_message("The Warning Tracker module is disabled on this server.", ephemeral=True)
        await interaction.response.send_modal(ModSendWarningModal(self.guild_id))

    @ui.button(label="View Warnings", style=discord.ButtonStyle.secondary, row=1)
    async def view_warning(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        if not cfg.get("warning_tracker_enabled", False):
            return await interaction.response.send_message("The Warning Tracker module is disabled on this server.", ephemeral=True)
        await interaction.response.send_modal(ModViewWarningModal())

    @ui.button(label="Delete Warning", style=discord.ButtonStyle.secondary, row=1)
    async def delete_warning(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        if not cfg.get("warning_tracker_enabled", False):
            return await interaction.response.send_message("The Warning Tracker module is disabled on this server.", ephemeral=True)
        await interaction.response.send_modal(ModDeleteWarningModal())

class SendAsMessageModal(ui.Modal, title='Send as message'):
    content = ui.TextInput(label='Message content', style=discord.TextStyle.paragraph, placeholder='Type your message here...', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(self.content.value)
        await interaction.response.send_message("Message sent as Nebot", ephemeral=True)

class ChangeStatusModal(ui.Modal, title='Change status'):
    status_text = ui.TextInput(label='Status text', style=discord.TextStyle.short, placeholder='Type status here...', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        import os
        from configuration_module import set_bot_status
        new_status = self.status_text.value
        set_bot_status(new_status)
        await interaction.client.change_presence(activity=discord.Game(name=new_status))
        await interaction.response.send_message(f"Status changed to: `{new_status}`", ephemeral=True)


async def get_logs_channel(guild: discord.Guild, cfg: dict):
    # Configured global log channel
    ch_id = cfg.get("global_log_channel_id")
    if ch_id:
        ch = guild.get_channel(ch_id)
        if not ch:
            try:
                ch = await guild.fetch_channel(ch_id)
            except Exception:
                pass
        if ch:
            return ch

    # Configured warning log channel as fallback
    ch_id = cfg.get("warning_log_channel_id")
    if ch_id:
        ch = guild.get_channel(ch_id)
        if not ch:
            try:
                ch = await guild.fetch_channel(ch_id)
            except Exception:
                pass
        if ch:
            return ch

    # Search for a channel named "logs" or "log" or "mod-log" or "mod-logs"
    for name in ["logs", "log", "mod-log", "mod-logs"]:
        ch = discord.utils.get(guild.text_channels, name=name)
        if ch:
            return ch
    return None

class AnnouncementConfirmView(ui.View):
    def __init__(self, content: str, owner_id: int):
        super().__init__(timeout=120.0)
        self.content = content
        self.owner_id = owner_id
        self.confirmed = None

    @ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        self.confirmed = False
        self.stop()
        await interaction.response.send_message("Announcement cancelled.", ephemeral=True)

class NebuffDashboardView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Nebuff Owner Dashboard",
            description="Nebot Owner controls. Press the button below to send a message as the bot.",
            color=discord.Color.purple()
        )
        return embed

    @ui.button(label="Send as message", style=discord.ButtonStyle.primary)
    async def send_as_message(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        await interaction.response.send_modal(SendAsMessageModal())

    @ui.button(label="Change status", style=discord.ButtonStyle.secondary)
    async def change_status(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        await interaction.response.send_modal(ChangeStatusModal())

    @ui.button(label="Edit Recommended Filters", style=discord.ButtonStyle.secondary)
    async def edit_recommended_filters(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        view = NebuffRecommendedFiltersView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Bot Analytics", style=discord.ButtonStyle.primary)
    async def bot_analytics(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        view = NebuffBotAnalyticsView()
        embed = view.build_embed(interaction)
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Send global announcement", style=discord.ButtonStyle.danger)
    async def send_global_announcement(self, interaction: discord.Interaction, button: ui.Button):
        import asyncio
        import datetime
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        await interaction.response.send_message(
            "Please send the message you want to announce next in this channel. "
            "It will be deleted automatically and you'll be prompted for confirmation.",
            ephemeral=True
        )

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            announcement_msg = await interaction.client.wait_for('message', check=check, timeout=300.0)
        except asyncio.TimeoutError:
            return await interaction.followup.send("Announcement setup timed out.", ephemeral=True)

        try:
            await announcement_msg.delete()
        except Exception:
            pass

        content = announcement_msg.content
        total_servers = len(interaction.client.guilds)

        confirm_view = AnnouncementConfirmView(content, interaction.user.id)
        
        preview_embed = discord.Embed(
            title="Global Announcement Preview",
            description=content,
            color=discord.Color.purple()
        )
        preview_embed.set_footer(text=f"Total target servers: {total_servers}")

        confirm_msg = await interaction.followup.send(
            content=f"Are you sure you want this message to be published to {total_servers} servers right now?",
            embed=preview_embed,
            view=confirm_view,
            ephemeral=True
        )

        await confirm_view.wait()

        if confirm_view.confirmed:
            await interaction.followup.send("Publishing announcement to all servers...", ephemeral=True)
            
            success_count = 0
            for guild in interaction.client.guilds:
                cfg = get_guild_config(guild.id)
                log_ch = await get_logs_channel(guild, cfg)
                if log_ch:
                    try:
                        announcement_embed = discord.Embed(
                            title="Global Announcement",
                            description=content,
                            color=discord.Color.purple(),
                            timestamp=datetime.datetime.utcnow()
                        )
                        announcement_embed.set_footer(text="Nebot Global Announcement System")
                        await log_ch.send(embed=announcement_embed)
                        success_count += 1
                    except Exception:
                        pass

            await interaction.followup.send(
                f"Announcement successfully published to {success_count}/{total_servers} servers.",
                ephemeral=True
            )

def setup_admin_commands(tree: app_commands.CommandTree):
    @tree.command(name="config", description="Show current Ne-OS server configuration")
    async def slash_config(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        cfg = get_guild_config(interaction.guild_id)
        allowed_ch = cfg.get("channel_id")
        if allowed_ch and interaction.channel_id != allowed_ch:
            return await interaction.response.send_message(f"Please use <#{allowed_ch}>.", ephemeral=True)
        if not is_admin(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        ch_str = f"<#{cfg.get('channel_id')}>" if cfg.get('channel_id') else "any channel"
        role_str = f"<@&{cfg.get('admin_role_id')}>" if cfg.get('admin_role_id') else "None (Admins Only)"
        sh_chan_str = f"<#{cfg.get('shared_channel_id')}>" if cfg.get('shared_channel_id') else "None"
        priv_en = cfg.get("private_sessions_enabled", False)
        sh_en = cfg.get("shared_enabled", False)
        ne_os_en = cfg.get("ne_os_enabled", False)
        battle_en = cfg.get("battle_enabled", False)
        battle_hp = cfg.get("battle_default_hp", 500)
        battle_dmg = cfg.get("battle_damage_range", "0-100")
        battle_to = cfg.get("battle_timeout", 180)
        minesweeper_en = cfg.get("minesweeper_enabled", False)
        minesweeper_mines = cfg.get("minesweeper_default_mines", 4)
        warning_en = cfg.get("warning_tracker_enabled", False)
        warning_mode = cfg.get("warning_escalation_mode", "static")
        
        verification_en = cfg.get("verification_enabled", False)
        verification_ch = cfg.get("verification_channel_id")
        verification_ch_str = f"<#{verification_ch}>" if verification_ch else "Not Set"
        verification_timeout = cfg.get("verification_timeout", 0)
        verification_timeout_str = f"{verification_timeout}s" if verification_timeout else "Disabled"
        auto_roller_en = cfg.get("auto_roller_enabled", False)
        automod_en = cfg.get("automod_enabled", False)

        info = (
            f"{BOLD}{FG_CYAN}Nebot Configuration Overview{RESET}\n"
            f"{'NE-OS MODULE:':<20} {FG_GREEN if ne_os_en else FG_RED}{'[ENABLED]' if ne_os_en else '[DISABLED]'}{RESET}\n"
            f"{'BATTLE MODULE:':<20} {FG_GREEN if battle_en else FG_RED}{'[ENABLED]' if battle_en else '[DISABLED]'}{RESET}\n"
            f"{'MINESWEEPER MODULE:':<20} {FG_GREEN if minesweeper_en else FG_RED}{'[ENABLED]' if minesweeper_en else '[DISABLED]'}{RESET}\n"
            f"{'WARNING MODULE:':<20} {FG_GREEN if warning_en else FG_RED}{'[ENABLED]' if warning_en else '[DISABLED]'}{RESET}\n"
            f"{'VERIFICATION MODULE:':<20} {FG_GREEN if verification_en else FG_RED}{'[ENABLED]' if verification_en else '[DISABLED]'}{RESET}\n"
            f"{'AUTO-ROLLER MODULE:':<20} {FG_GREEN if auto_roller_en else FG_RED}{'[ENABLED]' if auto_roller_en else '[DISABLED]'}{RESET}\n"
            f"{'AUTOMOD MODULE:':<20} {FG_GREEN if automod_en else FG_RED}{'[ENABLED]' if automod_en else '[DISABLED]'}{RESET}\n"
            f"{'NEBUFF MODULE:':<20} {FG_GREEN if cfg.get('nebuff_module_enabled', False) else FG_RED}{'[ENABLED]' if cfg.get('nebuff_module_enabled', False) else '[DISABLED]'}{RESET}\n"
            f"{'Verification Chan:':<20} {FG_GREEN}{verification_ch_str}{RESET}\n"
            f"{'Verification T/O:':<20} {FG_GREEN}{verification_timeout_str}{RESET}\n"
            f"{'Warning Mode:':<20} {FG_GREEN}{warning_mode.upper()}{RESET}\n"
            f"{'Prefix:':<20} {FG_GREEN}{cfg.get('prefix', DEFAULT_PREFIX)}{RESET}\n"
            f"{'Trigger Word:':<20} {FG_GREEN}{cfg.get('cmd', DEFAULT_CMD)}{RESET}\n"
            f"{'Admin Channel:':<20} {FG_GREEN}{ch_str}{RESET}\n"
            f"{'Admin Role:':<20} {FG_GREEN}{role_str}{RESET}\n"
            f"{'Shared Channel:':<20} {FG_GREEN}{sh_chan_str}{RESET}\n"
            f"{'Private SESS:':<20} {FG_GREEN if priv_en else FG_RED}{'[ENABLED]' if priv_en else '[DISABLED]'}{RESET}\n"
            f"{'Shared Mode:':<20} {FG_GREEN if sh_en else FG_RED}{'[ENABLED]' if sh_en else '[DISABLED]'}{RESET}\n"
            f"{'Battle HP:':<20} {FG_GREEN}{battle_hp}{RESET}\n"
            f"{'Battle Dmg:':<20} {FG_GREEN}{battle_dmg}{RESET}\n"
            f"{'Battle T/O:':<20} {FG_GREEN}{battle_to}s{RESET}\n"
            f"{'Minesweeper Mines:':<20} {FG_GREEN}{minesweeper_mines}{RESET}\n"
            f"{'Session T/O:':<20} {FG_BRIGHT_BLACK}{SESSION_TIMEOUT_SECONDS}s{RESET}\n"
            f"{'History Cap:':<20} {FG_BRIGHT_BLACK}10 items{RESET}"
        )
        await interaction.response.send_message(ansi_block(info), ephemeral=True)

    @tree.command(name="set-prefix", description="Change the bot prefix")
    async def slash_set_prefix(interaction: discord.Interaction, prefix: str):
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg): return await interaction.response.send_message("Permission denied.", ephemeral=True)
        if len(prefix) > 5: return await interaction.response.send_message("Prefix too long (max 5 chars).", ephemeral=True)
        cfg["prefix"] = prefix
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Updated prefix to `{prefix}`")
        await interaction.response.send_message(ansi_block(f"{FG_GREEN}Prefix updated to '{prefix}'{RESET}"), ephemeral=True)

    @tree.command(name="set-channel", description="Restrict the bot to a specific channel")
    async def slash_set_channel(interaction: discord.Interaction, channel: discord.TextChannel = None):
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg): return await interaction.response.send_message("Permission denied.", ephemeral=True)
        cfg["channel_id"] = channel.id if channel else None
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Restricted Ne-OS to {channel.mention}" if channel else "Removed Ne-OS channel restriction")
        if channel: await interaction.response.send_message(ansi_block(f"{FG_GREEN}Ne-OS restricted to {channel.mention}{RESET}"), ephemeral=True)
        else: await interaction.response.send_message(ansi_block(f"{FG_GREEN}Ne-OS now works in any channel{RESET}"), ephemeral=True)

    @tree.command(name="set-admin-role", description="Set a role allowed to manage bot settings")
    async def slash_set_admin_role(interaction: discord.Interaction, role: discord.Role = None):
        cfg = get_guild_config(interaction.guild_id)
        if not interaction.user.guild_permissions.administrator: return await interaction.response.send_message("Only Server Administrators can change the admin role.", ephemeral=True)
        cfg["admin_role_id"] = role.id if role else None
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Updated Admin Role to @{role.name}" if role else "Removed Admin Role configuration")
        if role: await interaction.response.send_message(ansi_block(f"{FG_GREEN}Admin role updated to @{role.name}{RESET}"), ephemeral=True)
        else: await interaction.response.send_message(ansi_block(f"{FG_GREEN}Admin role removed. Defaulting to Server Admins only.{RESET}"), ephemeral=True)

    @tree.command(name="set-mod-role", description="Set a role allowed to issue warnings")
    async def slash_set_mod_role(interaction: discord.Interaction, role: discord.Role = None):
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg): return await interaction.response.send_message("Permission denied.", ephemeral=True)
        cfg["mod_role_id"] = role.id if role else None
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Updated Moderator Role to @{role.name}" if role else "Removed Moderator Role configuration")
        if role: await interaction.response.send_message(ansi_block(f"{FG_GREEN}Moderator role updated to @{role.name}{RESET}"), ephemeral=True)
        else: await interaction.response.send_message(ansi_block(f"{FG_GREEN}Moderator role removed. Defaulting to admins only.{RESET}"), ephemeral=True)

    @tree.command(name="set-cmd", description="Change the bot's trigger command word")
    async def slash_set_cmd(interaction: discord.Interaction, word: str):
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg): return await interaction.response.send_message("Permission denied.", ephemeral=True)
        word = word.lower().strip()
        if not word or len(word) > 16: return await interaction.response.send_message("Word must be 1-16 characters.", ephemeral=True)
        cfg["cmd"] = word
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Updated command word to `{word}`")
        await interaction.response.send_message(ansi_block(f"{FG_GREEN}Command word updated to '{word}'{RESET}"), ephemeral=True)

    @tree.command(name="set-shared-channel", description="Enable a shared prefixless session in a channel")
    async def slash_set_shared(interaction: discord.Interaction, channel: discord.TextChannel = None):
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg): return await interaction.response.send_message("Permission denied.", ephemeral=True)
        cfg["shared_channel_id"] = channel.id if channel else None
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Enabled Shared session in {channel.mention}" if channel else "Disabled Shared session channel")
        if channel: await interaction.response.send_message(ansi_block(f"{FG_GREEN}Shared session enabled in {channel.mention}.\nPrefix/trigger no longer required there.{RESET}"), ephemeral=True)
        else: await interaction.response.send_message(ansi_block(f"{FG_GREEN}Shared session disabled.{RESET}"), ephemeral=True)

    @tree.command(name="toggle-private-sessions", description="Enable or disable per-user private sessions")
    async def slash_toggle_private(interaction: discord.Interaction, enabled: bool):
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg): return await interaction.response.send_message("Permission denied.", ephemeral=True)
        cfg["private_sessions_enabled"] = enabled
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Toggled private sessions to `{'enabled' if enabled else 'disabled'}`")
        await interaction.response.send_message(ansi_block(f"{FG_GREEN}Private sessions are now {'enabled' if enabled else 'disabled'}.{RESET}"), ephemeral=True)

    @tree.command(name="toggle-shared-sessions", description="Enable or disable prefixless shared sessions")
    async def slash_toggle_shared(interaction: discord.Interaction, enabled: bool):
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg): return await interaction.response.send_message("Permission denied.", ephemeral=True)
        cfg["shared_enabled"] = enabled
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Toggled prefixless shared session mode to `{'enabled' if enabled else 'disabled'}`")
        await interaction.response.send_message(ansi_block(f"{FG_GREEN}Shared session mode is now {'enabled' if enabled else 'disabled'}.{RESET}"), ephemeral=True)

    @tree.command(name="admin", description="Nebot Administration Dashboard")
    async def slash_admin(interaction: discord.Interaction):
        if not interaction.guild: return await interaction.response.send_message("Server only command", ephemeral=True)
        if not is_admin(interaction.user, get_guild_config(interaction.guild_id)): return await interaction.response.send_message("Permission denied", ephemeral=True)
        view = ModuleSelectView(interaction.guild_id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @tree.command(name="dash", description="Nebot Dashboard")
    async def slash_dash(interaction: discord.Interaction):
        if not interaction.guild: return await interaction.response.send_message("Server only command", ephemeral=True)
        view = UserDashboardView(interaction.guild_id, interaction.user)
        embed = await view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @tree.command(name="mod", description="Nebot Moderator Dashboard")
    async def slash_mod(interaction: discord.Interaction):
        if not interaction.guild: return await interaction.response.send_message("Server only command", ephemeral=True)
        if not is_mod(interaction.user, get_guild_config(interaction.guild_id)): return await interaction.response.send_message("Permission denied", ephemeral=True)
        view = ModeratorDashboardView(interaction.guild_id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @tree.command(name="nebuff", description="Nebot Owner Dashboard")
    async def slash_nebuff(interaction: discord.Interaction):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        view = NebuffDashboardView()
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class NebuffBotAnalyticsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def build_embed(self, interaction: discord.Interaction) -> discord.Embed:
        from configuration_module import guild_configs
        current_servers = len(interaction.client.guilds)

        all_guild_ids = set()
        for guild in interaction.client.guilds:
            all_guild_ids.add(guild.id)
        for guild_id in guild_configs.keys():
            all_guild_ids.add(guild_id)

        total_invited = len(all_guild_ids)

        embed = discord.Embed(
            title="Bot Analytics",
            description="Overall Bot Server Metrics",
            color=discord.Color.purple()
        )
        embed.add_field(name="Current Servers", value=str(current_servers), inline=True)
        embed.add_field(name="Total Invited (All Time)", value=str(total_invited), inline=True)
        return embed

    @ui.button(label="Complete Server List", style=discord.ButtonStyle.primary)
    async def complete_server_list(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        lines = []
        for guild in interaction.client.guilds:
            invite_url = "None"
            try:
                invites = await guild.invites()
                if invites:
                    invite_url = invites[0].url
                else:
                    channels = guild.text_channels
                    if channels:
                        invite = await channels[0].create_invite(max_age=0, max_uses=0)
                        invite_url = invite.url
            except Exception:
                invite_url = "Cannot fetch/create invite"

            cfg = get_guild_config(guild.id)
            features = []
            if cfg.get("automod_enabled"): features.append("AutoMod")
            if cfg.get("verification_enabled"): features.append("Verification")
            if cfg.get("music_enabled"): features.append("Music")
            if cfg.get("warning_tracker_enabled"): features.append("WarningTracker")
            if cfg.get("battle_enabled"): features.append("Battle")
            if cfg.get("ne_os_enabled"): features.append("NeOS")
            if cfg.get("minesweeper_enabled"): features.append("Minesweeper")
            if cfg.get("auto_roller_enabled"): features.append("AutoRoller")
            if cfg.get("analytics_enabled"): features.append("ServerAnalytics")
            if cfg.get("vc_wr_enabled"): features.append("VCWR")
            if cfg.get("join_filter_enabled"): features.append("JoinFilter")
            if cfg.get("private_sessions_enabled"): features.append("PrivateSessions")
            if cfg.get("shared_enabled"): features.append("SharedSessions")
            if cfg.get("nebuff_module_enabled"): features.append("Nebuff")

            features_str = ", ".join(features) if features else "None"

            lines.append(f"Server: {guild.name} (ID: {guild.id})")
            lines.append(f"Invite: {invite_url}")
            lines.append(f"Features: {features_str}")
            lines.append("-" * 40)

        full_text = "\n".join(lines)
        if not full_text:
            full_text = "No servers found."

        if len(full_text) > 1900:
            import io
            file = discord.File(io.BytesIO(full_text.encode('utf-8')), filename="server_list.txt")
            await interaction.followup.send("Server list is too long, sending as file:", file=file, ephemeral=True)
        else:
            await interaction.followup.send(f"```\n{full_text}\n```", ephemeral=True)

    @ui.button(label="Back to Owner Dashboard", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        view = NebuffDashboardView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class NebuffRecommendedFiltersView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Nebuff Owner: Recommended Filters Manager",
            description="Manage the global recommended filters lists for AutoMod and Join Filtering.",
            color=discord.Color.purple()
        )
        return embed

    @ui.button(label="AutoMod Recommended", style=discord.ButtonStyle.primary)
    async def automod_recommended(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        view = ManageGlobalRecommendedAutoModFiltersView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Join Recommended", style=discord.ButtonStyle.primary)
    async def join_recommended(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        view = ManageGlobalRecommendedJoinFiltersView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Back to Owner Dashboard", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        owner_id_str = os.getenv("OWNER_ID")
        if not owner_id_str or not owner_id_str.strip().isdigit() or interaction.user.id != int(owner_id_str.strip()):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
        view = NebuffDashboardView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class GlobalRecommendedAutoModFilterSelectMenu(ui.Select):
    def __init__(self):
        recs = configuration_module.recommended_automod_filters
        
        options = []
        for idx, f in enumerate(recs[:25]):
            options.append(discord.SelectOption(
                label=f.get("name"),
                description=f"Action: {f.get('enforcement_action')} | KWs: {len(f.get('keywords', []))}",
                value=str(idx)
            ))
            
        if not options:
            options.append(discord.SelectOption(label="No filters configured", value="none"))
            super().__init__(placeholder="No filters available", options=options, disabled=True, row=0)
        else:
            super().__init__(placeholder="Select a global filter...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_index = int(self.values[0]) if self.values[0] != "none" else None
        await self.view.refresh(interaction)


class ManageGlobalRecommendedAutoModFiltersView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.selected_index = None
        self.add_item(GlobalRecommendedAutoModFilterSelectMenu())

    def build_embed(self) -> discord.Embed:
        recs = configuration_module.recommended_automod_filters
        
        embed = discord.Embed(
            title="Owner: Recommended AutoMod Filters",
            description="Manage global default templates shown to all servers.",
            color=discord.Color.purple()
        )
        
        selected_filter = None
        if self.selected_index is not None and 0 <= self.selected_index < len(recs):
            selected_filter = recs[self.selected_index]
                
        if selected_filter:
            action = selected_filter.get("enforcement_action", "Delete Message Only")
            if action == "Delete + Warn User":
                action += f" (Severity: {selected_filter.get('warning_severity', 'Low')})"
            elif action == "Delete + Direct Penalty":
                action += f" (Penalty: {selected_filter.get('direct_penalty', '1-Hour Timeout')})"
                
            from configuration_module import safe_join_items
            kws = safe_join_items([f"`{k}`" for k in selected_filter.get("keywords", [])])
            
            embed.add_field(name="Filter Name", value=selected_filter.get("name"), inline=True)
            embed.add_field(name="Default Action", value=action, inline=True)
            embed.add_field(name="Keywords", value=kws or "None", inline=False)
        else:
            embed.add_field(name="Details", value="Please select a recommended filter from the dropdown to edit it.", inline=False)
            
        return embed

    @ui.button(label="Edit Keywords", style=discord.ButtonStyle.secondary, row=1)
    async def edit_keywords(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
            
        recs = configuration_module.recommended_automod_filters
        selected = recs[self.selected_index]
        await interaction.response.send_modal(EditGlobalRecommendedAutoModFilterKeywordsModal(self.selected_index, selected.get("keywords", [])))

    @ui.button(label="Delete Filter", style=discord.ButtonStyle.danger, row=1)
    async def delete_filter(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
            
        recs = configuration_module.recommended_automod_filters
        recs.pop(self.selected_index)
        configuration_module.save_config()
        
        view = ManageGlobalRecommendedAutoModFiltersView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Edit Action", style=discord.ButtonStyle.secondary, row=2)
    async def edit_action(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
            
        view = EditGlobalRecommendedAutoModFilterActionView(self.selected_index)
        embed = discord.Embed(
            title="Edit Recommended Filter: Enforcement Action",
            description="Configure the default enforcement action.",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Create Filter", style=discord.ButtonStyle.success, row=2)
    async def create_filter(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreateGlobalRecommendedAutoModFilterModal())

    @ui.button(label="Back to Recommended Manager", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = NebuffRecommendedFiltersView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        view = ManageGlobalRecommendedAutoModFiltersView()
        view.selected_index = self.selected_index
        await interaction.response.edit_message(embed=embed, view=view)


class CreateGlobalRecommendedAutoModFilterModal(ui.Modal, title="Create Recommended AutoMod Filter"):
    filter_name = ui.TextInput(label="Filter Name", placeholder="e.g. Mass Caps", required=True)
    keywords = ui.TextInput(
        label="Keywords (comma-separated)",
        placeholder="Use r: for regex (e.g., r:[A-Z]{5,})",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.filter_name.value.strip()
        kws = [k.strip() for k in self.keywords.value.split(",") if k.strip()]
        
        view = GlobalRecommendedAutoModFilterActionSelectionView(name, kws)
        embed = discord.Embed(
            title="Create Recommended Filter: Action",
            description=f"Configure the default action to take when a message matches **{name}**.",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class GlobalRecommendedAutoModFilterActionSelectionView(ui.View):
    def __init__(self, name: str, keywords: list[str]):
        super().__init__(timeout=None)
        self.name = name
        self.keywords = keywords

    @ui.button(label="Delete Message Only", style=discord.ButtonStyle.primary)
    async def delete_only(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("Delete Message Only")
        await self.finish(interaction)

    @ui.button(label="Delete + Warn User", style=discord.ButtonStyle.secondary)
    async def delete_warn(self, interaction: discord.Interaction, button: ui.Button):
        view = GlobalRecommendedAutoModFilterSelectSeverityView(self.name, self.keywords)
        embed = discord.Embed(title="Create Recommended Filter: Severity", description="Select the default warning severity.", color=discord.Color.purple())
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Delete + Direct Penalty", style=discord.ButtonStyle.danger)
    async def delete_direct(self, interaction: discord.Interaction, button: ui.Button):
        view = GlobalRecommendedAutoModFilterSelectPenaltyView(self.name, self.keywords)
        embed = discord.Embed(title="Create Recommended Filter: Penalty", description="Select the default immediate penalty.", color=discord.Color.purple())
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Delete + Alert Mods", style=discord.ButtonStyle.secondary)
    async def delete_alert_mods(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("Delete + Alert Mods")
        await self.finish(interaction)

    def save_filter(self, action: str, severity: str = None, penalty: str = None):
        import uuid
        recs = configuration_module.recommended_automod_filters
        recs.append({
            "id": uuid.uuid4().hex,
            "name": self.name,
            "enabled": True,
            "keywords": self.keywords,
            "enforcement_action": action,
            "warning_severity": severity,
            "direct_penalty": penalty,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        })
        configuration_module.save_config()

    async def finish(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Recommended filter created successfully!", embed=None, view=None)


class GlobalRecommendedAutoModFilterSelectSeverityView(ui.View):
    def __init__(self, name: str, keywords: list[str]):
        super().__init__(timeout=None)
        self.name = name
        self.keywords = keywords

    @ui.button(label="Low Severity", style=discord.ButtonStyle.secondary)
    async def low_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("Low")
        await self.finish(interaction)

    @ui.button(label="Medium Severity", style=discord.ButtonStyle.primary)
    async def med_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("Medium")
        await self.finish(interaction)

    @ui.button(label="High Severity", style=discord.ButtonStyle.danger)
    async def high_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("High")
        await self.finish(interaction)

    def save_filter(self, severity: str):
        import uuid
        recs = configuration_module.recommended_automod_filters
        recs.append({
            "id": uuid.uuid4().hex,
            "name": self.name,
            "enabled": True,
            "keywords": self.keywords,
            "enforcement_action": "Delete + Warn User",
            "warning_severity": severity,
            "direct_penalty": None,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        })
        configuration_module.save_config()

    async def finish(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Recommended filter created successfully!", embed=None, view=None)


class GlobalRecommendedAutoModFilterSelectPenaltyView(ui.View):
    def __init__(self, name: str, keywords: list[str]):
        super().__init__(timeout=None)
        self.name = name
        self.keywords = keywords

    @ui.button(label="1-Hour Timeout", style=discord.ButtonStyle.secondary)
    async def timeout_penalty(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("1-Hour Timeout")
        await self.finish(interaction)

    @ui.button(label="Permanent Ban", style=discord.ButtonStyle.danger)
    async def ban_penalty(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("Permanent Ban")
        await self.finish(interaction)

    def save_filter(self, penalty: str):
        import uuid
        recs = configuration_module.recommended_automod_filters
        recs.append({
            "id": uuid.uuid4().hex,
            "name": self.name,
            "enabled": True,
            "keywords": self.keywords,
            "enforcement_action": "Delete + Direct Penalty",
            "warning_severity": None,
            "direct_penalty": penalty,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        })
        configuration_module.save_config()

    async def finish(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Recommended filter created successfully!", embed=None, view=None)


class EditGlobalRecommendedAutoModFilterKeywordsModal(ui.Modal, title="Edit Recommended Filter Keywords"):
    def __init__(self, index: int, current_kws: list[str]):
        super().__init__()
        self.index = index
        self.keywords_input = ui.TextInput(
            label="Keywords (comma-separated)",
            default=", ".join(current_kws),
            placeholder="Keywords/regex",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.keywords_input)

    async def on_submit(self, interaction: discord.Interaction):
        recs = configuration_module.recommended_automod_filters
        if 0 <= self.index < len(recs):
            recs[self.index]["keywords"] = [k.strip() for k in self.keywords_input.value.split(",") if k.strip()]
            configuration_module.save_config()
            
        view = ManageGlobalRecommendedAutoModFiltersView()
        view.selected_index = self.index
        embed = view.build_embed()
        await interaction.response.edit_message(content="Keywords updated successfully!", embed=embed, view=view)


class EditGlobalRecommendedAutoModFilterActionView(ui.View):
    def __init__(self, index: int):
        super().__init__(timeout=None)
        self.index = index

    @ui.button(label="Delete Message Only", style=discord.ButtonStyle.primary)
    async def delete_only(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action("Delete Message Only")
        await self.finish(interaction)

    @ui.button(label="Delete + Warn User", style=discord.ButtonStyle.secondary)
    async def delete_warn(self, interaction: discord.Interaction, button: ui.Button):
        view = EditGlobalRecommendedAutoModFilterSelectSeverityView(self.index)
        embed = discord.Embed(title="Edit Recommended Filter: Severity", description="Select the warning severity.", color=discord.Color.purple())
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Delete + Direct Penalty", style=discord.ButtonStyle.danger)
    async def delete_direct(self, interaction: discord.Interaction, button: ui.Button):
        view = EditGlobalRecommendedAutoModFilterSelectPenaltyView(self.index)
        embed = discord.Embed(title="Edit Recommended Filter: Penalty", description="Select the direct penalty.", color=discord.Color.purple())
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Delete + Alert Mods", style=discord.ButtonStyle.secondary)
    async def delete_alert_mods(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action("Delete + Alert Mods")
        await self.finish(interaction)

    def update_action(self, action: str, severity: str = None, penalty: str = None):
        recs = configuration_module.recommended_automod_filters
        if 0 <= self.index < len(recs):
            recs[self.index]["enforcement_action"] = action
            recs[self.index]["warning_severity"] = severity
            recs[self.index]["direct_penalty"] = penalty
            configuration_module.save_config()

    async def finish(self, interaction: discord.Interaction):
        view = ManageGlobalRecommendedAutoModFiltersView()
        view.selected_index = self.index
        embed = view.build_embed()
        await interaction.response.edit_message(content="Action updated successfully!", embed=embed, view=view)


class EditGlobalRecommendedAutoModFilterSelectSeverityView(ui.View):
    def __init__(self, index: int):
        super().__init__(timeout=None)
        self.index = index

    @ui.button(label="Low Severity", style=discord.ButtonStyle.secondary)
    async def low_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.update_severity("Low")
        await self.finish(interaction)

    @ui.button(label="Medium Severity", style=discord.ButtonStyle.primary)
    async def med_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.update_severity("Medium")
        await self.finish(interaction)

    @ui.button(label="High Severity", style=discord.ButtonStyle.danger)
    async def high_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.update_severity("High")
        await self.finish(interaction)

    def update_severity(self, severity: str):
        recs = configuration_module.recommended_automod_filters
        if 0 <= self.index < len(recs):
            recs[self.index]["enforcement_action"] = "Delete + Warn User"
            recs[self.index]["warning_severity"] = severity
            recs[self.index]["direct_penalty"] = None
            configuration_module.save_config()

    async def finish(self, interaction: discord.Interaction):
        view = ManageGlobalRecommendedAutoModFiltersView()
        view.selected_index = self.index
        embed = view.build_embed()
        await interaction.response.edit_message(content="Severity updated successfully!", embed=embed, view=view)


class EditGlobalRecommendedAutoModFilterSelectPenaltyView(ui.View):
    def __init__(self, index: int):
        super().__init__(timeout=None)
        self.index = index

    @ui.button(label="1-Hour Timeout", style=discord.ButtonStyle.secondary)
    async def timeout_penalty(self, interaction: discord.Interaction, button: ui.Button):
        self.update_penalty("1-Hour Timeout")
        await self.finish(interaction)

    @ui.button(label="Permanent Ban", style=discord.ButtonStyle.danger)
    async def ban_penalty(self, interaction: discord.Interaction, button: ui.Button):
        self.update_penalty("Permanent Ban")
        await self.finish(interaction)

    def update_penalty(self, penalty: str):
        recs = configuration_module.recommended_automod_filters
        if 0 <= self.index < len(recs):
            recs[self.index]["enforcement_action"] = "Delete + Direct Penalty"
            recs[self.index]["warning_severity"] = None
            recs[self.index]["direct_penalty"] = penalty
            configuration_module.save_config()

    async def finish(self, interaction: discord.Interaction):
        view = ManageGlobalRecommendedAutoModFiltersView()
        view.selected_index = self.index
        embed = view.build_embed()
        await interaction.response.edit_message(content="Penalty updated successfully!", embed=embed, view=view)


class GlobalRecommendedJoinFilterSelectMenu(ui.Select):
    def __init__(self):
        recs = configuration_module.recommended_join_filters
        
        options = []
        for idx, f in enumerate(recs[:25]):
            options.append(discord.SelectOption(
                label=f.get("name"),
                description=f"Action: {f.get('enforcement_action').capitalize()} | KWs: {len(f.get('keywords', []))}",
                value=str(idx)
            ))
            
        if not options:
            options.append(discord.SelectOption(label="No filters configured", value="none"))
            super().__init__(placeholder="No filters available", options=options, disabled=True, row=0)
        else:
            super().__init__(placeholder="Select a global join filter...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_index = int(self.values[0]) if self.values[0] != "none" else None
        await self.view.refresh(interaction)


class ManageGlobalRecommendedJoinFiltersView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.selected_index = None
        self.add_item(GlobalRecommendedJoinFilterSelectMenu())

    def build_embed(self) -> discord.Embed:
        recs = configuration_module.recommended_join_filters
        
        embed = discord.Embed(
            title="Owner: Recommended Join Filters",
            description="Manage global default join templates shown to all servers.",
            color=discord.Color.purple()
        )
        
        selected_filter = None
        if self.selected_index is not None and 0 <= self.selected_index < len(recs):
            selected_filter = recs[self.selected_index]
                
        if selected_filter:
            action = selected_filter.get("enforcement_action", "quarantine").capitalize()
            from configuration_module import safe_join_items
            kws = safe_join_items([f"`{k}`" for k in selected_filter.get("keywords", [])])
            
            embed.add_field(name="Filter Name", value=selected_filter.get("name"), inline=True)
            embed.add_field(name="Default Action", value=action, inline=True)
            embed.add_field(name="Keywords", value=kws or "None", inline=False)
        else:
            embed.add_field(name="Details", value="Please select a recommended join filter from the dropdown to edit it.", inline=False)
            
        return embed

    @ui.button(label="Edit Keywords", style=discord.ButtonStyle.secondary, row=1)
    async def edit_keywords(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
            
        recs = configuration_module.recommended_join_filters
        selected = recs[self.selected_index]
        await interaction.response.send_modal(EditGlobalRecommendedJoinFilterKeywordsModal(self.selected_index, selected.get("keywords", [])))

    @ui.button(label="Delete Filter", style=discord.ButtonStyle.danger, row=1)
    async def delete_filter(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
            
        recs = configuration_module.recommended_join_filters
        recs.pop(self.selected_index)
        configuration_module.save_config()
        
        view = ManageGlobalRecommendedJoinFiltersView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Edit Action", style=discord.ButtonStyle.secondary, row=2)
    async def edit_action(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
            
        view = EditGlobalRecommendedJoinFilterActionView(self.selected_index)
        embed = discord.Embed(
            title="Edit Recommended Join Filter: Action",
            description="Configure the default enforcement action.",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Create Filter", style=discord.ButtonStyle.success, row=2)
    async def create_filter(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreateGlobalRecommendedJoinFilterModal())

    @ui.button(label="Back to Recommended Manager", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = NebuffRecommendedFiltersView()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        view = ManageGlobalRecommendedJoinFiltersView()
        view.selected_index = self.selected_index
        await interaction.response.edit_message(embed=embed, view=view)


class CreateGlobalRecommendedJoinFilterModal(ui.Modal, title="Create Recommended Join Filter"):
    filter_name = ui.TextInput(label="Filter Name", placeholder="e.g. Bot Pattern", required=True)
    keywords = ui.TextInput(
        label="Keywords (comma-separated)",
        placeholder="Use r: for regex (e.g., r:alt_.*)",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.filter_name.value.strip()
        kws = [k.strip() for k in self.keywords.value.split(",") if k.strip()]
        
        view = GlobalRecommendedJoinFilterActionSelectionView(name, kws)
        embed = discord.Embed(
            title="Create Recommended Join Filter: Action",
            description=f"Configure the default enforcement action to take when a joining user matches **{name}**.",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class GlobalRecommendedJoinFilterActionSelectionView(ui.View):
    def __init__(self, name: str, keywords: list[str]):
        super().__init__(timeout=None)
        self.name = name
        self.keywords = keywords

    @ui.button(label="Quarantine", style=discord.ButtonStyle.primary)
    async def quarantine_action(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("quarantine")
        await self.finish(interaction)

    @ui.button(label="Kick", style=discord.ButtonStyle.secondary)
    async def kick_action(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("kick")
        await self.finish(interaction)

    @ui.button(label="Ban", style=discord.ButtonStyle.danger)
    async def ban_action(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter("ban")
        await self.finish(interaction)

    def save_filter(self, action: str):
        import uuid
        recs = configuration_module.recommended_join_filters
        recs.append({
            "id": uuid.uuid4().hex,
            "name": self.name,
            "enabled": True,
            "keywords": self.keywords,
            "enforcement_action": action
        })
        configuration_module.save_config()

    async def finish(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Recommended join filter created successfully!", embed=None, view=None)


class EditGlobalRecommendedJoinFilterKeywordsModal(ui.Modal, title="Edit Recommended Join Filter Keywords"):
    def __init__(self, index: int, current_kws: list[str]):
        super().__init__()
        self.index = index
        self.keywords_input = ui.TextInput(
            label="Keywords (comma-separated)",
            default=", ".join(current_kws),
            placeholder="Keywords/regex",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.keywords_input)

    async def on_submit(self, interaction: discord.Interaction):
        recs = configuration_module.recommended_join_filters
        if 0 <= self.index < len(recs):
            recs[self.index]["keywords"] = [k.strip() for k in self.keywords_input.value.split(",") if k.strip()]
            configuration_module.save_config()
            
        view = ManageGlobalRecommendedJoinFiltersView()
        view.selected_index = self.index
        embed = view.build_embed()
        await interaction.response.edit_message(content="Keywords updated successfully!", embed=embed, view=view)


class EditGlobalRecommendedJoinFilterActionView(ui.View):
    def __init__(self, index: int):
        super().__init__(timeout=None)
        self.index = index

    @ui.button(label="Quarantine", style=discord.ButtonStyle.primary)
    async def quarantine_action(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action("quarantine")
        await self.finish(interaction)

    @ui.button(label="Kick", style=discord.ButtonStyle.secondary)
    async def kick_action(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action("kick")
        await self.finish(interaction)

    @ui.button(label="Ban", style=discord.ButtonStyle.danger)
    async def ban_action(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action("ban")
        await self.finish(interaction)

    def update_action(self, action: str):
        recs = configuration_module.recommended_join_filters
        if 0 <= self.index < len(recs):
            recs[self.index]["enforcement_action"] = action
            configuration_module.save_config()

    async def finish(self, interaction: discord.Interaction):
        view = ManageGlobalRecommendedJoinFiltersView()
        view.selected_index = self.index
        embed = view.build_embed()
        await interaction.response.edit_message(content="Action updated successfully!", embed=embed, view=view)