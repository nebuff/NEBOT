import os
import json
import asyncio
import datetime
import configuration_module
import re
import discord
from discord import ui
from configuration_module import get_guild_config, save_config, is_admin
from automod_module import convert_emojis_to_text, convert_homoglyphs_to_text, make_bypass_regex

db_lock = asyncio.Lock()

def format_action_name(action: str) -> str:
    action_lower = action.lower()
    if action_lower == "quarantine":
        return "Alert Moderators"
    return action.capitalize()

def parse_join_keyword(kw: str) -> tuple[bool, str, bool, bool]:
    """
    Parses a join filter keyword into (is_regex, pattern_str, is_wildcard_start, is_wildcard_end).
    """
    kw_clean = kw.lower().strip()
    is_regex = False
    is_wildcard_start = False
    is_wildcard_end = False
    
    if kw_clean.startswith("r:"):
        is_regex = True
        pattern_str = kw_clean[2:].strip()
    else:
        if kw_clean.startswith("**") and kw_clean.endswith("**") and len(kw_clean) >= 4:
            pattern_str = kw_clean[2:-2].strip()
        else:
            if kw_clean.startswith("\\*"):
                is_wildcard_start = True
                kw_clean = kw_clean[2:].strip()
            elif kw_clean.startswith("*"):
                is_wildcard_start = True
                kw_clean = kw_clean[1:].strip()

            if kw_clean.endswith("\\*"):
                is_wildcard_end = True
                kw_clean = kw_clean[:-2].strip()
            elif kw_clean.endswith("*"):
                is_wildcard_end = True
                kw_clean = kw_clean[:-1].strip()
            
            pattern_str = kw_clean
            
    return is_regex, pattern_str, is_wildcard_start, is_wildcard_end

async def load_join_filter_logs() -> dict:
    from db_service import get_db_connection
    try:
        def _read():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM join_filtering_logs;")
            rows = cursor.fetchall()
            logs = {}
            for r in rows:
                g_str = str(r["guild_id"])
                if g_str not in logs:
                    logs[g_str] = []
                logs[g_str].append({
                    "user_id": int(r["user_id"]) if r["user_id"].isdigit() else r["user_id"],
                    "username": r["username"],
                    "account_created_at": r["account_created_at"],
                    "age_evaluated": r["age_evaluated"],
                    "reason": r["reason"],
                    "action": r["action"],
                    "status": r["status"],
                    "timestamp": r["timestamp"]
                })
            return logs
            
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _read)
    except Exception as e:
        print(f"Error loading join filter logs: {e}")
        return {}

async def save_join_filter_logs(logs: dict):
    from db_service import get_db_connection
    try:
        def _write():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM join_filtering_logs;")
            for g_str, entries in logs.items():
                g_id = int(g_str)
                # Ensure guild exists
                cursor.execute("INSERT OR IGNORE INTO guild_configs (guild_id) VALUES (?);", (g_id,))
                
                for entry in entries:
                    cursor.execute("""
                    INSERT INTO join_filtering_logs (
                        guild_id, user_id, username, account_created_at, age_evaluated, reason, action, status, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        g_id,
                        str(entry.get("user_id")),
                        entry.get("username"),
                        entry.get("account_created_at"),
                        entry.get("age_evaluated"),
                        entry.get("reason"),
                        entry.get("action"),
                        entry.get("status"),
                        entry.get("timestamp")
                    ))
            conn.commit()
            
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _write)
    except Exception as e:
        print(f"Error saving join filter logs: {e}")

async def log_enforcement_action(guild_id: int, user_id: int, username: str, account_created_at: str, age_evaluated: str, reason: str, action: str, status: str):
    from db_service import get_db_connection
    ts_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        def _log():
            conn = get_db_connection()
            cursor = conn.cursor()
            # Ensure guild exists
            cursor.execute("INSERT OR IGNORE INTO guild_configs (guild_id) VALUES (?);", (guild_id,))
            cursor.execute("""
            INSERT INTO join_filtering_logs (
                guild_id, user_id, username, account_created_at, age_evaluated, reason, action, status, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                guild_id,
                str(user_id),
                username,
                account_created_at,
                age_evaluated,
                reason,
                action,
                status,
                ts_str
            ))
            conn.commit()
            
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _log)
    except Exception as e:
        print(f"Error logging enforcement action: {e}")

async def send_join_filter_notification(guild: discord.Guild, embed: discord.Embed):
    cfg = get_guild_config(guild.id)
    target_ids = []
    for key in ["verification_log_channel_id", "global_log_channel_id", "warning_log_channel_id", "channel_id"]:
        val = cfg.get(key)
        if val and val not in target_ids:
            target_ids.append(val)
            
    sent = False
    for ch_id in target_ids:
        try:
            ch = guild.get_channel(ch_id) or await guild.fetch_channel(ch_id)
            if ch:
                await ch.send(embed=embed)
                sent = True
                break
        except Exception:
            pass
            
    if not sent and guild.system_channel:
        try:
            await guild.system_channel.send(embed=embed)
            sent = True
        except Exception:
            pass
            
    if not sent and guild.owner:
        try:
            await guild.owner.send(embed=embed)
        except Exception:
            pass

async def handle_member_join(member: discord.Member) -> bool:
    """
    Evaluates joining member against configured criteria (age, username patterns).
    Returns True if user was flagged and action was executed, halting downstream routines.
    """
    guild = member.guild
    cfg = get_guild_config(guild.id)
    
    if not cfg.get("join_filter_enabled", False):
        return False
        
    now = datetime.datetime.now(datetime.timezone.utc)
    account_created = member.created_at
    if not account_created:
        # Fallback if creation time not populated
        return False
        
    age = now - account_created
    min_age_val = cfg.get("join_filter_min_age_value", 0)
    min_age_unit = cfg.get("join_filter_min_age_unit", "days").lower()
    
    flagged = False
    reason = ""
    age_evaluated_str = f"{age.days}d {age.seconds // 3600}h"
    
    # Age Screening
    if min_age_val > 0:
        if min_age_unit == "days":
            threshold = datetime.timedelta(days=min_age_val)
        else:
            threshold = datetime.timedelta(hours=min_age_val)
            
        if age < threshold:
            flagged = True
            reason = f"Account age of {age_evaluated_str} is below threshold of {min_age_val} {min_age_unit}."
            
    # Username screening if not already flagged
    action = cfg.get("join_filter_enforcement", "quarantine").lower()
    
    if not flagged:
        patterns = cfg.get("join_filter_username_patterns", [])
        
        # Determine check names based on global legacy toggles
        use_username_emoji = cfg.get("join_filter_username_emojis", False)
        use_username_homo = cfg.get("join_filter_username_homoglyphs", False)
        
        check_names = [member.name, member.display_name]
        if use_username_emoji and use_username_homo:
            check_names.append(convert_homoglyphs_to_text(convert_emojis_to_text(member.name)))
            check_names.append(convert_homoglyphs_to_text(convert_emojis_to_text(member.display_name)))
        elif use_username_emoji:
            check_names.append(convert_emojis_to_text(member.name))
            check_names.append(convert_emojis_to_text(member.display_name))
        elif use_username_homo:
            check_names.append(convert_homoglyphs_to_text(member.name))
            check_names.append(convert_homoglyphs_to_text(member.display_name))
            
        for pattern in patterns:
            is_regex, clean_pattern, is_wildcard_start, is_wildcard_end = parse_join_keyword(pattern)
            
            # Treat plain keywords as bypass regexes if emojis or homoglyphs toggle is enabled
            if is_regex:
                pat = clean_pattern
            elif use_username_emoji or use_username_homo:
                pat = make_bypass_regex(clean_pattern, is_wildcard_start, is_wildcard_end)
                is_regex = True
            else:
                start_anchor = "" if is_wildcard_start else r"\b"
                end_anchor = "" if is_wildcard_end else r"\b"
                pat = rf"{start_anchor}{re.escape(clean_pattern)}{end_anchor}"
                
            try:
                rx = re.compile(pat, re.IGNORECASE)
                matched_username = False
                for name_to_check in check_names:
                    if rx.search(name_to_check):
                        matched_username = True
                        break
                if matched_username:
                    flagged = True
                    reason = f"Username or Display Name matched pattern: {clean_pattern}"
                    break
            except Exception:
                pass

    # New list-based join filters
    triggered_filters = []
    join_filters = cfg.get("join_filters", [])

    # Cache for check names to avoid redundant conversions
    cached_check_names = {}
    base_names = [member.name, member.display_name]

    for f in join_filters:
        if not f.get("enabled", True):
            continue
        kws = f.get("keywords", [])
        
        # Determine check names based on filter toggles
        use_emoji = f.get("filter_emojis", False)
        use_homo = f.get("filter_homoglyphs", False)
        
        cache_key = (use_emoji, use_homo)
        if cache_key not in cached_check_names:
            names = list(base_names)
            if use_emoji and use_homo:
                names.append(convert_homoglyphs_to_text(convert_emojis_to_text(member.name)))
                names.append(convert_homoglyphs_to_text(convert_emojis_to_text(member.display_name)))
            elif use_emoji:
                names.append(convert_emojis_to_text(member.name))
                names.append(convert_emojis_to_text(member.display_name))
            elif use_homo:
                names.append(convert_homoglyphs_to_text(member.name))
                names.append(convert_homoglyphs_to_text(member.display_name))
            cached_check_names[cache_key] = names

        check_names = cached_check_names[cache_key]
            
        for pattern in kws:
            is_regex, clean_pattern, is_wildcard_start, is_wildcard_end = parse_join_keyword(pattern)
                
            matched = False
            if is_regex:
                pat = clean_pattern
            elif use_emoji or use_homo:
                pat = make_bypass_regex(clean_pattern, is_wildcard_start, is_wildcard_end)
                is_regex = True
            else:
                start_anchor = "" if is_wildcard_start else r"\b"
                end_anchor = "" if is_wildcard_end else r"\b"
                pat = rf"{start_anchor}{re.escape(clean_pattern)}{end_anchor}"
                
            try:
                rx = re.compile(pat, re.IGNORECASE)
                for name_to_check in check_names:
                    if rx.search(name_to_check):
                        matched = True
                        break
            except Exception:
                pass
            
            if matched:
                triggered_filters.append(f)
                break
                
    if triggered_filters:
        def get_action_precedence(act):
            act_lower = act.lower()
            if act_lower == "ban": return 3
            if act_lower == "kick": return 2
            return 1
            
        triggered_filters.sort(key=lambda item: get_action_precedence(item.get("enforcement_action", "quarantine")), reverse=True)
        winning_filter = triggered_filters[0]
        
        list_action = winning_filter.get("enforcement_action", "quarantine").lower()
        if flagged:
            if get_action_precedence(list_action) > get_action_precedence(action):
                action = list_action
                reason = f"Matched Join Filter '{winning_filter.get('name')}': Username or Display Name triggered rules (higher precedence action taken)."
        else:
            flagged = True
            action = list_action
            reason = f"Matched Join Filter '{winning_filter.get('name')}': Username or Display Name triggered rules."
            
    if not flagged:
        return False
        
    status = "Pending"
    
    bot_member = guild.me or await guild.fetch_member(guild.client.user.id)
    
    if action == "quarantine":
        # Quarantine: role state and staff channel alert
        unverified_role_id = cfg.get("verification_unverified_role_id")
        if unverified_role_id:
            role = guild.get_role(unverified_role_id)
            if role:
                if bot_member.guild_permissions.manage_roles and role.position < bot_member.top_role.position:
                    try:
                        await member.add_roles(role, reason="Join filtering quarantine.")
                        status = "Quarantined"
                    except Exception as e:
                        status = f"Failed Quarantine Role Assignment: {e}"
                else:
                    status = "Failed Quarantine: Bot role hierarchy or Manage Roles permission issue"
            else:
                status = "Failed Quarantine: Unverified role not found"
        else:
            status = "Quarantined without role (no unverified role set)"
            
        embed = discord.Embed(
            title="Join Filtering Quarantine Incident",
            description=f"User {member.mention} ({member.name}, ID: {member.id}) failed connection requirements.",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Account Created At", value=account_created.isoformat(), inline=True)
        embed.add_field(name="Account Age", value=age_evaluated_str, inline=True)
        embed.add_field(name="Flag Trigger", value=reason, inline=False)
        embed.add_field(name="Enforcement Status", value=status, inline=False)
        await send_join_filter_notification(guild, embed)
        
    elif action == "kick":
        # Kick: DM first, then remove
        try:
            dm_msg = f"You have been removed from {guild.name} because your account does not meet the minimum entry requirements. Reason: {reason}"
            await member.send(dm_msg)
        except Exception:
            pass
            
        if bot_member.guild_permissions.kick_members and bot_member.top_role.position > member.top_role.position:
            try:
                await member.kick(reason=f"Join filter match: {reason}")
                status = "Kicked Successfully"
            except Exception as e:
                status = f"Failed Kick: {e}"
        else:
            status = "Failed Kick: Bot lacks Kick Members permission or role hierarchy restriction"
            
        embed = discord.Embed(
            title="Join Filtering Kick Incident",
            description=f"User {member.name} (ID: {member.id}) was processed for removal.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Account Created At", value=account_created.isoformat(), inline=True)
        embed.add_field(name="Account Age", value=age_evaluated_str, inline=True)
        embed.add_field(name="Flag Trigger", value=reason, inline=False)
        embed.add_field(name="Enforcement Status", value=status, inline=False)
        await send_join_filter_notification(guild, embed)
        
    elif action == "ban":
        # Ban: permanently ban
        if bot_member.guild_permissions.ban_members and bot_member.top_role.position > member.top_role.position:
            try:
                await member.ban(reason=f"Join filter match: {reason}", delete_message_days=0)
                status = "Banned Successfully"
            except Exception as e:
                status = f"Failed Ban: {e}"
        else:
            status = "Failed Ban: Bot lacks Ban Members permission or role hierarchy restriction"
            
        embed = discord.Embed(
            title="Join Filtering Ban Incident",
            description=f"User {member.name} (ID: {member.id}) was banned.",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Account Created At", value=account_created.isoformat(), inline=True)
        embed.add_field(name="Account Age", value=age_evaluated_str, inline=True)
        embed.add_field(name="Flag Trigger", value=reason, inline=False)
        embed.add_field(name="Enforcement Status", value=status, inline=False)
        await send_join_filter_notification(guild, embed)
        
    await log_enforcement_action(
        guild_id=guild.id,
        user_id=member.id,
        username=member.name,
        account_created_at=account_created.isoformat(),
        age_evaluated=age_evaluated_str,
        reason=reason,
        action=action,
        status=status
    )
    
    return True


class JoinFilteringConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        enabled = cfg.get("join_filter_enabled", False)
        
        min_age_val = cfg.get("join_filter_min_age_value", 0)
        min_age_unit = cfg.get("join_filter_min_age_unit", "days")
        if min_age_val > 0:
            age_str = f"{min_age_val} {min_age_unit}"
        else:
            age_str = "Disabled"
            
        patterns = cfg.get("join_filter_username_patterns", [])
        legacy_rules_str = f"{len(patterns)} legacy rules"
        
        filters = cfg.get("join_filters", [])
        
        use_username_emoji = cfg.get("join_filter_username_emojis", False)
        use_username_homo = cfg.get("join_filter_username_homoglyphs", False)
        
        embed = discord.Embed(
            title="Nebot Module: Join Filtering Gatekeeper",
            description="Configure automated screening parameters, account verification requirements, and threshold-based filter profiles for incoming accounts.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Status", value="[ENABLED]" if enabled else "[DISABLED]", inline=True)
        embed.add_field(name="Account Age Filter", value=age_str, inline=True)
        embed.add_field(name="Filter Count", value=f"{len(filters)} registered filters ({legacy_rules_str})", inline=True)
        embed.add_field(name="Username Emoji Filter", value="[ENABLED]" if use_username_emoji else "[DISABLED]", inline=True)
        embed.add_field(name="Username Homoglyph Filter", value="[ENABLED]" if use_username_homo else "[DISABLED]", inline=True)
        
        if filters:
            f_lines = []
            for f in filters[:10]:
                status_icon = "[ON]" if f.get("enabled", True) else "[OFF]"
                action_str = format_action_name(f.get("enforcement_action", "quarantine"))
                f_lines.append(f"{status_icon} **{f.get('name')}**: {action_str} ({len(f.get('keywords', []))} keywords)")
            embed.add_field(name="Active Filters Profile", value="\n".join(f_lines), inline=False)
        else:
            embed.add_field(name="Active Filters Profile", value="No filters configured yet.", inline=False)
            
        return embed

    @ui.button(label="Toggle Join Filter", style=discord.ButtonStyle.primary, row=0)
    async def toggle_filter(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["join_filter_enabled"] = not cfg.get("join_filter_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Join Filtering module state to `{'enabled' if cfg['join_filter_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Manage Filters", style=discord.ButtonStyle.secondary, row=0)
    async def manage_filters(self, interaction: discord.Interaction, button: ui.Button):
        view = ManageJoinFiltersView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Create Filter", style=discord.ButtonStyle.success, row=0)
    async def create_filter(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreateJoinFilterModal(self.guild_id))

    @ui.button(label="Account Age Setup", style=discord.ButtonStyle.secondary, row=1)
    async def age_setup(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(JoinFilterAgeModal(self.guild_id))

    @ui.button(label="Recommended Filters", style=discord.ButtonStyle.secondary, row=1)
    async def recommended_filters(self, interaction: discord.Interaction, button: ui.Button):
        view = ManageRecommendedJoinFiltersView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Toggle Username Emoji", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_username_emoji(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["join_filter_username_emojis"] = not cfg.get("join_filter_username_emojis", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Join legacy username emoji filtering to `{'enabled' if cfg['join_filter_username_emojis'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Toggle Username Homoglyph", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_username_homoglyph(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["join_filter_username_homoglyphs"] = not cfg.get("join_filter_username_homoglyphs", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Join legacy username homoglyph filtering to `{'enabled' if cfg['join_filter_username_homoglyphs'] else 'disabled'}`")
        await self.refresh(interaction)

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


class JoinFilterSelectMenu(ui.Select):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        cfg = get_guild_config(guild_id)
        filters = cfg.get("join_filters", [])
        
        options = []
        for f in filters[:25]:
            status_str = "Enabled" if f.get("enabled", True) else "Disabled"
            options.append(discord.SelectOption(
                label=f.get("name"),
                description=f"Status: {status_str} | Action: {f.get('enforcement_action').capitalize()}",
                value=f.get("id")
            ))
            
        if not options:
            options.append(discord.SelectOption(label="No filters configured", value="none"))
            super().__init__(placeholder="No filters available", options=options, disabled=True, row=0)
        else:
            super().__init__(placeholder="Select a join filter...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_filter_id = self.values[0]
        await self.view.refresh(interaction)


class ManageJoinFiltersView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.selected_filter_id = None
        self.add_item(JoinFilterSelectMenu(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        filters = cfg.get("join_filters", [])
        
        embed = discord.Embed(
            title="Join Filtering: Manage Filters",
            description="View details, toggle, or delete existing join filters.",
            color=discord.Color.blue()
        )
        
        selected_filter = next((f for f in filters if f.get("id") == self.selected_filter_id), None)
                
        if selected_filter:
            status = "ENABLED" if selected_filter.get("enabled", True) else "DISABLED"
            emoji_status = "ENABLED" if selected_filter.get("filter_emojis", False) else "DISABLED"
            homoglyph_status = "ENABLED" if selected_filter.get("filter_homoglyphs", False) else "DISABLED"
            action = format_action_name(selected_filter.get("enforcement_action", "quarantine"))
            from configuration_module import safe_join_items
            kws = safe_join_items([f"`{k}`" for k in selected_filter.get("keywords", [])])
            
            embed.add_field(name="Filter Name", value=selected_filter.get("name"), inline=True)
            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(name="Enforcement Action", value=action, inline=True)
            embed.add_field(name="Emoji Filter", value=emoji_status, inline=True)
            embed.add_field(name="Homoglyph Filter", value=homoglyph_status, inline=True)
            embed.add_field(name="Keywords", value=kws or "None", inline=False)
        else:
            embed.add_field(name="Details", value="Please select a join filter from the dropdown to manage it.", inline=False)
            
        return embed

    @ui.button(label="Toggle Status", style=discord.ButtonStyle.primary, row=1)
    async def toggle_status(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        new_status = False
        for f in cfg.get("join_filters", []):
            if f.get("id") == self.selected_filter_id:
                f["enabled"] = not f.get("enabled", True)
                filter_name = f.get("name", "Unknown")
                new_status = f["enabled"]
                break
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Toggled status of Join filter `{filter_name}` to `{'enabled' if new_status else 'disabled'}`")
        
        view = ManageJoinFiltersView(self.guild_id)
        view.selected_filter_id = self.selected_filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Edit Keywords", style=discord.ButtonStyle.secondary, row=1)
    async def edit_keywords(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        selected_filter = next((f for f in cfg.get("join_filters", []) if f.get("id") == self.selected_filter_id), None)
        if not selected_filter:
            return await interaction.response.send_message("Filter not found.", ephemeral=True)
            
        await interaction.response.send_modal(EditJoinFilterKeywordsModal(self.guild_id, self.selected_filter_id, selected_filter.get("keywords", [])))

    @ui.button(label="Delete Filter", style=discord.ButtonStyle.danger, row=1)
    async def delete_filter(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filters = cfg.get("join_filters", [])
        filter_name = "Unknown"
        for i, f in enumerate(filters):
            if f.get("id") == self.selected_filter_id:
                filter_name = f.get("name", "Unknown")
                filters.pop(i)
                break
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Deleted Join filter `{filter_name}`")
        
        view = ManageJoinFiltersView(self.guild_id)
        view.selected_filter_id = None
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Edit Action", style=discord.ButtonStyle.secondary, row=2)
    async def edit_action(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        view = EditJoinFilterEnforcementActionView(self.guild_id, self.selected_filter_id)
        embed = discord.Embed(
            title="Edit Join Filter: Enforcement Action",
            description="Configure the connection requirements enforcement action.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Toggle Emoji Filter", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_emoji_filter(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        new_status = False
        for f in cfg.get("join_filters", []):
            if f.get("id") == self.selected_filter_id:
                f["filter_emojis"] = not f.get("filter_emojis", False)
                filter_name = f.get("name", "Unknown")
                new_status = f["filter_emojis"]
                break
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Toggled emoji filtering of Join filter `{filter_name}` to `{'enabled' if new_status else 'disabled'}`")
        
        view = ManageJoinFiltersView(self.guild_id)
        view.selected_filter_id = self.selected_filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Toggle Homoglyph Filter", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_homoglyph_filter(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        new_status = False
        for f in cfg.get("join_filters", []):
            if f.get("id") == self.selected_filter_id:
                f["filter_homoglyphs"] = not f.get("filter_homoglyphs", False)
                filter_name = f.get("name", "Unknown")
                new_status = f["filter_homoglyphs"]
                break
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Toggled homoglyph filtering of Join filter `{filter_name}` to `{'enabled' if new_status else 'disabled'}`")
        
        view = ManageJoinFiltersView(self.guild_id)
        view.selected_filter_id = self.selected_filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Back to Gatekeeper", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = JoinFilteringConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class CreateJoinFilterModal(ui.Modal, title="Create Join Filter"):
    filter_name = ui.TextInput(label="Filter Name", placeholder="e.g. Spambot Prevention", required=True)
    keywords = ui.TextInput(
        label="Keywords (comma-separated)",
        placeholder="Use *word* for wildcards, r: for regex (e.g. *bot*, r:alt_\\d+)",
        style=discord.TextStyle.paragraph,
        required=True
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        name = self.filter_name.value.strip()
        kws = [k.strip() for k in self.keywords.value.split(",") if k.strip()]
        
        view = JoinFilterEnforcementActionSelectionView(self.guild_id, name, kws)
        embed = discord.Embed(
            title="Create Join Filter: Action",
            description=f"Configure the enforcement action to take when a user join matches **{name}**.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class JoinFilterEnforcementActionSelectionView(ui.View):
    def __init__(self, guild_id: int, name: str, keywords: list[str]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.name = name
        self.keywords = keywords

    @ui.button(label="Alert Moderators", style=discord.ButtonStyle.primary)
    async def quarantine_action(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "quarantine")
        await self.finish(interaction)

    @ui.button(label="Kick", style=discord.ButtonStyle.secondary)
    async def kick_action(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "kick")
        await self.finish(interaction)

    @ui.button(label="Ban", style=discord.ButtonStyle.danger)
    async def ban_action(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "ban")
        await self.finish(interaction)

    def save_filter(self, user, action: str):
        import uuid
        cfg = get_guild_config(self.guild_id)
        filters = cfg.setdefault("join_filters", [])
        filters.append({
            "id": uuid.uuid4().hex,
            "name": self.name,
            "enabled": True,
            "keywords": self.keywords,
            "enforcement_action": action,
            "filter_emojis": False,
            "filter_homoglyphs": False
        })
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(user.guild, user, f"Created Join filter `{self.name}` with enforcement action `{action}`")

    async def finish(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Join filter created successfully!", embed=None, view=None)


class EditJoinFilterKeywordsModal(ui.Modal, title="Edit Join Filter Keywords"):
    def __init__(self, guild_id: int, filter_id: str, current_kws: list[str]):
        super().__init__()
        self.guild_id = guild_id
        self.filter_id = filter_id
        self.keywords_input = ui.TextInput(
            label="Keywords (comma-separated)",
            default=", ".join(current_kws),
            placeholder="Use *word* for wildcards, r: for regex (e.g. *bot*, r:alt_\\d+)",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.keywords_input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        new_kws = []
        for f in cfg.get("join_filters", []):
            if f.get("id") == self.filter_id:
                f["keywords"] = [k.strip() for k in self.keywords_input.value.split(",") if k.strip()]
                filter_name = f.get("name", "Unknown")
                new_kws = f["keywords"]
                break
        save_config()
        from configuration_module import log_setting_change
        await log_setting_change(interaction.guild, interaction.user, f"Updated keywords for Join filter `{filter_name}` to: {', '.join(new_kws)}")
        
        view = ManageJoinFiltersView(self.guild_id)
        view.selected_filter_id = self.filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(content="Keywords updated successfully!", embed=embed, view=view)


class EditJoinFilterEnforcementActionView(ui.View):
    def __init__(self, guild_id: int, filter_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.filter_id = filter_id

    @ui.button(label="Alert Moderators", style=discord.ButtonStyle.primary)
    async def quarantine_action(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action(interaction.user, "quarantine")
        await self.finish(interaction)

    @ui.button(label="Kick", style=discord.ButtonStyle.secondary)
    async def kick_action(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action(interaction.user, "kick")
        await self.finish(interaction)

    @ui.button(label="Ban", style=discord.ButtonStyle.danger)
    async def ban_action(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action(interaction.user, "ban")
        await self.finish(interaction)

    def update_action(self, user, action: str):
        cfg = get_guild_config(self.guild_id)
        for f in cfg.get("join_filters", []):
            if f.get("id") == self.filter_id:
                f["enforcement_action"] = action
                save_config()
                from configuration_module import log_setting_change_task
                log_setting_change_task(user.guild, user, f"Updated enforcement action for Join filter `{f.get('name')}` to `{action}`")
                break

    async def finish(self, interaction: discord.Interaction):
        view = ManageJoinFiltersView(self.guild_id)
        view.selected_filter_id = self.filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(content="Enforcement action updated successfully!", embed=embed, view=view)


class RecommendedJoinFilterSelectMenu(ui.Select):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        recs = configuration_module.recommended_join_filters
        
        options = []
        for idx, f in enumerate(recs[:25]):
            options.append(discord.SelectOption(
                label=f.get("name"),
                description=f"Action: {format_action_name(f.get('enforcement_action', 'quarantine'))} | KWs: {len(f.get('keywords', []))}",
                value=str(idx)
            ))
            
        if not options:
            options.append(discord.SelectOption(label="No recommended filters configured", value="none"))
            super().__init__(placeholder="No recommended filters available", options=options, disabled=True, row=0)
        else:
            super().__init__(placeholder="Select a recommended filter...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_index = int(self.values[0]) if self.values[0] != "none" else None
        await self.view.refresh(interaction)


class ManageRecommendedJoinFiltersView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.selected_index = None
        self.filter_emojis = False
        self.filter_homoglyphs = False
        self.add_item(RecommendedJoinFilterSelectMenu(guild_id))

    def build_embed(self) -> discord.Embed:
        recs = configuration_module.recommended_join_filters
        
        embed = discord.Embed(
            title="Join Filtering: Recommended Filters",
            description="View recommended join filters and add them to your gatekeeper filter list.",
            color=discord.Color.blue()
        )
        
        selected_filter = None
        if self.selected_index is not None and 0 <= self.selected_index < len(recs):
            selected_filter = recs[self.selected_index]
                
        if selected_filter:
            action = format_action_name(selected_filter.get("enforcement_action", "quarantine"))
            from configuration_module import safe_join_items
            kws = safe_join_items([f"`{k}`" for k in selected_filter.get("keywords", [])])
            emoji_status = "ENABLED" if self.filter_emojis else "DISABLED"
            homoglyph_status = "ENABLED" if self.filter_homoglyphs else "DISABLED"
            
            embed.add_field(name="Filter Name", value=selected_filter.get("name"), inline=True)
            embed.add_field(name="Default Action", value=action, inline=True)
            embed.add_field(name="Emoji Filter", value=emoji_status, inline=True)
            embed.add_field(name="Homoglyph Filter", value=homoglyph_status, inline=True)
            embed.add_field(name="Keywords", value=kws or "None", inline=False)
        else:
            embed.add_field(name="Details", value="Select a recommended join filter from the dropdown to view its contents.", inline=False)
            
        return embed

    @ui.button(label="Add Selected Filter", style=discord.ButtonStyle.success, row=1)
    async def add_selected(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
            
        recs = configuration_module.recommended_join_filters
        if self.selected_index < 0 or self.selected_index >= len(recs):
            return await interaction.response.send_message("Invalid selection.", ephemeral=True)
            
        selected = recs[self.selected_index]
        cfg = get_guild_config(self.guild_id)
        filters = cfg.setdefault("join_filters", [])
        
        if any(f.get("name").lower() == selected.get("name").lower() for f in filters):
            return await interaction.response.send_message(f"A filter named '{selected.get('name')}' is already in your filter list.", ephemeral=True)
            
        import uuid
        new_filter = {
            "id": uuid.uuid4().hex,
            "name": selected.get("name"),
            "enabled": True,
            "keywords": list(selected.get("keywords", [])),
            "enforcement_action": selected.get("enforcement_action", "quarantine"),
            "filter_emojis": self.filter_emojis,
            "filter_homoglyphs": self.filter_homoglyphs
        }
        filters.append(new_filter)
        save_config()
        
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Added recommended Join filter '{new_filter['name']}'")
        await interaction.response.send_message(f"Successfully added '{new_filter['name']}' to your filter list.", ephemeral=True)

    @ui.button(label="Add All Recommended", style=discord.ButtonStyle.primary, row=1)
    async def add_all(self, interaction: discord.Interaction, button: ui.Button):
        recs = configuration_module.recommended_join_filters
        if not recs:
            return await interaction.response.send_message("No recommended filters available.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filters = cfg.setdefault("join_filters", [])
        
        added_names = []
        import uuid
        for rec in recs:
            if any(f.get("name").lower() == rec.get("name").lower() for f in filters):
                continue
            new_filter = {
                "id": uuid.uuid4().hex,
                "name": rec.get("name"),
                "enabled": True,
                "keywords": list(rec.get("keywords", [])),
                "enforcement_action": rec.get("enforcement_action", "quarantine"),
                "filter_emojis": False,
                "filter_homoglyphs": False
            }
            filters.append(new_filter)
            added_names.append(new_filter["name"])
            
        if not added_names:
            return await interaction.response.send_message("All recommended filters are already in your filter list.", ephemeral=True)
            
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Added all recommended Join filters: {', '.join(added_names)}")
        await interaction.response.send_message(f"Successfully added {len(added_names)} recommended filters: {', '.join(added_names)}", ephemeral=True)

    @ui.button(label="Toggle Emoji Filter", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_emoji_filter(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
        self.filter_emojis = not self.filter_emojis
        await self.refresh(interaction)

    @ui.button(label="Toggle Homoglyph Filter", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_homoglyph_filter(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
        self.filter_homoglyphs = not self.filter_homoglyphs
        await self.refresh(interaction)

    @ui.button(label="Back to Gatekeeper", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = JoinFilteringConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class JoinFilterAgeModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Account Age Filter Setup")
        
        cfg = get_guild_config(guild_id)
        current_val = cfg.get("join_filter_min_age_value", 0)
        current_unit = cfg.get("join_filter_min_age_unit", "days")
        
        self.val_input = ui.TextInput(
            label="Minimum Age Value (0 to disable)",
            default=str(current_val),
            placeholder="e.g. 3 or 24",
            required=True
        )
        self.unit_input = ui.TextInput(
            label="Unit (days or hours)",
            default=current_unit,
            placeholder="Enter 'days' or 'hours'",
            required=True
        )
        self.add_item(self.val_input)
        self.add_item(self.unit_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.val_input.value.strip())
            if val < 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("Minimum age value must be a non-negative integer.", ephemeral=True)
            
        unit = self.unit_input.value.strip().lower()
        if unit not in ["days", "hours"]:
            return await interaction.response.send_message("Unit must be either 'days' or 'hours'.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        cfg["join_filter_min_age_value"] = val
        cfg["join_filter_min_age_unit"] = unit
        save_config()
        
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Join Filtering minimum account age to {val} {unit}")
        
        dashboard = JoinFilteringConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

class JoinFilterUsernameRulesView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        patterns = cfg.get("join_filter_username_patterns", [])
        
        if patterns:
            from configuration_module import safe_join_items
            patterns_str = safe_join_items(patterns, max_len=1500)
        else:
            patterns_str = "No username scanning rules configured."
            
        embed = discord.Embed(
            title="Join Filtering: Username Rules Wizard",
            description="Manage patterns and regex structures evaluated against incoming account usernames and display names.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Active Pattern Rules", value=patterns_str, inline=False)
        return embed

    @ui.button(label="Add Rule", style=discord.ButtonStyle.secondary, row=0)
    async def add_rule(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(JoinFilterAddRuleModal(self.guild_id))

    @ui.button(label="Remove Rule", style=discord.ButtonStyle.secondary, row=0)
    async def remove_rule(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        patterns = cfg.get("join_filter_username_patterns", [])
        if not patterns:
            await interaction.response.send_message("There are no rules to remove.", ephemeral=True)
            return
            
        view = JoinFilterRemoveRuleView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Clear Rules", style=discord.ButtonStyle.danger, row=0)
    async def clear_rules(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["join_filter_username_patterns"] = []
        save_config()
        
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared all Join Filtering username rules")
        
        await self.refresh(interaction)

    @ui.button(label="Back to Gatekeeper", style=discord.ButtonStyle.primary, row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = JoinFilteringConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class JoinFilterAddRuleModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Add Username Filtering Rule")
        
        self.pattern_input = ui.TextInput(
            label="Keyword or Regex Pattern",
            placeholder="e.g. alt_account.* or helper_impersonator",
            required=True
        )
        self.add_item(self.pattern_input)

    async def on_submit(self, interaction: discord.Interaction):
        pattern = self.pattern_input.value.strip()
        if not pattern:
            return await interaction.response.send_message("Pattern cannot be empty.", ephemeral=True)
            
        try:
            re.compile(pattern)
        except re.error:
            pass
            
        cfg = get_guild_config(self.guild_id)
        patterns = cfg.get("join_filter_username_patterns", [])
        if pattern not in patterns:
            patterns.append(pattern)
            cfg["join_filter_username_patterns"] = patterns
            save_config()
            
            from configuration_module import log_setting_change_task
            log_setting_change_task(interaction.guild, interaction.user, f"Added Join Filtering username rule: {pattern}")
            
        view = JoinFilterUsernameRulesView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

class JoinFilterRemoveRuleView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
        cfg = get_guild_config(guild_id)
        patterns = cfg.get("join_filter_username_patterns", [])
        
        self.add_item(JoinFilterRuleSelect(guild_id, patterns[:25]))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Join Filtering: Remove Username Rule",
            description="Select a rule from the dropdown below to remove it from the gateway screening.",
            color=discord.Color.blue()
        )
        return embed

    @ui.button(label="Back to Rules", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = JoinFilterUsernameRulesView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

class JoinFilterRuleSelect(ui.Select):
    def __init__(self, guild_id: int, options_list: list[str]):
        self.guild_id = guild_id
        options = [discord.SelectOption(label=opt[:100], value=opt) for opt in options_list]
        super().__init__(placeholder="Select rule to delete...", options=options, custom_id="join_filter_rule_select", row=0)

    async def callback(self, interaction: discord.Interaction):
        selected_val = self.values[0]
        cfg = get_guild_config(self.guild_id)
        patterns = cfg.get("join_filter_username_patterns", [])
        if selected_val in patterns:
            patterns.remove(selected_val)
            cfg["join_filter_username_patterns"] = patterns
            save_config()
            
            from configuration_module import log_setting_change_task
            log_setting_change_task(interaction.guild, interaction.user, f"Removed Join Filtering username rule: {selected_val}")
            
        view = JoinFilterUsernameRulesView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

class JoinFilterEnforcementView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
        cfg = get_guild_config(self.guild_id)
        current = cfg.get("join_filter_enforcement", "quarantine").lower()
        
        self.quarantine_btn.style = discord.ButtonStyle.success if current == "quarantine" else discord.ButtonStyle.secondary
        self.kick_btn.style = discord.ButtonStyle.success if current == "kick" else discord.ButtonStyle.secondary
        self.ban_btn.style = discord.ButtonStyle.success if current == "ban" else discord.ButtonStyle.secondary

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        current = format_action_name(cfg.get("join_filter_enforcement", "quarantine"))
        
        embed = discord.Embed(
            title="Join Filtering: Enforcement Options",
            description="Select the enforcement action taken when an incoming account fails a gatekeeper rule check.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Enforcement", value=current, inline=False)
        return embed

    @ui.button(label="Alert Moderators", style=discord.ButtonStyle.secondary, row=0)
    async def quarantine_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self.set_enforcement(interaction, "quarantine")

    @ui.button(label="Kick", style=discord.ButtonStyle.secondary, row=0)
    async def kick_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self.set_enforcement(interaction, "kick")

    @ui.button(label="Ban", style=discord.ButtonStyle.secondary, row=0)
    async def ban_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self.set_enforcement(interaction, "ban")

    @ui.button(label="Back to Gatekeeper", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = JoinFilteringConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def set_enforcement(self, interaction: discord.Interaction, value: str):
        cfg = get_guild_config(self.guild_id)
        cfg["join_filter_enforcement"] = value
        save_config()
        
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Join Filtering enforcement action to {format_action_name(value)}")
        
        view = JoinFilterEnforcementView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
