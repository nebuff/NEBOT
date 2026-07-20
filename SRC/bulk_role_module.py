import discord
from discord import ui
import asyncio
from configuration_module import get_guild_config, refresh_interaction, log_setting_change_task

active_bulk_role_operations = {}

async def run_bulk_role_task(guild: discord.Guild, target_role: discord.Role, operation: str, filter_type: str, filter_role: discord.Role = None, filter_channel: discord.TextChannel = None, notify_channel: discord.TextChannel = None, started_by: discord.Member = None):
    guild_id = guild.id
    active_bulk_role_operations[guild_id] = {
        "status": "processing",
        "processed": 0,
        "applied": 0,
        "cancel": False,
        "total": guild.member_count or len(guild.members),
        "target_role_name": target_role.name,
        "operation": operation,
        "filter_type": filter_type
    }
    
    status_data = active_bulk_role_operations[guild_id]
    
    if notify_channel:
        start_embed = discord.Embed(
            title=" Bulk Role Operation Started",
            description=f"Running **{operation.upper()}** on role {target_role.mention}.",
            color=discord.Color.orange()
        )
        f_val = "None"
        if filter_type == "has_role" and filter_role:
            f_val = f"Has role: {filter_role.name}"
        elif filter_type == "missing_role" and filter_role:
            f_val = f"Missing role: {filter_role.name}"
        elif filter_type == "channel_allowed" and filter_channel:
            f_val = f"Allowed in channel: {filter_channel.mention}"
        else:
            f_val = filter_type.upper()
            
        start_embed.add_field(name="Filter Criteria", value=f_val, inline=True)
        start_embed.add_field(name="Started By", value=started_by.mention if started_by else "System", inline=True)
        try:
            await notify_channel.send(embed=start_embed)
        except Exception:
            pass

    try:
        if not guild.chunked or len(guild.members) < guild.member_count:
            try:
                await guild.chunk()
            except Exception:
                pass
                
        members = list(guild.members)
        status_data["total"] = len(members)
        
        bot_member = guild.me
        if not bot_member.guild_permissions.manage_roles:
            status_data["status"] = "failed"
            status_data["error"] = "Bot lacks Manage Roles permission."
            if notify_channel:
                await notify_channel.send(" **Bulk Role Operation Failed**: Bot lacks Manage Roles permission.")
            return
            
        if target_role.position >= bot_member.top_role.position:
            status_data["status"] = "failed"
            status_data["error"] = "Target role is above the bot's hierarchy."
            if notify_channel:
                await notify_channel.send(f" **Bulk Role Operation Failed**: Target role **{target_role.name}** is above bot's highest role in hierarchy.")
            return

        for member in members:
            if status_data["cancel"]:
                status_data["status"] = "cancelled"
                if notify_channel:
                    await notify_channel.send(f"️ **Bulk Role Operation Cancelled** by user. Processed: {status_data['processed']}, changes: {status_data['applied']}.")
                return

            status_data["processed"] += 1
            
            matches = False
            if filter_type == "all":
                matches = True
            elif filter_type == "bots":
                matches = member.bot
            elif filter_type == "humans":
                matches = not member.bot
            elif filter_type == "has_role":
                if filter_role:
                    matches = member.get_role(filter_role.id) is not None
            elif filter_type == "missing_role":
                if filter_role:
                    matches = member.get_role(filter_role.id) is None
            elif filter_type == "channel_allowed":
                if filter_channel:
                    perms = filter_channel.permissions_for(member)
                    matches = perms.read_messages or perms.view_channel

            if not matches:
                continue

            has_role = member.get_role(target_role.id) is not None
            needs_action = False
            
            if operation == "assign" and not has_role:
                needs_action = True
            elif operation == "remove" and has_role:
                needs_action = True

            if needs_action:
                try:
                    if operation == "assign":
                        await member.add_roles(target_role, reason=f"Bulk Role assignment by {started_by.mention if hasattr(started_by, 'mention') else started_by}")
                    else:
                        await member.remove_roles(target_role, reason=f"Bulk Role removal by {started_by.mention if hasattr(started_by, 'mention') else started_by}")
                    status_data["applied"] += 1
                    await asyncio.sleep(0.1)
                except discord.Forbidden:
                    pass
                except Exception:
                    pass

        status_data["status"] = "completed"
        if notify_channel:
            done_embed = discord.Embed(
                title=" Bulk Role Operation Completed",
                color=discord.Color.green()
            )
            done_embed.add_field(name="Operation", value=operation.upper(), inline=True)
            done_embed.add_field(name="Target Role", value=target_role.name, inline=True)
            done_embed.add_field(name="Processed", value=f"{status_data['processed']}/{status_data['total']}", inline=True)
            done_embed.add_field(name="Changes Made", value=str(status_data["applied"]), inline=True)
            try:
                await notify_channel.send(embed=done_embed)
            except Exception:
                pass
                
    except Exception as ex:
        status_data["status"] = "failed"
        status_data["error"] = str(ex)
        if notify_channel:
            try:
                await notify_channel.send(f" **Bulk Role Operation Failed**: {ex}")
            except Exception:
                pass

class BulkTargetRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Select Target Role...", min_values=1, max_values=1, row=1)
    async def callback(self, interaction: discord.Interaction):
        self.view.target_role = self.values[0]
        await interaction.response.defer()

class BulkFilterRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Select Filter Role...", min_values=1, max_values=1, row=2)
    async def callback(self, interaction: discord.Interaction):
        self.view.filter_role = self.values[0]
        await interaction.response.defer()

class BulkFilterChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Select Filter Channel...", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, row=2)
    async def callback(self, interaction: discord.Interaction):
        self.view.filter_channel = self.values[0]
        await interaction.response.defer()

class BulkNotifyChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Select Notification Channel...", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, row=3)
    async def callback(self, interaction: discord.Interaction):
        self.view.notify_channel = self.values[0]
        await interaction.response.defer()

class BulkFilterTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Everyone (All)", value="all"),
            discord.SelectOption(label="Only Bots", value="bots"),
            discord.SelectOption(label="Only Humans", value="humans"),
            discord.SelectOption(label="Has Specific Role", value="has_role"),
            discord.SelectOption(label="Missing Specific Role", value="missing_role"),
            discord.SelectOption(label="Allowed in Channel", value="channel_allowed")
        ]
        super().__init__(placeholder="Select Filter Type...", options=options, min_values=1, max_values=1, row=4)
        
    async def callback(self, interaction: discord.Interaction):
        self.view.filter_type = self.values[0]
        self.view.filter_role = None
        self.view.filter_channel = None
        await self.view.refresh_view(interaction)

class BulkRoleDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
        self.target_role = None
        self.operation = "assign"
        self.filter_type = "all"
        self.filter_role = None
        self.filter_channel = None
        self.notify_channel = None
        
        self.setup_items()
        
    def setup_items(self):
        self.clear_items()
        
        self.add_item(ui.Button(label=f"Op: {self.operation.upper()}", style=discord.ButtonStyle.primary, custom_id="bulk_toggle_op", row=0))
        self.add_item(ui.Button(label="Start Job", style=discord.ButtonStyle.success, custom_id="bulk_start", row=0))
        self.add_item(ui.Button(label="Cancel Job", style=discord.ButtonStyle.danger, custom_id="bulk_cancel", row=0))
        self.add_item(ui.Button(label="Back to Tools", style=discord.ButtonStyle.secondary, custom_id="bulk_back", row=0))
        
        self.add_item(BulkTargetRoleSelect())
        
        if self.filter_type in ["has_role", "missing_role"]:
            self.add_item(BulkFilterRoleSelect())
        elif self.filter_type == "channel_allowed":
            self.add_item(BulkFilterChannelSelect())
            
        self.add_item(BulkNotifyChannelSelect())
        self.add_item(BulkFilterTypeSelect())

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="️ Bulk Role Manager",
            description="Perform bulk role assignments or removals based on various filters.",
            color=discord.Color.dark_teal()
        )
        
        embed.add_field(name="Operation", value=self.operation.upper(), inline=True)
        embed.add_field(name="Target Role", value=self.target_role.mention if self.target_role else "None Selected", inline=True)
        embed.add_field(name="Filter Type", value=self.filter_type.upper(), inline=True)
        
        f_val = "None Required"
        if self.filter_type in ["has_role", "missing_role"] and self.filter_role:
            f_val = f"Role: {self.filter_role.name}"
        elif self.filter_type == "channel_allowed" and self.filter_channel:
            f_val = f"Channel: <#{self.filter_channel.id}>"
        embed.add_field(name="Filter Value", value=f_val, inline=True)
        
        embed.add_field(name="Notification Channel", value=f"<#{self.notify_channel.id}>" if self.notify_channel else "None Selected", inline=True)
        
        status_str = "Idle"
        active_job = active_bulk_role_operations.get(self.guild_id)
        if active_job:
            status_str = f"**{active_job['status'].upper()}**\n• Scanned: {active_job['processed']}/{active_job['total']}\n• Changes: {active_job['applied']}"
        embed.add_field(name="Active Job Status", value=status_str, inline=False)
        
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data.get("custom_id")
        if custom_id == "bulk_toggle_op":
            self.operation = "remove" if self.operation == "assign" else "assign"
            await self.refresh_view(interaction)
            return False
        elif custom_id == "bulk_back":
            from admin_ui_module import ToolsView
            view = ToolsView(self.guild_id)
            embed = view.build_embed()
            await interaction.response.edit_message(content=None, embed=embed, view=view)
            return False
        elif custom_id == "bulk_cancel":
            active_job = active_bulk_role_operations.get(self.guild_id)
            if active_job and active_job["status"] == "processing":
                active_job["cancel"] = True
                await interaction.response.send_message("Cancellation requested.", ephemeral=True)
            else:
                await interaction.response.send_message("No active bulk role operation running.", ephemeral=True)
            return False
        elif custom_id == "bulk_start":
            active_job = active_bulk_role_operations.get(self.guild_id)
            if active_job and active_job["status"] == "processing":
                await interaction.response.send_message("An operation is already in progress on this server.", ephemeral=True)
                return False
                
            if not self.target_role:
                await interaction.response.send_message("Please select a target role first.", ephemeral=True)
                return False
                
            if not self.notify_channel:
                await interaction.response.send_message("Please select a notification channel.", ephemeral=True)
                return False
                
            if self.filter_type in ["has_role", "missing_role"] and not self.filter_role:
                await interaction.response.send_message("Please select a filter role.", ephemeral=True)
                return False
                
            if self.filter_type == "channel_allowed" and not self.filter_channel:
                await interaction.response.send_message("Please select a filter channel.", ephemeral=True)
                return False
                
            guild = interaction.guild
            target_role = guild.get_role(self.target_role.id)
            filter_role = guild.get_role(self.filter_role.id) if self.filter_role else None
            filter_channel = guild.get_channel(self.filter_channel.id) if self.filter_channel else None
            notify_channel = guild.get_channel(self.notify_channel.id)
            
            asyncio.create_task(run_bulk_role_task(
                guild=guild,
                target_role=target_role,
                operation=self.operation,
                filter_type=self.filter_type,
                filter_role=filter_role,
                filter_channel=filter_channel,
                notify_channel=notify_channel,
                started_by=interaction.user
            ))
            
            log_setting_change_task(interaction.guild, interaction.user, f"Started bulk role {self.operation} for role {target_role.name} (filter: {self.filter_type})")
            await interaction.response.send_message("Bulk role operation started in the background. Check your notification channel for alerts.", ephemeral=True)
            await self.refresh_view(None, interaction)
            return False
            
        return True

    async def refresh_view(self, interaction: discord.Interaction = None, fallback_interaction: discord.Interaction = None):
        self.setup_items()
        embed = self.build_embed()
        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        elif fallback_interaction:
            await fallback_interaction.followup.edit_message(fallback_interaction.message.id, embed=embed, view=self)
