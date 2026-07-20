import discord
from discord import ui
from configuration_module import get_guild_config, save_config, safe_join_items

class AutoRollerRolesSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Auto-Roller Roles...", min_values=1, max_values=10, row=1)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        roles = self.values
        cfg = get_guild_config(self.guild_id)
        cfg["auto_roller_role_ids"] = [r.id for r in roles]
        cfg["auto_roller_role_id"] = roles[0].id if roles else None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Auto-Roller roles to: {', '.join(r.name for r in roles)}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message("Auto-roller roles configured successfully.", ephemeral=True)

class AutoRollerConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(AutoRollerRolesSelect(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        enabled = cfg.get("auto_roller_enabled", False)
        
        role_ids = cfg.get("auto_roller_role_ids", [])
        single_role = cfg.get("auto_roller_role_id")
        if single_role and single_role not in role_ids:
            role_ids = [single_role] + role_ids
            
        roles_str = safe_join_items([f"<@&{rid}>" for rid in role_ids])

        embed = discord.Embed(
            title="Nebot Module: Auto-Roller Configuration",
            description=(
                "Configure roles that are automatically granted to users when they join the server.\n\n"
                "**Owner Setup Instructions:**\n"
                "• Select the target role(s) to grant automatically from the dropdown below.\n"
                "• The bot must have the `Manage Roles` permission, and its top role must be positioned above the configured auto-roller roles."
            ),
            color=discord.Color.teal()
        )
        embed.add_field(name="Status", value="[ENABLED]" if enabled else "[DISABLED]", inline=True)
        embed.add_field(name="Auto-Roller Roles", value=roles_str, inline=True)
        return embed

    @ui.button(label="Toggle Auto-Roller", style=discord.ButtonStyle.primary, row=0)
    async def toggle_auto_roller(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["auto_roller_enabled"] = not cfg.get("auto_roller_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Auto-Roller module state to `{'enabled' if cfg['auto_roller_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Clear Auto-Roller Roles", style=discord.ButtonStyle.secondary, row=0)
    async def clear_roles(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["auto_roller_role_ids"] = []
        cfg["auto_roller_role_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Auto-Roller roles")
        await self.refresh(interaction)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        from admin_ui_module import ModuleSelectView
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)
