import os
import json
import asyncio
import datetime
import discord
from discord import app_commands, ui
from configuration_module import get_guild_config, save_config, is_mod

db_lock = asyncio.Lock()




async def load_analytics_records() -> dict:
    from db_service import get_db_connection
    try:
        def _read():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM server_analytics;")
            rows = cursor.fetchall()
            records = {}
            for r in rows:
                g_str = str(r["guild_id"])
                records[g_str] = {
                    "messages": json.loads(r["messages"]) if r["messages"] else {},
                    "churn": json.loads(r["churn"]) if r["churn"] else [],
                    "voice": json.loads(r["voice"]) if r["voice"] else []
                }
            return records
        return await asyncio.to_thread(_read)
    except Exception as e:
        print(f"Error loading analytics records: {e}")
        return {}

async def save_analytics_records(records: dict):
    from db_service import get_db_connection
    try:
        def _write():
            conn = get_db_connection()
            cursor = conn.cursor()
            for g_str, data in records.items():
                guild_id = int(g_str)
                cursor.execute(
                    "INSERT OR REPLACE INTO server_analytics (guild_id, messages, churn, voice) VALUES (?, ?, ?, ?)",
                    (
                        guild_id,
                        json.dumps(data.get("messages", {})),
                        json.dumps(data.get("churn", [])),
                        json.dumps(data.get("voice", []))
                    )
                )
            conn.commit()
        await asyncio.to_thread(_write)
    except Exception as e:
        print(f"Error saving analytics records: {e}")

async def clean_old_records(records: dict, guild_id: str):
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    cutoff_ts = cutoff.timestamp()
    
    guild_data = records.get(guild_id)
    if not guild_data:
        return
    
    # Clean message velocity hour buckets
    if "messages" in guild_data:
        cleaned_messages = {}
        for ch_id, hours in guild_data["messages"].items():
            cleaned_hours = {}
            for hr_str, count in hours.items():
                try:
                    dt = datetime.datetime.fromisoformat(hr_str.replace("Z", "+00:00"))
                    if dt.replace(tzinfo=None) >= cutoff:
                        cleaned_hours[hr_str] = count
                except Exception:
                    pass
            if cleaned_hours:
                cleaned_messages[ch_id] = cleaned_hours
        guild_data["messages"] = cleaned_messages
        
    # Clean member churn
    if "churn" in guild_data:
        guild_data["churn"] = [
            event for event in guild_data["churn"]
            if event.get("timestamp", 0) >= cutoff_ts
        ]
        
    # Clean voice concurrency
    if "voice" in guild_data:
        guild_data["voice"] = [
            pt for pt in guild_data["voice"]
            if pt.get("timestamp", 0) >= cutoff_ts
        ]

async def handle_message_velocity(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    guild_id = message.guild.id
    cfg = get_guild_config(guild_id)
    if not cfg.get("analytics_enabled", False):
        return
    excluded = cfg.get("analytics_excluded_channels", [])
    if message.channel.id in excluded:
        return
    
    now = datetime.datetime.utcnow()
    hour_str = now.strftime("%Y-%m-%dT%H:00:00Z")
    
    async with db_lock:
        records = await load_analytics_records()
        g_str = str(guild_id)
        if g_str not in records:
            records[g_str] = {}
        if "messages" not in records[g_str]:
            records[g_str]["messages"] = {}
        
        ch_str = str(message.channel.id)
        if ch_str not in records[g_str]["messages"]:
            records[g_str]["messages"][ch_str] = {}
        
        records[g_str]["messages"][ch_str][hour_str] = records[g_str]["messages"][ch_str].get(hour_str, 0) + 1
        
        await clean_old_records(records, g_str)
        await save_analytics_records(records)

async def handle_member_join(member: discord.Member):
    guild_id = member.guild.id
    cfg = get_guild_config(guild_id)
    if not cfg.get("analytics_enabled", False):
        return
    
    now = datetime.datetime.utcnow().timestamp()
    async with db_lock:
        records = await load_analytics_records()
        g_str = str(guild_id)
        if g_str not in records:
            records[g_str] = {}
        if "churn" not in records[g_str]:
            records[g_str]["churn"] = []
        
        records[g_str]["churn"].append({
            "event": "join",
            "user_id": member.id,
            "timestamp": now
        })
        await clean_old_records(records, g_str)
        await save_analytics_records(records)

async def handle_member_leave(member: discord.Member):
    guild_id = member.guild.id
    cfg = get_guild_config(guild_id)
    if not cfg.get("analytics_enabled", False):
        return
    
    now = datetime.datetime.utcnow().timestamp()
    async with db_lock:
        records = await load_analytics_records()
        g_str = str(guild_id)
        if g_str not in records:
            records[g_str] = {}
        if "churn" not in records[g_str]:
            records[g_str]["churn"] = []
        
        records[g_str]["churn"].append({
            "event": "leave",
            "user_id": member.id,
            "timestamp": now
        })
        await clean_old_records(records, g_str)
        await save_analytics_records(records)

async def handle_voice_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.bot:
        return
    guild = member.guild
    cfg = get_guild_config(guild.id)
    if not cfg.get("analytics_enabled", False):
        return
    if before.channel == after.channel:
        return
    
    voice_count = 0
    for vc in guild.voice_channels:
        for m in vc.members:
            if not m.bot:
                voice_count += 1
                
    now = datetime.datetime.utcnow().timestamp()
    async with db_lock:
        records = await load_analytics_records()
        g_str = str(guild.id)
        if g_str not in records:
            records[g_str] = {}
        if "voice" not in records[g_str]:
            records[g_str]["voice"] = []
            
        records[g_str]["voice"].append({
            "timestamp": now,
            "count": voice_count
        })
        await clean_old_records(records, g_str)
        await save_analytics_records(records)

class AnalyticsExcludedChannelsSelect(ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(
            placeholder="Select channels to exclude...",
            min_values=0,
            max_values=25,
            channel_types=[discord.ChannelType.text, discord.ChannelType.news, discord.ChannelType.voice],
            row=0
        )
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        selected_ids = [ch.id for ch in self.values] if self.values else []
        cfg["analytics_excluded_channels"] = selected_ids
        save_config()
        
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Updated Server Analytics excluded channels")
        
        view = self.view
        if hasattr(view, "refresh"):
            await view.refresh(interaction)
        else:
            await interaction.response.defer(ephemeral=True)

class AnalyticsConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        enabled = cfg.get("analytics_enabled", False)
        excluded = cfg.get("analytics_excluded_channels", [])
        
        embed = discord.Embed(
            title="Nebot Module: Server Analytics",
            description="Configure community health tracking parameters, data collection windows, and administrative privacy settings.",
            color=discord.Color.blue()
        )
        
        status_str = "[ENABLED]" if enabled else "[DISABLED]"
        ch_str = ", ".join([f"<#{cid}>" for cid in excluded]) if excluded else "None"
        
        embed.add_field(name="Status", value=status_str, inline=True)
        embed.add_field(name="Excluded Channels", value=ch_str, inline=False)
        return embed

    @ui.button(label="Toggle Analytics", style=discord.ButtonStyle.primary, row=0)
    async def toggle_analytics(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["analytics_enabled"] = not cfg.get("analytics_enabled", False)
        save_config()
        
        from configuration_module import log_setting_change_task
        log_setting_change_task(
            interaction.guild,
            interaction.user,
            f"Toggled Server Analytics module to {'enabled' if cfg['analytics_enabled'] else 'disabled'}"
        )
        await self.refresh(interaction)

    @ui.button(label="Exclude Channels", style=discord.ButtonStyle.secondary, row=0)
    async def exclude_channels(self, interaction: discord.Interaction, button: ui.Button):
        view = ui.View()
        select = AnalyticsExcludedChannelsSelect(self.guild_id)
        select.view = view

        async def cancel_callback(i: discord.Interaction):
            await self.refresh(i)

        cancel_btn = ui.Button(label="Back", style=discord.ButtonStyle.danger, row=1)
        cancel_btn.callback = cancel_callback

        view.add_item(select)
        view.add_item(cancel_btn)
        view.refresh = self.refresh

        await interaction.response.edit_message(view=view)

    @ui.button(label="Clear Historical Data", style=discord.ButtonStyle.danger, row=1)
    async def clear_historical_data(self, interaction: discord.Interaction, button: ui.Button):
        async with db_lock:
            records = await load_analytics_records()
            g_str = str(self.guild_id)
            if g_str in records:
                del records[g_str]
                await save_analytics_records(records)
                
        from configuration_module import log_setting_change_task
        log_setting_change_task(
            interaction.guild,
            interaction.user,
            "Cleared all historical analytics logs"
        )
        await self.refresh(interaction)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=1)
    async def back_to_modules(self, interaction: discord.Interaction, button: ui.Button):
        from admin_ui_module import ModuleSelectView
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

def setup_analytics_commands(tree: app_commands.CommandTree):
    @tree.command(name="analytics", description="View server activity analytics report")
    @app_commands.describe(window="The time window for the analytics report")
    @app_commands.choices(window=[
        app_commands.Choice(name="Last 24 Hours", value="24h"),
        app_commands.Choice(name="Last 7 Days", value="7d")
    ])
    async def slash_analytics(interaction: discord.Interaction, window: str = "24h"):
        if not interaction.guild:
            return await interaction.response.send_message("Server only command", ephemeral=True)
            
        cfg = get_guild_config(interaction.guild_id)
        if not is_mod(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild_id
        g_str = str(guild_id)
        records = await load_analytics_records()
        guild_data = records.get(g_str, {})
        
        now = datetime.datetime.utcnow()
        if window == "24h":
            cutoff = now - datetime.timedelta(hours=24)
        else:
            cutoff = now - datetime.timedelta(days=7)
            
        cutoff_ts = cutoff.timestamp()
        
        # Chat activity
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
            
        # Member churn
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
        
        # Voice concurrency
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
            title=f"Server Analytics Report for {interaction.guild.name}",
            description="Activity metrics and user churn trends over the selected observation window.",
            color=discord.Color.blue()
        )
        
        chat_val = (
            f"Total Messages Processed: {total_messages}\n"
            f"Peak Message Hour: {peak_hour_formatted} with {peak_count} messages\n"
            f"Most Active Text Channel: {most_active_channel_str}"
        )
        embed.add_field(name="Chat Activity Metrics", value=chat_val, inline=False)
        
        churn_val = (
            f"Members Joined: {joins}\n"
            f"Members Left: {leaves}\n"
            f"Net Growth: {net_growth}"
        )
        embed.add_field(name="Member Churn Trends", value=churn_val, inline=False)
        
        voice_val = (
            f"Peak Voice Concurrency: {peak_voice} members\n"
            f"Average Voice Concurrency: {avg_voice:.1f} members"
        )
        embed.add_field(name="Voice Activity Metrics", value=voice_val, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
