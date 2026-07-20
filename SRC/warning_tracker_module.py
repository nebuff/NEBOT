import os
import json
import asyncio
import datetime
import uuid
import re
import discord
from discord import app_commands, ui
from configuration_module import get_guild_config, save_config, is_admin, is_mod

db_lock = asyncio.Lock()

# Target Construction Helpers
def make_discord_target(member: discord.Member | discord.User) -> dict:
    return {
        "platform": "Discord",
        "identifier": str(member.id),
        "display_name": member.name
    }

def make_twitch_target(username: str) -> dict:
    return {
        "platform": "Twitch",
        "identifier": username.strip().lower(),
        "display_name": username.strip()
    }

async def make_discord_id_target(guild: discord.Guild, client: discord.Client, user_id_str: str) -> dict:
    user_id_str = user_id_str.strip()
    user = None
    if user_id_str.isdigit():
        user = guild.get_member(int(user_id_str))
        if not user:
            try:
                user = await client.fetch_user(int(user_id_str))
            except Exception:
                pass
    if user:
        return make_discord_target(user)
    return {
        "platform": "Discord",
        "identifier": user_id_str,
        "display_name": f"ID: {user_id_str}"
    }

# Helper functions for asynchronous database access
async def get_user_warnings(guild_id: int, targets: list[dict]) -> list[dict]:
    from db_service import get_db_connection
    try:
        def _query():
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Find warnings associated with this guild
            # First, fetch all warnings for this guild
            cursor.execute("SELECT * FROM warnings WHERE guild_id = ?;", (guild_id,))
            w_rows = cursor.fetchall()
            if not w_rows:
                return []
                
            matched_warnings = []
            target_keys = {(t["platform"], t["identifier"]) for t in targets}
            
            for r in w_rows:
                w_id = r["id"]
                # Fetch linked accounts
                cursor.execute("SELECT platform, identifier, display_name FROM warning_linked_accounts WHERE warning_id = ?;", (w_id,))
                acc_rows = cursor.fetchall()
                linked = [{"platform": a["platform"], "identifier": a["identifier"], "display_name": a["display_name"]} for a in acc_rows]
                
                record_keys = {(acc["platform"], acc["identifier"]) for acc in linked}
                if target_keys.intersection(record_keys):
                    record = {
                        "id": w_id,
                        "guild_id": r["guild_id"],
                        "linked_accounts": linked,
                        "details": r["details"],
                        "severity": r["severity"],
                        "points": r["points"],
                        "timestamp": r["timestamp"],
                        "action_taken": r["action_taken"]
                    }
                    matched_warnings.append(record)
            
            # Sort by timestamp descending
            matched_warnings.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return matched_warnings
            
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _query)
    except Exception as e:
        print(f"Error reading warnings from DB: {e}")
        return []

async def get_active_points_and_records(guild_id: int, targets: list[dict], mode: str, window_days: int) -> tuple[int, list[dict]]:
    records = await get_user_warnings(guild_id, targets)
    if mode == "static":
        total_points = sum(r.get("points", 0) for r in records)
        return total_points, records
    
    # Rolling Mode
    active_records = []
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=window_days)
    total_points = 0
    for r in records:
        try:
            ts = datetime.datetime.fromisoformat(r.get("timestamp", ""))
            if ts >= cutoff:
                active_records.append(r)
                total_points += r.get("points", 0)
        except Exception:
            active_records.append(r)
            total_points += r.get("points", 0)
    return total_points, active_records

async def add_warning_record(guild_id: int, targets: list[dict], details: str, severity: str, points: int, action_taken: str) -> dict:
    from db_service import get_db_connection
    w_id = uuid.uuid4().hex
    ts_str = datetime.datetime.utcnow().isoformat()
    
    try:
        def _write():
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Ensure guild config exists
            cursor.execute("INSERT OR IGNORE INTO guild_configs (guild_id) VALUES (?)", (guild_id,))
            
            cursor.execute("""
            INSERT INTO warnings (id, guild_id, details, severity, points, timestamp, action_taken)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (w_id, guild_id, details, severity, points, ts_str, action_taken))
            
            for acc in targets:
                cursor.execute("""
                INSERT INTO warning_linked_accounts (warning_id, platform, identifier, display_name)
                VALUES (?, ?, ?, ?);
                """, (w_id, acc.get("platform"), acc.get("identifier"), acc.get("display_name")))
                
            conn.commit()
            
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _write)
        
        return {
            "id": w_id,
            "guild_id": guild_id,
            "linked_accounts": targets,
            "details": details,
            "severity": severity,
            "points": points,
            "timestamp": ts_str,
            "action_taken": action_taken
        }
    except Exception as e:
        print(f"Error adding warning record: {e}")
        return {}

async def edit_warning_record(guild_id: int, warning_id: str, new_details: str, new_points: int) -> tuple[bool, str]:
    from db_service import get_db_connection
    try:
        def _edit():
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM warnings WHERE id = ? AND guild_id = ?;", (warning_id, guild_id))
            row = cursor.fetchone()
            if not row:
                return False
                
            cursor.execute("""
            UPDATE warnings
            SET details = ?, points = ?
            WHERE id = ? AND guild_id = ?;
            """, (new_details, new_points, warning_id, guild_id))
            
            conn.commit()
            return True
            
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, _edit)
        if success:
            return True, "Warning updated successfully."
        else:
            return False, "Warning ID not found."
    except Exception as e:
        print(f"Error editing warning record: {e}")
        return False, f"Database error: {e}"

async def delete_warning_record(guild_id: int, warning_id: str) -> tuple[bool, str]:
    from db_service import get_db_connection
    try:
        def _delete():
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM warnings WHERE id = ? AND guild_id = ?;", (warning_id, guild_id))
            row = cursor.fetchone()
            if not row:
                return False
                
            cursor.execute("DELETE FROM warnings WHERE id = ? AND guild_id = ?;", (warning_id, guild_id))
            conn.commit()
            return True
            
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, _delete)
        if success:
            return True, "Warning deleted successfully."
        else:
            return False, "Warning ID not found."
    except Exception as e:
        print(f"Error deleting warning record: {e}")
        return False, f"Database error: {e}"

def parse_moderation_action(action: str) -> tuple[str, datetime.timedelta | None]:
    if not action:
        return "none", None
    
    act_lower = action.lower().strip()
    if act_lower in ("none", "", "null", "undefined"):
        return "none", None
        
    if "ban" in act_lower:
        return "ban", None
    if "kick" in act_lower:
        return "kick", None
        
    pattern = r"(\d+)\s*(seconds?|sec|s|minutes?|min|m|hours?|hr|h|days?|d|weeks?|wk|w|months?|mo)\b"
    match = re.search(pattern, act_lower)
    if match:
        val = int(match.group(1))
        unit = match.group(2)
        
        if unit.startswith("s"):
            return "timeout", datetime.timedelta(seconds=val)
        elif unit.startswith("m") and not unit.startswith("mo"):
            return "timeout", datetime.timedelta(minutes=val)
        elif unit.startswith("h"):
            return "timeout", datetime.timedelta(hours=val)
        elif unit.startswith("d"):
            return "timeout", datetime.timedelta(days=val)
        elif unit.startswith("w"):
            return "timeout", datetime.timedelta(weeks=val)
        elif unit.startswith("mo") or unit == "mo":
            return "timeout", datetime.timedelta(days=val * 30)
            
    if "timeout" in act_lower:
        num_match = re.search(r"(\d+)", act_lower)
        if num_match:
            val = int(num_match.group(1))
            return "timeout", datetime.timedelta(minutes=val)
        return "timeout", datetime.timedelta(minutes=10)
        
    return "none", None

async def log_action_to_channel(guild: discord.Guild, message: str, moderator: discord.Member | discord.User | str | None = None):
    config = get_guild_config(guild.id)
    log_ch_id = config.get("warning_log_channel_id") or config.get("global_log_channel_id")
    if log_ch_id:
        channel = guild.get_channel(log_ch_id)
        if not channel:
            try:
                channel = await guild.fetch_channel(log_ch_id)
            except Exception:
                pass
        if channel:
            embed = discord.Embed(
                title="Moderation Action Executed",
                description=message,
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.utcnow()
            )
            if moderator:
                if isinstance(moderator, str):
                    embed.set_footer(text=f"Moderator: {moderator}")
                else:
                    embed.set_footer(text=f"Moderator: {moderator.name}")
            else:
                embed.set_footer(text="Moderator: Unknown")
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

# Moderation Action Executer
async def execute_moderation_action(guild: discord.Guild, targets: list[dict], action: str, reason: str, moderator: discord.Member | discord.User | str | None = None) -> str:
    action_type, duration = parse_moderation_action(action)
    
    discord_targets = [t for t in targets if t["platform"] == "Discord"]
    if not discord_targets:
        msg = f"No Discord accounts linked. Escalation '{action}' logged but cannot be executed on Discord."
        print(f"[{datetime.datetime.utcnow().isoformat()}] [MODERATION ACTION] Guild '{guild.name}' (ID: {guild.id}) - Escalation '{action}' triggered for targets {[t['display_name'] for t in targets]} but no Discord accounts are linked.")
        return msg

    if action_type == "none":
        print(f"[{datetime.datetime.utcnow().isoformat()}] [MODERATION ACTION] Guild '{guild.name}' (ID: {guild.id}) - Action '{action}' parsed as log-only. No Discord enforcement taken.")
        return "No automated action mapping matched."

    results = []

    # Build a fast lookup cache for names if we need to fallback
    name_cache = {m.name.lower(): m for m in guild.members}

    # First pass: try to resolve all targets from cache
    resolved_members = {}
    missing_ids = set()

    for dt in discord_targets:
        user_id_str = dt["identifier"]
        member = None
        if user_id_str.isdigit():
            member = guild.get_member(int(user_id_str))

        if member:
            resolved_members[user_id_str] = member
        elif user_id_str.isdigit():
            missing_ids.add(int(user_id_str))

    # Second pass: fetch missing members concurrently
    if missing_ids:
        async def safe_fetch(uid):
            try:
                return uid, await guild.fetch_member(uid)
            except Exception:
                return uid, None

        fetch_results = await asyncio.gather(*(safe_fetch(uid) for uid in missing_ids))
        for uid, member in fetch_results:
            if member:
                resolved_members[str(uid)] = member

    for dt in discord_targets:
        user_id_str = dt["identifier"]
        member = resolved_members.get(user_id_str)

        if not member:
            # Fallback to fast search in cache by name only if exact ID lookup failed
            member = name_cache.get(dt["display_name"].lower())

        if not member:
            if action_type == "ban" and user_id_str.isdigit():
                try:
                    await guild.ban(discord.Object(id=int(user_id_str)), reason=reason)
                    msg_res = f"Successfully banned user ID {user_id_str} (not in server)."
                    results.append(msg_res)
                    print(f"[{datetime.datetime.utcnow().isoformat()}] [MODERATION ACTION] Guild '{guild.name}' (ID: {guild.id}) - Banned user ID {user_id_str} (not in server) for '{action}'. Reason: {reason}")
                    await log_action_to_channel(guild, f"Banned user ID {user_id_str} (not in server) (Action: {action}). Reason: {reason}", moderator=moderator)
                except discord.Forbidden as ex:
                    print(f"[ERROR] Permission error: Nebot lacks ban permission to ban ID {user_id_str} in guild {guild.name} ({guild.id}): {ex}")
                    results.append(f"Failed to ban ID {user_id_str}: Bot lacks permission.")
                except Exception as e:
                    results.append(f"Failed to ban ID {user_id_str}: {e}")
            else:
                results.append(f"User '{dt['display_name']}' is not present in the Discord server. Escalation skipped.")
            continue

        if action_type == "timeout" and duration:
            try:
                await member.timeout(duration, reason=reason)
                results.append(f"Applied {action} to {member.mention}.")
                print(f"[{datetime.datetime.utcnow().isoformat()}] [MODERATION ACTION] Guild '{guild.name}' (ID: {guild.id}) - Timed out {member.name} (ID: {member.id}) for {duration} due to '{action}'. Reason: {reason}")
                await log_action_to_channel(guild, f"Timed out {member.name} ({member.mention}) for {duration} (Action: {action}). Reason: {reason}", moderator=moderator)
            except discord.Forbidden as ex:
                print(f"[ERROR] Permission error: Nebot lacks timeout permission or role hierarchy prevents timing out user {member.name} ({member.id}) in guild {guild.name} ({guild.id}): {ex}")
                results.append(f"Failed to timeout {member.name}: Bot lacks permissions.")
            except Exception as e:
                results.append(f"Failed to timeout {member.name}: {e}")

        elif action_type == "ban":
            try:
                await member.ban(reason=reason)
                results.append(f"Banned {member.name} from the server.")
                print(f"[{datetime.datetime.utcnow().isoformat()}] [MODERATION ACTION] Guild '{guild.name}' (ID: {guild.id}) - Banned {member.name} (ID: {member.id}) due to '{action}'. Reason: {reason}")
                await log_action_to_channel(guild, f"Banned {member.name} ({member.mention}) (Action: {action}). Reason: {reason}", moderator=moderator)
            except discord.Forbidden as ex:
                print(f"[ERROR] Permission error: Nebot lacks ban permission or role hierarchy prevents banning user {member.name} ({member.id}) in guild {guild.name} ({guild.id}): {ex}")
                results.append(f"Failed to ban {member.name}: Bot lacks permissions.")
            except Exception as e:
                results.append(f"Failed to ban {member.name}: {e}")

        elif action_type == "kick":
            try:
                await member.kick(reason=reason)
                results.append(f"Kicked {member.name} from the server.")
                print(f"[{datetime.datetime.utcnow().isoformat()}] [MODERATION ACTION] Guild '{guild.name}' (ID: {guild.id}) - Kicked {member.name} (ID: {member.id}) due to '{action}'. Reason: {reason}")
                await log_action_to_channel(guild, f"Kicked {member.name} ({member.mention}) (Action: {action}). Reason: {reason}", moderator=moderator)
            except discord.Forbidden as ex:
                print(f"[ERROR] Permission error: Nebot lacks kick permission or role hierarchy prevents kicking user {member.name} ({member.id}) in guild {guild.name} ({guild.id}): {ex}")
                results.append(f"Failed to kick {member.name}: Bot lacks permissions.")
            except Exception as e:
                results.append(f"Failed to kick {member.name}: {e}")

    return "\n".join(results)


# --- WIZARD FLOW VIEWS ---

class WizardConfirmView(ui.View):
    def __init__(self, targets: list[dict], guild_id: int, author_id: int, config: dict):
        super().__init__(timeout=300)
        self.targets = targets
        self.guild_id = guild_id
        self.author_id = author_id
        self.config = config
        
        self.selected_platform = None
        self.details = ""
        self.severity = ""
        self.points = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This wizard is only for the command issuer.", ephemeral=True)
            return False
        return True

    @ui.button(label="Confirm User", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        platforms = self.config.get("warning_platforms", ["Discord"])
        if len(platforms) > 1:
            view = PlatformSelectionView(self, platforms)
            embed = discord.Embed(title="Warning Creation: Platform Origin", description="Where did this infraction occur?", color=discord.Color.orange())
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            self.selected_platform = platforms[0]
            view = DetailsPromptView(self)
            embed = discord.Embed(title="Warning Creation: Infraction Details", description="Provide the infraction description/reason.", color=discord.Color.orange())
            await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Warning creation cancelled.", embed=None, view=None)


class PlatformSelectionView(ui.View):
    def __init__(self, wizard: WizardConfirmView, platforms: list[str]):
        super().__init__(timeout=300)
        self.wizard = wizard
        for platform in platforms:
            self.add_item(PlatformButton(platform))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.wizard.author_id

    @ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: ui.Button):
        past_warnings = await get_user_warnings(self.wizard.guild_id, self.wizard.targets)
        total_pts = sum(r.get("points", 0) for r in past_warnings)
        
        target_names = []
        for t in self.wizard.targets:
            if t["platform"] == "Discord":
                target_names.append(f"Discord: {t['display_name']} (ID: {t['identifier']})")
            else:
                target_names.append(f"Twitch: {t['display_name']}")
        targets_str = ", ".join(target_names)

        if past_warnings:
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
        else:
            embed = discord.Embed(
                title="Is this the user? No active historical warnings found.",
                description=f"Proceed to log a new infraction for targets:\n**{targets_str}**?",
                color=discord.Color.light_grey()
            )
        
        view = WizardConfirmView(self.wizard.targets, self.wizard.guild_id, self.wizard.author_id, self.wizard.config)
        await interaction.response.edit_message(embed=embed, view=view)


class PlatformButton(ui.Button):
    def __init__(self, platform: str):
        super().__init__(label=platform, style=discord.ButtonStyle.secondary)
        self.platform = platform

    async def callback(self, interaction: discord.Interaction):
        self.view.wizard.selected_platform = self.platform
        view = DetailsPromptView(self.view.wizard)
        embed = discord.Embed(title="Warning Creation: Infraction Details", description="Provide the infraction description/reason.", color=discord.Color.orange())
        await interaction.response.edit_message(embed=embed, view=view)


class DetailsModal(ui.Modal, title="Infraction Description"):
    details_input = ui.TextInput(label="Incident Details", style=discord.TextStyle.paragraph, placeholder="Enter details of the warning...", required=True)

    def __init__(self, wizard: WizardConfirmView):
        super().__init__()
        self.wizard = wizard
        if wizard.details:
            self.details_input.default = wizard.details

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard.details = self.details_input.value
        
        # Calculate current points before presenting severity view
        mode = self.wizard.config.get("warning_escalation_mode", "static")
        days = self.wizard.config.get("warning_rolling_window_days", 90)
        current_points, _ = await get_active_points_and_records(self.wizard.guild_id, self.wizard.targets, mode, days)
        
        view = SeveritySelectionView(self.wizard, current_points)
        
        severity_points = self.wizard.config.get("warning_severity_points", {"Low": 1, "Medium": 2, "High": 3})
        warning_ladder = self.wizard.config.get("warning_ladder", {})
        
        forecasts = []
        for name, points in severity_points.items():
            new_points = current_points + points
            applicable_action = "None"
            highest_milestone = 0
            for pt_str, act in warning_ladder.items():
                try:
                    pt = int(pt_str)
                    if new_points >= pt and pt > highest_milestone:
                        highest_milestone = pt
                        applicable_action = act
                except ValueError:
                    continue
            forecasts.append(f"• **{name}** (+{points} pt) -> New Total: **{new_points}** pts -> Action: **{applicable_action}**")
            
        chart_str = "\n".join(forecasts)
        embed = discord.Embed(
            title="Warning Creation: Warning Severity",
            description=(
                f"Details captured. Now assign a severity level for this warning.\n\n"
                f"**Details:** {self.wizard.details}\n\n"
                f"**Escalation Action Forecast Chart:**\n{chart_str}"
            ),
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class DetailsPromptView(ui.View):
    def __init__(self, wizard: WizardConfirmView):
        super().__init__(timeout=300)
        self.wizard = wizard

    @ui.button(label="Enter Warning Details", style=discord.ButtonStyle.primary)
    async def enter_details(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(DetailsModal(self.wizard))

    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: discord.Interaction, button: ui.Button):
        platforms = self.wizard.config.get("warning_platforms", ["Discord"])
        if len(platforms) > 1:
            view = PlatformSelectionView(self.wizard, platforms)
            embed = discord.Embed(title="Warning Creation: Platform Origin", description="Where did this infraction occur?", color=discord.Color.orange())
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            past_warnings = await get_user_warnings(self.wizard.guild_id, self.wizard.targets)
            total_pts = sum(r.get("points", 0) for r in past_warnings)
            target_names = []
            for t in self.wizard.targets:
                if t["platform"] == "Discord":
                    target_names.append(f"Discord: {t['display_name']} (ID: {t['identifier']})")
                else:
                    target_names.append(f"Twitch: {t['display_name']}")
            targets_str = ", ".join(target_names)
            if past_warnings:
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
            else:
                embed = discord.Embed(
                    title="Is this the user? No active historical warnings found.",
                    description=f"Proceed to log a new infraction for targets:\n**{targets_str}**?",
                    color=discord.Color.light_grey()
                )
            view = WizardConfirmView(self.wizard.targets, self.wizard.guild_id, self.wizard.author_id, self.wizard.config)
            await interaction.response.edit_message(embed=embed, view=view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.wizard.author_id


class SeveritySelectionView(ui.View):
    def __init__(self, wizard: WizardConfirmView, current_points: int):
        super().__init__(timeout=300)
        self.wizard = wizard
        
        severity_points = wizard.config.get("warning_severity_points", {"Low": 1, "Medium": 2, "High": 3})
        warning_ladder = wizard.config.get("warning_ladder", {})
        
        for name, points in severity_points.items():
            new_points = current_points + points
            applicable_action = "None"
            highest_milestone = 0
            for pt_str, act in warning_ladder.items():
                try:
                    pt = int(pt_str)
                    if new_points >= pt and pt > highest_milestone:
                        highest_milestone = pt
                        applicable_action = act
                except ValueError:
                    continue
            
            button_label = f"{name} (+{points} pts) -> Action: {applicable_action}"
            if len(button_label) > 80:
                button_label = button_label[:77] + "..."
            self.add_item(SeverityButton(name, points, button_label))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.wizard.author_id

    @ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: ui.Button):
        view = DetailsPromptView(self.wizard)
        embed = discord.Embed(title="Warning Creation: Infraction Details", description="Provide the infraction description/reason.", color=discord.Color.orange())
        await interaction.response.edit_message(embed=embed, view=view)


class SeverityButton(ui.Button):
    def __init__(self, name: str, points: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.sev_name = name
        self.points = points

    async def callback(self, interaction: discord.Interaction):
        self.view.wizard.severity = self.sev_name
        self.view.wizard.points = self.points
        
        targets = self.view.wizard.targets
        guild_id = self.view.wizard.guild_id
        config = self.view.wizard.config
        mode = config.get("warning_escalation_mode", "static")
        days = config.get("warning_rolling_window_days", 90)
        
        active_points, active_records = await get_active_points_and_records(guild_id, targets, mode, days)
        view = ActionConfirmationView(self.view.wizard, active_records)
        
        # Calculate forecasted escalation action for this severity
        new_total_points = active_points + self.points
        warning_ladder = config.get("warning_ladder", {})
        applicable_action = "None"
        highest_milestone = 0
        for pt_str, act in warning_ladder.items():
            try:
                pt = int(pt_str)
                if new_total_points >= pt and pt > highest_milestone:
                    highest_milestone = pt
                    applicable_action = act
            except ValueError:
                continue

        embed = discord.Embed(title="Should action be taken?", color=discord.Color.red())
        
        target_names = []
        for t in targets:
            if t["platform"] == "Discord":
                target_names.append(f"Discord: {t['display_name']} (ID: {t['identifier']})")
            else:
                target_names.append(f"Twitch: {t['display_name']}")
        targets_str = "\n".join(target_names)
        
        embed.add_field(name="Warning Targets", value=targets_str, inline=False)
        embed.add_field(name="Platform Origin", value=self.view.wizard.selected_platform, inline=True)
        embed.add_field(name="Severity", value=f"{self.sev_name} ({self.points} pts)", inline=True)
        embed.add_field(name="Action to be Taken", value=applicable_action, inline=True)
        embed.add_field(name="New Incident Details", value=self.view.wizard.details, inline=False)
        embed.add_field(name="Current Active Points", value=f"{active_points} pt(s)", inline=True)
        embed.add_field(name="Escalation Mode", value=f"{mode.capitalize()} (Rolling: {days} days)" if mode == "rolling" else "Static", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=view)


class ActionConfirmationView(ui.View):
    def __init__(self, wizard: WizardConfirmView, active_records: list[dict]):
        super().__init__(timeout=300)
        self.wizard = wizard
        self.active_records = active_records
        
        if active_records:
            options = []
            for i, r in enumerate(active_records[:25]):
                timestamp = r.get("timestamp", "").split("T")[0]
                details = r.get("details", "")
                if len(details) > 50:
                    details = details[:47] + "..."
                label = f"[{timestamp}] {r.get('severity')} ({r.get('points')} pt)"
                desc = details
                options.append(discord.SelectOption(label=label, description=desc, value=r.get("id")))
            self.add_item(ui.Select(placeholder="View active warning history...", options=options, disabled=False, row=0))
        else:
            self.add_item(ui.Select(placeholder="No active warnings in history", options=[discord.SelectOption(label="None", value="none")], disabled=True, row=0))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.wizard.author_id

    @ui.button(label="Apply Ladder Action", style=discord.ButtonStyle.success, row=1)
    async def apply_ladder(self, interaction: discord.Interaction, button: ui.Button):
        config = self.wizard.config
        mode = config.get("warning_escalation_mode", "static")
        days = config.get("warning_rolling_window_days", 90)
        
        current_points, _ = await get_active_points_and_records(self.wizard.guild_id, self.wizard.targets, mode, days)
        new_total_points = current_points + self.wizard.points
        
        warning_ladder = config.get("warning_ladder", {})
        applicable_action = "None"
        highest_milestone = 0
        for pt_str, act in warning_ladder.items():
            try:
                pt = int(pt_str)
                if new_total_points >= pt and pt > highest_milestone:
                    highest_milestone = pt
                    applicable_action = act
            except ValueError:
                continue

        target_names = ", ".join(t["display_name"] for t in self.wizard.targets)
        reason = f"Warning Escalation: Cleared milestone {highest_milestone} with {new_total_points} total warning points. Targets: {target_names}. Incident: {self.wizard.details}"
        status_msg = await execute_moderation_action(interaction.guild, self.wizard.targets, applicable_action, reason, moderator=interaction.user)
        
        # Save warning record
        record = await add_warning_record(
            guild_id=self.wizard.guild_id,
            targets=self.wizard.targets,
            details=self.wizard.details,
            severity=self.wizard.severity,
            points=self.wizard.points,
            action_taken=applicable_action
        )
        
        # Trigger Logging & DM alerts
        await handle_warning_notifications(interaction, record, applicable_action)
        
        embed = discord.Embed(title="Warning Applied Successfully", color=discord.Color.green())
        embed.add_field(name="Warning Targets", value=target_names)
        embed.add_field(name="Severity", value=self.wizard.severity)
        embed.add_field(name="Points Assigned", value=f"{self.wizard.points} pts")
        embed.add_field(name="New Total Points", value=f"{new_total_points} pts")
        embed.add_field(name="Ladder Action Triggered", value=applicable_action)
        embed.add_field(name="Action Result", value=status_msg, inline=False)
        await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(label="Override & Log Only", style=discord.ButtonStyle.secondary, row=1)
    async def log_only(self, interaction: discord.Interaction, button: ui.Button):
        record = await add_warning_record(
            guild_id=self.wizard.guild_id,
            targets=self.wizard.targets,
            details=self.wizard.details,
            severity=self.wizard.severity,
            points=self.wizard.points,
            action_taken="None (Override/Logged)"
        )
        
        await handle_warning_notifications(interaction, record, "None (Override/Logged)")
        
        target_names = ", ".join(t["display_name"] for t in self.wizard.targets)
        embed = discord.Embed(title="Warning Logged (No Action)", color=discord.Color.blue())
        embed.add_field(name="Warning Targets", value=target_names)
        embed.add_field(name="Severity", value=self.wizard.severity)
        embed.add_field(name="Points Assigned", value=f"{self.wizard.points} pts")
        embed.add_field(name="Status", value="Incident saved to history database. Automated ladder progression bypassed.")
        await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(label="Manual Override: Ban", style=discord.ButtonStyle.danger, row=1)
    async def manual_ban(self, interaction: discord.Interaction, button: ui.Button):
        target_names = ", ".join(t["display_name"] for t in self.wizard.targets)
        reason = f"Manual override ban during warning creation. Targets: {target_names}. Incident: {self.wizard.details}"
        status_msg = await execute_moderation_action(interaction.guild, self.wizard.targets, "Permanent ban", reason, moderator=interaction.user)
        
        record = await add_warning_record(
            guild_id=self.wizard.guild_id,
            targets=self.wizard.targets,
            details=self.wizard.details,
            severity=self.wizard.severity,
            points=self.wizard.points,
            action_taken="Permanent ban (Manual Override)"
        )
        
        await handle_warning_notifications(interaction, record, "Permanent ban (Manual Override)")
        
        embed = discord.Embed(title="Manual Override Ban Executed", color=discord.Color.dark_red())
        embed.add_field(name="Warning Targets", value=target_names)
        embed.add_field(name="Status", value="Immediate permanent ban executed.")
        embed.add_field(name="Action Result", value=status_msg, inline=False)
        await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(label="Re-edit Details", style=discord.ButtonStyle.secondary, row=2)
    async def reedit_details(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(DetailsModal(self.wizard))

    @ui.button(label="Back", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: ui.Button):
        mode = self.wizard.config.get("warning_escalation_mode", "static")
        days = self.wizard.config.get("warning_rolling_window_days", 90)
        current_points, _ = await get_active_points_and_records(self.wizard.guild_id, self.wizard.targets, mode, days)
        
        view = SeveritySelectionView(self.wizard, current_points)
        
        severity_points = self.wizard.config.get("warning_severity_points", {"Low": 1, "Medium": 2, "High": 3})
        warning_ladder = self.wizard.config.get("warning_ladder", {})
        
        forecasts = []
        for name, points in severity_points.items():
            new_points = current_points + points
            applicable_action = "None"
            highest_milestone = 0
            for pt_str, act in warning_ladder.items():
                try:
                    pt = int(pt_str)
                    if new_points >= pt and pt > highest_milestone:
                        highest_milestone = pt
                        applicable_action = act
                except ValueError:
                    continue
            forecasts.append(f"• **{name}** (+{points} pt) -> New Total: **{new_points}** pts -> Action: **{applicable_action}**")
            
        chart_str = "\n".join(forecasts)
        embed = discord.Embed(
            title="Warning Creation: Warning Severity",
            description=(
                f"Details captured. Now assign a severity level for this warning.\n\n"
                f"**Details:** {self.wizard.details}\n\n"
                f"**Escalation Action Forecast Chart:**\n{chart_str}"
            ),
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# Helper function to distribute warning logs & DM notifications
async def handle_warning_notifications(interaction: discord.Interaction, record: dict, action_taken: str):
    config = get_guild_config(interaction.guild_id)
    
    # Warning Log Channel
    log_ch_id = config.get("warning_log_channel_id") or config.get("global_log_channel_id")
    if log_ch_id:
        channel = interaction.guild.get_channel(log_ch_id)
        if not channel:
            try:
                channel = await interaction.guild.fetch_channel(log_ch_id)
            except Exception:
                pass
        if channel:
            target_names = []
            for t in record.get("linked_accounts", []):
                if t["platform"] == "Discord":
                    target_names.append(f"Discord: {t['display_name']} (ID: {t['identifier']})")
                else:
                    target_names.append(f"Twitch: {t['display_name']}")
            targets_str = ", ".join(target_names)
            
            embed = discord.Embed(title="Warning Event Logged", color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Warning ID", value=record.get("id"), inline=True)
            embed.add_field(name="Severity", value=record.get("severity"), inline=True)
            embed.add_field(name="Points", value=str(record.get("points")), inline=True)
            embed.add_field(name="Warning Targets", value=targets_str, inline=False)
            embed.add_field(name="Details", value=record.get("details"), inline=False)
            embed.add_field(name="Escalation Action Taken", value=action_taken, inline=False)
            embed.set_footer(text=f"Moderator: {interaction.user.name}")
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

    # Direct Message Warning Alert
    dm_enabled = config.get("warning_dm_enabled", False)
    if dm_enabled:
        for t in record.get("linked_accounts", []):
            if t["platform"] == "Discord":
                user_id_str = t["identifier"]
                try:
                    member = await interaction.guild.fetch_member(int(user_id_str))
                    if member:
                        dm_msg = (
                            f"{interaction.guild.name} added a warning to your account for {record.get('details')}.\n"
                            f"Action taken: {action_taken}"
                        )
                        await member.send(dm_msg)
                except Exception:
                    pass

async def handle_warning_deletion_log(interaction: discord.Interaction, record: dict):
    config = get_guild_config(interaction.guild_id)
    log_ch_id = config.get("warning_log_channel_id") or config.get("global_log_channel_id")
    if log_ch_id:
        channel = interaction.guild.get_channel(log_ch_id)
        if not channel:
            try:
                channel = await interaction.guild.fetch_channel(log_ch_id)
            except Exception:
                pass
        if channel:
            target_names = []
            for t in record.get("linked_accounts", []):
                if t["platform"] == "Discord":
                    target_names.append(f"Discord: {t['display_name']} (ID: {t['identifier']})")
                else:
                    target_names.append(f"Twitch: {t['display_name']}")
            targets_str = ", ".join(target_names)
            
            embed = discord.Embed(
                title="Warning Record Deleted", 
                color=discord.Color.orange(), 
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Warning ID", value=record.get("id"), inline=True)
            embed.add_field(name="Severity", value=record.get("severity"), inline=True)
            embed.add_field(name="Points", value=str(record.get("points")), inline=True)
            embed.add_field(name="Warning Targets", value=targets_str, inline=False)
            embed.add_field(name="Original Details", value=record.get("details"), inline=False)
            embed.set_footer(text=f"Deleted By: {interaction.user.name}")
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

# --- EDIT MODAL ---
class EditWarningModal(ui.Modal, title="Edit Warning Record"):
    def __init__(self, warning_id: str, record: dict):
        super().__init__()
        self.warning_id = warning_id
        self.details_input = ui.TextInput(label="New Warning Details", default=record.get("details", ""), style=discord.TextStyle.paragraph, required=True)
        self.points_input = ui.TextInput(label="New Points Value", default=str(record.get("points", 0)), required=True)
        self.add_item(self.details_input)
        self.add_item(self.points_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            pts = int(self.points_input.value.strip())
            if pts < 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("Points must be a non-negative integer.", ephemeral=True)
        
        success, msg = await edit_warning_record(interaction.guild_id, self.warning_id, self.details_input.value, pts)
        await interaction.response.send_message(msg, ephemeral=True)


def setup_warning_tracker_commands(tree: app_commands.CommandTree):
    @tree.command(name="warning", description="Warn a user and process escalation actions")
    @app_commands.describe(
        discord_user="Primary Discord user account to warn",
        discord_id="Primary Discord user ID to warn",
        twitch_username="Primary Twitch username to warn",
        discord_user_2="Secondary/alt Discord user account to warn",
        discord_id_2="Secondary/alt Discord user ID to warn",
        twitch_username_2="Secondary/alt Twitch username to warn"
    )
    async def slash_warning(
        interaction: discord.Interaction,
        discord_user: discord.Member = None,
        discord_id: str = None,
        twitch_username: str = None,
        discord_user_2: discord.Member = None,
        discord_id_2: str = None,
        twitch_username_2: str = None
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        cfg = get_guild_config(interaction.guild_id)
        if not is_mod(interaction.user, cfg):
            await interaction.response.send_message("Permission denied.", ephemeral=True)
            return

        if not cfg.get("warning_tracker_enabled", False):
            await interaction.response.send_message("The Warning Tracker module is disabled on this server.", ephemeral=True)
            return

        targets = []
        if discord_user:
            targets.append(make_discord_target(discord_user))
        if discord_id:
            targets.append(await make_discord_id_target(interaction.guild, interaction.client, discord_id))
        if twitch_username:
            targets.append(make_twitch_target(twitch_username))
        if discord_user_2:
            targets.append(make_discord_target(discord_user_2))
        if discord_id_2:
            targets.append(await make_discord_id_target(interaction.guild, interaction.client, discord_id_2))
        if twitch_username_2:
            targets.append(make_twitch_target(twitch_username_2))

        if not targets:
            await interaction.response.send_message(
                "You must supply at least one warning target (Discord user, Discord ID, or Twitch username).", ephemeral=True
            )
            return

        past_warnings = await get_user_warnings(interaction.guild_id, targets)
        
        target_names = []
        for t in targets:
            if t["platform"] == "Discord":
                target_names.append(f"Discord: {t['display_name']} (ID: {t['identifier']})")
            else:
                target_names.append(f"Twitch: {t['display_name']}")
        targets_str = ", ".join(target_names)

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
            
            view = WizardConfirmView(targets, interaction.guild_id, interaction.user.id, cfg)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            embed = discord.Embed(
                title="Is this the user? No active historical warnings found.",
                description=f"Proceed to log a new infraction for targets:\n**{targets_str}**?",
                color=discord.Color.light_grey()
            )
            view = WizardConfirmView(targets, interaction.guild_id, interaction.user.id, cfg)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def warning_id_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        from db_service import get_db_connection
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM warnings WHERE guild_id = ?;", (interaction.guild_id,))
            w_rows = cursor.fetchall()
            if not w_rows:
                return []
                
            choices = []
            current_lower = current.lower()
            
            for r in w_rows:
                w_id = r["id"]
                # Fetch linked accounts
                cursor.execute("SELECT platform, identifier, display_name FROM warning_linked_accounts WHERE warning_id = ?;", (w_id,))
                acc_rows = cursor.fetchall()
                linked = [{"platform": a["platform"], "identifier": a["identifier"], "display_name": a["display_name"]} for a in acc_rows]
                
                details = r["details"] or ""
                if len(details) > 40:
                    details = details[:37] + "..."
                linked_names = ", ".join(acc["display_name"] for acc in linked)
                label = f"[{w_id[:6]}] {linked_names}: {details}"
                if len(label) > 100:
                    label = label[:97] + "..."
                    
                if not current or current_lower in w_id.lower() or current_lower in linked_names.lower() or current_lower in details.lower():
                    choices.append(app_commands.Choice(name=label, value=w_id))
            return choices[:25]
        except Exception as e:
            print(f"Error in warning autocomplete: {e}")
            return []

    @tree.command(name="warning-view", description="View warning infractions for a user")
    @app_commands.describe(
        discord_user="Discord user account to view warnings for",
        discord_id="Discord user ID to view warnings for",
        twitch_username="Twitch username to view warnings for"
    )
    async def slash_warning_view(
        interaction: discord.Interaction,
        discord_user: discord.Member = None,
        discord_id: str = None,
        twitch_username: str = None
    ):
        if not interaction.guild:
            return await interaction.response.send_message("Server only command", ephemeral=True)
        
        cfg = get_guild_config(interaction.guild_id)
        if not is_mod(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        targets = []
        search_name = ""
        if discord_user:
            targets.append(make_discord_target(discord_user))
            search_name = discord_user.name
        if discord_id:
            target = await make_discord_id_target(interaction.guild, interaction.client, discord_id)
            targets.append(target)
            if search_name:
                search_name += f" / {target['display_name']}"
            else:
                search_name = target['display_name']
        if twitch_username:
            targets.append(make_twitch_target(twitch_username))
            if search_name:
                search_name += f" / Twitch:{twitch_username}"
            else:
                search_name = f"Twitch:{twitch_username}"

        if not targets:
            return await interaction.response.send_message(
                "You must supply at least one target (Discord user, Discord ID, or Twitch username).", ephemeral=True
            )

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

    @tree.command(name="warning-edit", description="Edit an existing warning record details and points")
    @app_commands.describe(warning_id="Unique Warning ID string")
    @app_commands.autocomplete(warning_id=warning_id_autocomplete)
    async def slash_warning_edit(interaction: discord.Interaction, warning_id: str):
        if not interaction.guild:
            return await interaction.response.send_message("Server only command", ephemeral=True)
            
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        from db_service import get_db_connection
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM warnings WHERE id = ? AND guild_id = ?;", (warning_id, interaction.guild_id))
            row = cursor.fetchone()
            if not row:
                return await interaction.response.send_message(f"Warning ID '{warning_id}' not found.", ephemeral=True)
                
            cursor.execute("SELECT platform, identifier, display_name FROM warning_linked_accounts WHERE warning_id = ?;", (warning_id,))
            acc_rows = cursor.fetchall()
            linked = [{"platform": a["platform"], "identifier": a["identifier"], "display_name": a["display_name"]} for a in acc_rows]
            
            record = {
                "id": row["id"],
                "guild_id": row["guild_id"],
                "linked_accounts": linked,
                "details": row["details"],
                "severity": row["severity"],
                "points": row["points"],
                "timestamp": row["timestamp"],
                "action_taken": row["action_taken"]
            }
            await interaction.response.send_modal(EditWarningModal(warning_id, record))
        except Exception as e:
            return await interaction.response.send_message(f"Database error: {e}", ephemeral=True)

    @tree.command(name="warning-delete", description="Delete an infraction warning record")
    @app_commands.describe(warning_id="Unique Warning ID string")
    @app_commands.autocomplete(warning_id=warning_id_autocomplete)
    async def slash_warning_delete(interaction: discord.Interaction, warning_id: str):
        if not interaction.guild:
            return await interaction.response.send_message("Server only command", ephemeral=True)

        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied.", ephemeral=True)

        from db_service import get_db_connection
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM warnings WHERE id = ? AND guild_id = ?;", (warning_id, interaction.guild_id))
            row = cursor.fetchone()
            if not row:
                return await interaction.response.send_message(f"Warning ID '{warning_id}' not found.", ephemeral=True)
                
            cursor.execute("SELECT platform, identifier, display_name FROM warning_linked_accounts WHERE warning_id = ?;", (warning_id,))
            acc_rows = cursor.fetchall()
            linked = [{"platform": a["platform"], "identifier": a["identifier"], "display_name": a["display_name"]} for a in acc_rows]
            
            record = {
                "id": row["id"],
                "guild_id": row["guild_id"],
                "linked_accounts": linked,
                "details": row["details"],
                "severity": row["severity"],
                "points": row["points"],
                "timestamp": row["timestamp"],
                "action_taken": row["action_taken"]
            }
            
            success, msg = await delete_warning_record(interaction.guild_id, warning_id)
            if success:
                await handle_warning_deletion_log(interaction, record)
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"Database error: {e}", ephemeral=True)
