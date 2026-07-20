import os
import json
import asyncio
import asyncio
import datetime
import discord
from discord import app_commands, ui
from configuration_module import get_guild_config, save_config







async def load_vc_wr_records() -> dict:
    from db_service import get_db_connection
    try:
        def _read():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vc_wr_records;")
            rows = cursor.fetchall()
            records = {}
            for r in rows:
                g_str = str(r["guild_id"])
                u_str = r["user_id"]
                dur = r["duration"]
                if g_str not in records:
                    records[g_str] = {}
                records[g_str][u_str] = dur
            return records
        return await asyncio.to_thread(_read)
    except Exception as e:
        print(f"Error loading VC WR records: {e}")
        return {}

async def save_vc_wr_records(records: dict):
    from db_service import get_db_connection
    try:
        def _write():
            conn = get_db_connection()
            cursor = conn.cursor()
            for g_str, users in records.items():
                guild_id = int(g_str)
                for u_str, dur in users.items():
                    cursor.execute(
                        "INSERT OR REPLACE INTO vc_wr_records (guild_id, user_id, duration) VALUES (?, ?, ?)",
                        (guild_id, u_str, dur)
                    )
            conn.commit()
        await asyncio.to_thread(_write)
    except Exception as e:
        print(f"Error saving VC WR records: {e}")

async def load_vc_wr_sessions() -> dict:
    from db_service import get_db_connection
    try:
        def _read():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vc_wr_sessions;")
            rows = cursor.fetchall()
            sessions = {}
            for r in rows:
                g_str = str(r["guild_id"])
                u_str = r["user_id"]
                jt = r["join_time"]
                if g_str not in sessions:
                    sessions[g_str] = {}
                sessions[g_str][u_str] = jt
            return sessions
        return await asyncio.to_thread(_read)
    except Exception as e:
        print(f"Error loading VC WR sessions: {e}")
        return {}

async def save_vc_wr_sessions(sessions: dict):
    from db_service import get_db_connection
    try:
        def _write():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vc_wr_sessions;")
            for g_str, users in sessions.items():
                guild_id = int(g_str)
                for u_str, jt in users.items():
                    cursor.execute(
                        "INSERT OR REPLACE INTO vc_wr_sessions (guild_id, user_id, join_time) VALUES (?, ?, ?)",
                        (guild_id, u_str, jt)
                    )
            conn.commit()
        await asyncio.to_thread(_write)
    except Exception as e:
        print(f"Error saving VC WR sessions: {e}")

async def get_user_vc_wr_stats(guild_id: int, user_id: int) -> dict:
    records = await load_vc_wr_records()
    g_str = str(guild_id)
    u_str = str(user_id)

    guild_records = records.get(g_str, {})

    # Calculate on-the-fly current session
    sessions = await load_vc_wr_sessions()
    current_session_duration = 0.0
    if g_str in sessions and u_str in sessions[g_str]:
        join_time = sessions[g_str][u_str]
        current_session_duration = datetime.datetime.utcnow().timestamp() - join_time

    user_record = guild_records.get(u_str, 0.0)
    effective_record = user_record + current_session_duration

    if effective_record == 0.0:
        return {"rank": None, "record": 0.0, "current_session": current_session_duration}

    # Sort to find rank
    now = datetime.datetime.utcnow().timestamp()
    sorted_records = []
    for uid, dur in guild_records.items():
        current_dur = 0.0
        if uid in sessions.get(g_str, {}):
            current_dur = now - sessions[g_str][uid]
        sorted_records.append((uid, dur + current_dur))

    # Check for active sessions that might not have a stored record yet
    active_users = sessions.get(g_str, {})
    for a_uid, a_join in active_users.items():
        if a_uid not in guild_records:
            dur = now - a_join
            sorted_records.append((a_uid, dur))

    sorted_final = sorted(sorted_records, key=lambda x: x[1], reverse=True)

    rank = None
    for idx, (uid, dur) in enumerate(sorted_final):
        if uid == u_str:
            rank = idx + 1
            break

    return {"rank": rank, "record": effective_record, "current_session": current_session_duration}

def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0 seconds"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)

    parts = []
    if d > 0:
        parts.append(f"{d} day{'s' if d != 1 else ''}")
    if h > 0:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m > 0:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    if s > 0 or not parts:
        parts.append(f"{s} second{'s' if s != 1 else ''}")

    return ", ".join(parts)

class VCWRAllowedChannelsSelect(ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(
            placeholder="Select allowed voice channels...",
            min_values=0,
            max_values=10,
            channel_types=[discord.ChannelType.voice],
            row=0
        )
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        selected_ids = [ch.id for ch in self.values] if self.values else []
        cfg["vc_wr_allowed_channels"] = selected_ids
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Updated VC WR allowed channels")

        view = self.view
        if hasattr(view, "refresh"):
            await view.refresh(interaction)
        else:
            await interaction.response.defer(ephemeral=True)

class VCWRConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        enabled = cfg.get("vc_wr_enabled", False)
        allowed_ch = cfg.get("vc_wr_allowed_channels", [])
        lb_size = cfg.get("vc_wr_leaderboard_size", 5)
        live_ch_id = cfg.get("vc_wr_live_channel_id")

        embed = discord.Embed(
            title="Nebot Module: VC World Record",
            description="Configure competitive voice channel session duration leaderboards and notification triggers.",
            color=discord.Color.gold()
        )

        ch_str = ", ".join([f"<#{cid}>" for cid in allowed_ch]) if allowed_ch else "All Voice Channels"
        live_str = f"<#{live_ch_id}>" if live_ch_id else "Not Set"

        embed.add_field(name="Status", value="[ENABLED]" if enabled else "[DISABLED]", inline=True)
        embed.add_field(name="Leaderboard Size", value=str(lb_size), inline=True)
        embed.add_field(name="Live Channel", value=live_str, inline=True)
        embed.add_field(name="Allowed Channels", value=ch_str, inline=False)
        return embed

    @ui.button(label="Toggle VC WR", style=discord.ButtonStyle.primary, row=0)
    async def toggle_vc_wr(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["vc_wr_enabled"] = not cfg.get("vc_wr_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled VC WR module to {'enabled' if cfg['vc_wr_enabled'] else 'disabled'}")
        await self.refresh(interaction)

    @ui.button(label="Set Channels", style=discord.ButtonStyle.secondary, row=0)
    async def set_channels(self, interaction: discord.Interaction, button: ui.Button):
        view = ui.View()
        select = VCWRAllowedChannelsSelect(self.guild_id)
        select.view = view

        async def cancel_callback(i: discord.Interaction):
            await self.refresh(i)

        cancel_btn = ui.Button(label="Back", style=discord.ButtonStyle.danger, row=1)
        cancel_btn.callback = cancel_callback

        view.add_item(select)
        view.add_item(cancel_btn)

        # We need a bound refresh for the select to work
        view.refresh = self.refresh

        await interaction.response.edit_message(view=view)

    @ui.button(label="Leaderboard Size", style=discord.ButtonStyle.secondary, row=0)
    async def set_lb_size(self, interaction: discord.Interaction, button: ui.Button):
        view = ui.View()
        select = ui.Select(
            placeholder="Select leaderboard size...",
            options=[discord.SelectOption(label=str(i), value=str(i)) for i in range(5, 21, 5)],
            row=0
        )

        async def select_callback(i: discord.Interaction):
            cfg = get_guild_config(self.guild_id)
            cfg["vc_wr_leaderboard_size"] = int(select.values[0])
            save_config()
            from configuration_module import log_setting_change_task
            log_setting_change_task(i.guild, i.user, f"Updated VC WR leaderboard size to {select.values[0]}")
            await self.refresh(i)

        select.callback = select_callback

        async def cancel_callback(i: discord.Interaction):
            await self.refresh(i)

        cancel_btn = ui.Button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel_btn.callback = cancel_callback

        view.add_item(select)
        view.add_item(cancel_btn)

        await interaction.response.edit_message(view=view)

    @ui.button(label="Setup Live Channel", style=discord.ButtonStyle.success, row=1)
    async def setup_live_channel(self, interaction: discord.Interaction, button: ui.Button):
        view = ui.View()
        select = ui.ChannelSelect(
            placeholder="Select live channel...",
            channel_types=[discord.ChannelType.text],
            max_values=1,
            row=0
        )

        async def select_callback(i: discord.Interaction):
            cfg = get_guild_config(self.guild_id)
            channel_id = select.values[0].id
            cfg["vc_wr_live_channel_id"] = channel_id
            cfg["vc_wr_live_message_id"] = None # Reset message id so it sends a new one
            save_config()

            from configuration_module import log_setting_change_task
            log_setting_change_task(i.guild, i.user, f"Updated VC WR live channel to <#{channel_id}>")

            # Send initial message
            channel = i.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = await build_leaderboard_embed(self.guild_id)
                    msg = await channel.send(embed=embed)
                    cfg["vc_wr_live_message_id"] = msg.id
                    save_config()
                except Exception as e:
                    print(f"Error sending live message: {e}")

            await self.refresh(i)

        select.callback = select_callback

        async def clear_callback(i: discord.Interaction):
            cfg = get_guild_config(self.guild_id)
            cfg["vc_wr_live_channel_id"] = None
            cfg["vc_wr_live_message_id"] = None
            save_config()

            from configuration_module import log_setting_change_task
            log_setting_change_task(i.guild, i.user, "Cleared VC WR live channel")

            await self.refresh(i)

        clear_btn = ui.Button(label="Clear Channel", style=discord.ButtonStyle.secondary, row=1)
        clear_btn.callback = clear_callback

        async def cancel_callback(i: discord.Interaction):
            await self.refresh(i)

        cancel_btn = ui.Button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel_btn.callback = cancel_callback

        view.add_item(select)
        view.add_item(clear_btn)
        view.add_item(cancel_btn)

        await interaction.response.edit_message(view=view)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        from admin_ui_module import ModuleSelectView
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)


async def build_leaderboard_embed(guild_id: int) -> discord.Embed:
    cfg = get_guild_config(guild_id)
    size = cfg.get("vc_wr_leaderboard_size", 5)

    records = await load_vc_wr_records()
    sessions = await load_vc_wr_sessions()

    g_str = str(guild_id)
    guild_records = records.get(g_str, {})
    active_users = sessions.get(g_str, {})

    # Calculate total cumulative durations (all-time stored + current active)
    combined = []

    all_users = set(guild_records.keys()).union(set(active_users.keys()))

    for u_str in all_users:
        stored_dur = guild_records.get(u_str, 0.0)
        current_dur = 0.0
        if u_str in active_users:
            current_dur = datetime.datetime.utcnow().timestamp() - active_users[u_str]

        total_dur = stored_dur + current_dur
        if total_dur > 0:
            combined.append((u_str, total_dur))

    combined.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="Voice Channel World Records",
        description="Most total time spent in voice channels:",
        color=discord.Color.gold()
    )

    if not combined:
        embed.add_field(name="No Records Yet", value="Join a voice channel to start your timer!", inline=False)
        return embed

    for i, (u_str, dur) in enumerate(combined[:size]):
        is_active = " *(Live)*" if u_str in active_users else ""

        embed.add_field(
            name=f"Rank {i+1}",
            value=f"<@{u_str}>: **{format_duration(dur)}**{is_active}",
            inline=False
        )

    embed.set_footer(text="Accumulates time spent in voice channels.")
    embed.timestamp = datetime.datetime.utcnow()
    return embed

async def update_live_message(guild_id: int, client: discord.Client):
    cfg = get_guild_config(guild_id)
    enabled = cfg.get("vc_wr_enabled", False)
    if not enabled:
        return

    live_ch_id = cfg.get("vc_wr_live_channel_id")
    if not live_ch_id:
        return

    live_msg_id = cfg.get("vc_wr_live_message_id")

    guild = client.get_guild(guild_id)
    if not guild: return

    channel = guild.get_channel(live_ch_id)
    if not channel: return

    embed = await build_leaderboard_embed(guild_id)

    if live_msg_id:
        try:
            msg = await channel.fetch_message(live_msg_id)
            await msg.edit(embed=embed)
            return
        except discord.NotFound:
            pass # Message deleted, fall through to send a new one
        except Exception as e:
            print(f"Error updating live VC WR message: {e}")
            return

    # Send a new one and update config
    try:
        msg = await channel.send(embed=embed)
        cfg["vc_wr_live_message_id"] = msg.id
        save_config()
    except Exception as e:
        print(f"Error sending live VC WR message: {e}")


async def handle_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState, client: discord.Client):
    if member.bot:
        return

    guild_id = member.guild.id
    cfg = get_guild_config(guild_id)
    if not cfg.get("vc_wr_enabled", False):
        return

    allowed_channels = cfg.get("vc_wr_allowed_channels", [])

    b_ch = before.channel
    a_ch = after.channel

    if b_ch == a_ch:
        return

    g_str = str(guild_id)
    u_str = str(member.id)

    sessions = await load_vc_wr_sessions()
    records = await load_vc_wr_records()

    now = datetime.datetime.utcnow().timestamp()

    updated_live_msg = False

    # Did they leave an allowed channel?
    was_in_allowed = b_ch and (not allowed_channels or b_ch.id in allowed_channels)
    if was_in_allowed and g_str in sessions and u_str in sessions[g_str]:
        join_time = sessions[g_str].pop(u_str)
        await save_vc_wr_sessions(sessions)

        duration = now - join_time
        if duration > 0:
            if g_str not in records: records[g_str] = {}
            pb = records[g_str].get(u_str, 0.0)

            lb_size = cfg.get("vc_wr_leaderboard_size", 5)

            # Check rank before adding the new duration
            had_record = u_str in records[g_str]
            was_on_leaderboard = False
            if had_record:
                prev_durations = list(records[g_str].values())
                prev_durations.sort(reverse=True)
                prev_rank = prev_durations.index(pb) + 1
                was_on_leaderboard = prev_rank <= lb_size

            new_total = pb + duration
            records[g_str][u_str] = new_total
            await save_vc_wr_records(records)

            # Get all records to see rank
            all_durations = list(records[g_str].values())
            all_durations.sort(reverse=True)

            rank = all_durations.index(new_total) + 1

            if rank <= lb_size and not was_on_leaderboard:
                try:
                    await member.send("You have just made your way into the leaderboard!")
                except discord.Forbidden:
                    pass
                except Exception as e:
                    print(f"Failed to DM user about VC WR: {e}")

        updated_live_msg = True

    # Did they join an allowed channel?
    is_in_allowed = a_ch and (not allowed_channels or a_ch.id in allowed_channels)
    if is_in_allowed:
        if g_str not in sessions: sessions[g_str] = {}
        sessions[g_str][u_str] = now
        await save_vc_wr_sessions(sessions)
        updated_live_msg = True

    if updated_live_msg:
        await update_live_message(guild_id, client)


def setup_vc_wr_commands(tree: app_commands.CommandTree):
    @tree.command(name="vcwr", description="View the Voice Channel World Record Leaderboard")
    async def slash_vcwr(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only command", ephemeral=True)

        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("vc_wr_enabled", False):
            return await interaction.response.send_message("VC World Record tracking is currently disabled.", ephemeral=True)

        embed = await build_leaderboard_embed(interaction.guild_id)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # We don't have to return anything, it mutates tree

async def initialize_vc_sessions(client: discord.Client):
    sessions = await load_vc_wr_sessions()
    records = await load_vc_wr_records()
    now = datetime.datetime.utcnow().timestamp()

    modified_sessions = False
    modified_records = False
    live_update_guilds = set()

    for guild in client.guilds:
        g_str = str(guild.id)
        cfg = get_guild_config(guild.id)

        if not cfg.get("vc_wr_enabled", False):
            # If disabled, terminate all existing sessions for this guild
            if g_str in sessions:
                # We don't record PBs for disabled guilds on boot
                del sessions[g_str]
                modified_sessions = True
            continue

        allowed_channels = cfg.get("vc_wr_allowed_channels", [])

        # Get active users in allowed VCs
        active_in_vc = set()
        for vc in guild.voice_channels:
            if not allowed_channels or vc.id in allowed_channels:
                for member in vc.members:
                    if not member.bot:
                        active_in_vc.add(str(member.id))

        guild_sessions = sessions.get(g_str, {})
        new_guild_sessions = {}

        # Terminate sessions for users no longer in VC
        for u_str, join_time in guild_sessions.items():
            if u_str not in active_in_vc:
                duration = now - join_time
                if duration > 0:
                    if g_str not in records: records[g_str] = {}
                    records[g_str][u_str] = records[g_str].get(u_str, 0.0) + duration
                    modified_records = True
                modified_sessions = True
                live_update_guilds.add(guild.id)
            else:
                new_guild_sessions[u_str] = join_time

        # Start sessions for users in VC but missing from tracking
        for u_str in active_in_vc:
            if u_str not in new_guild_sessions:
                new_guild_sessions[u_str] = now
                modified_sessions = True
                live_update_guilds.add(guild.id)

        if new_guild_sessions:
            sessions[g_str] = new_guild_sessions
        elif g_str in sessions:
            del sessions[g_str]
            modified_sessions = True

    if modified_records:
        await save_vc_wr_records(records)
    if modified_sessions:
        await save_vc_wr_sessions(sessions)

    for gid in live_update_guilds:
        asyncio.create_task(update_live_message(gid, client))
