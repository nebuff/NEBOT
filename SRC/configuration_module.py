import os
import json
import discord

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

def _parse_int_env(name: str) -> int:
    val = os.getenv(name)
    if val:
        try:
            return int(val.strip())
        except ValueError:
            pass
    return None

MAIN_SERVER_ID = (
    _parse_int_env("MAIN_SERVER") or 
    _parse_int_env("MAIN_SERVER_ID") or 
    _parse_int_env("main-server")
)
AVATAR_CHANNEL_ID = (
    _parse_int_env("AVATAR_CHANNEL") or 
    _parse_int_env("AVATAR_CHANNEL_ID") or 
    _parse_int_env("avatar-channel")
)

DEFAULT_PREFIX = "!"
DEFAULT_CMD = "nebot"

SESSION_TIMEOUT_SECONDS = 5 * 60
SESSION_WARNING_BEFORE_SECONDS = 60
SESSION_WARNING_INTERVAL_SECONDS = 5

RESET = "\x1b[0m"
FG_RED = "\x1b[31m"
FG_GREEN = "\x1b[32m"
FG_YELLOW = "\x1b[33m"
FG_BLUE = "\x1b[34m"
FG_MAGENTA = "\x1b[35m"
FG_CYAN = "\x1b[36m"
FG_WHITE = "\x1b[37m"
FG_BRIGHT_BLACK = "\x1b[90m"
BOLD = "\x1b[1m"

guild_configs: dict[int, dict] = {}
bot_status: str = "Asuchan's really cool bot"
recommended_automod_filters: list[dict] = []
recommended_join_filters: list[dict] = []

def get_default_recommended_automod_filters() -> list[dict]:
    return [
        {
            "id": "rec_am_1",
            "name": "Profanity Filter",
            "enabled": True,
            "keywords": ["fuck", "shit", "asshole", "bitch", "cunt"],
            "enforcement_action": "Delete Message Only",
            "warning_severity": None,
            "direct_penalty": None,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        },
        {
            "id": "rec_am_2",
            "name": "Invite Links",
            "enabled": True,
            "keywords": ["r:discord\\.gg/\\w+", "r:discord\\.com/invite/\\w+"],
            "enforcement_action": "Delete + Warn User",
            "warning_severity": "Medium",
            "direct_penalty": None,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        },
        {
            "id": "rec_am_3",
            "name": "Phishing Links",
            "enabled": True,
            "keywords": ["r:steamcommmun[iy]ty\\.com", "r:free-nitro", "r:gift-nitro"],
            "enforcement_action": "Delete + Direct Penalty",
            "warning_severity": None,
            "direct_penalty": "1-Hour Timeout",
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        }
    ]

def get_default_recommended_join_filters() -> list[dict]:
    return [
        {
            "id": "rec_jf_1",
            "name": "Spambot Gate",
            "enabled": True,
            "keywords": ["spambot", "r:bot_\\d+", "r:alt_\\d+"],
            "enforcement_action": "ban"
        },
        {
            "id": "rec_jf_2",
            "name": "Advertiser Gate",
            "enabled": True,
            "keywords": ["nitro", "promo", "free_gift"],
            "enforcement_action": "kick"
        },
        {
            "id": "rec_jf_3",
            "name": "New Account Gate",
            "enabled": True,
            "keywords": ["r:alt_account.*", "r:helper_impersonator"],
            "enforcement_action": "quarantine"
        }
    ]

recommended_automod_filters.extend(get_default_recommended_automod_filters())
recommended_join_filters.extend(get_default_recommended_join_filters())

def get_bot_status() -> str:
    return bot_status

def set_bot_status(new_status: str):
    global bot_status
    bot_status = new_status
    save_config()

def load_config():
    global guild_configs, bot_status, recommended_automod_filters, recommended_join_filters
    from db_service import get_db_connection
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM global_configs;")
        rows = cursor.fetchall()
        raw_globals = {row["key"]: row["value"] for row in rows}
        
        bot_status = raw_globals.get("bot_status", "Asuchan's really cool bot")
        
        if "recommended_automod_filters" in raw_globals:
            recommended_automod_filters = json.loads(raw_globals["recommended_automod_filters"])
        else:
            recommended_automod_filters = get_default_recommended_automod_filters()
            
        if "recommended_join_filters" in raw_globals:
            recommended_join_filters = json.loads(raw_globals["recommended_join_filters"])
        else:
            recommended_join_filters = get_default_recommended_join_filters()
            
        # Load guild configs
        guild_configs = {}
        cursor.execute("SELECT * FROM guild_configs;")
        guild_rows = cursor.fetchall()
        for r in guild_rows:
            g_id = r["guild_id"]
            # Convert row to dict
            g_dict = dict(r)
            # Remove guild_id from the dict to match old behavior where keys are keys of raw dict
            del g_dict["guild_id"]
            
            # De-serialize JSON fields
            json_fields = [
                "warning_platforms", "warning_severity_points", "warning_ladder",
                "verification_verified_role_ids", "auto_roller_role_ids",
                "automod_filters", "automod_ignored_channels", "automod_ignored_roles",
                "music_allowed_roles", "music_allowed_users", "analytics_excluded_channels",
                "join_filter_username_patterns", "join_filters", "auto_channel_namer_exclude_ids",
                "self_roles_groups"
            ]
            for field in json_fields:
                if g_dict.get(field):
                    try:
                        g_dict[field] = json.loads(g_dict[field])
                    except Exception:
                        g_dict[field] = [] if "ids" in field or "filters" in field or "channels" in field or "roles" in field or "platforms" in field or "patterns" in field or "users" in field or "groups" in field else {}
                else:
                    g_dict[field] = [] if "ids" in field or "filters" in field or "channels" in field or "roles" in field or "platforms" in field or "patterns" in field or "users" in field or "groups" in field else {}
                    
            guild_configs[g_id] = g_dict
    except Exception as e:
        print(f"Error loading configuration from DB: {e}")
        guild_configs = {}

def save_config():
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("INSERT OR REPLACE INTO global_configs (key, value) VALUES (?, ?)", ("bot_status", bot_status))
        cursor.execute("INSERT OR REPLACE INTO global_configs (key, value) VALUES (?, ?)", ("recommended_automod_filters", json.dumps(recommended_automod_filters)))
        cursor.execute("INSERT OR REPLACE INTO global_configs (key, value) VALUES (?, ?)", ("recommended_join_filters", json.dumps(recommended_join_filters)))
        
        # Save guild configs
        for g_id, v in guild_configs.items():
            cursor.execute("""
            INSERT OR REPLACE INTO guild_configs (
                guild_id, prefix, cmd, channel_id, admin_role_id, shared_channel_id,
                private_sessions_enabled, shared_enabled, ne_os_enabled, nebuff_module_enabled, battle_enabled,
                battle_default_hp, battle_damage_range, battle_timeout, minesweeper_enabled,
                minesweeper_default_mines, warning_tracker_enabled, warning_platforms,
                warning_severity_points, warning_escalation_mode, warning_rolling_window_days,
                warning_ladder, warning_log_channel_id, warning_dm_enabled, verification_enabled,
                verification_unverified_role_id, verification_verified_role_id,
                verification_verified_role_ids, verification_channel_id,
                verification_landing_channel_id, global_log_channel_id,
                verification_log_channel_id, verification_timeout, mod_role_id,
                auto_roller_enabled, auto_roller_role_id, auto_roller_role_ids,
                automod_enabled, automod_filters, automod_ignored_channels, automod_ignored_roles,
                music_enabled, music_role_restriction_enabled, music_allowed_roles,
                music_allowed_users, music_component_restriction_enabled, analytics_enabled,
                analytics_excluded_channels, vc_wr_enabled, join_filter_enabled,
                join_filter_min_age_value, join_filter_min_age_unit, join_filter_username_patterns,
                join_filter_username_emojis, join_filter_username_homoglyphs,
                join_filter_enforcement, join_filters, auto_channel_namer_enabled,
                auto_channel_namer_left, auto_channel_namer_right, auto_channel_namer_font,
                auto_channel_namer_exclude_ids, plurality_enabled, self_roles_enabled,
                self_roles_groups
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            );
            """, (
                g_id,
                v.get("prefix"),
                v.get("cmd"),
                v.get("channel_id"),
                v.get("admin_role_id"),
                v.get("shared_channel_id"),
                v.get("private_sessions_enabled"),
                v.get("shared_enabled"),
                v.get("ne_os_enabled"),
                v.get("nebuff_module_enabled"),
                v.get("battle_enabled"),
                v.get("battle_default_hp"),
                v.get("battle_damage_range"),
                v.get("battle_timeout"),
                v.get("minesweeper_enabled"),
                v.get("minesweeper_default_mines"),
                v.get("warning_tracker_enabled"),
                json.dumps(v.get("warning_platforms", [])),
                json.dumps(v.get("warning_severity_points", {})),
                v.get("warning_escalation_mode"),
                v.get("warning_rolling_window_days"),
                json.dumps(v.get("warning_ladder", {})),
                v.get("warning_log_channel_id"),
                v.get("warning_dm_enabled"),
                v.get("verification_enabled"),
                v.get("verification_unverified_role_id"),
                v.get("verification_verified_role_id"),
                json.dumps(v.get("verification_verified_role_ids", [])),
                v.get("verification_channel_id"),
                v.get("verification_landing_channel_id"),
                v.get("global_log_channel_id"),
                v.get("verification_log_channel_id"),
                v.get("verification_timeout"),
                v.get("mod_role_id"),
                v.get("auto_roller_enabled"),
                v.get("auto_roller_role_id"),
                json.dumps(v.get("auto_roller_role_ids", [])),
                v.get("automod_enabled"),
                json.dumps(v.get("automod_filters", [])),
                json.dumps(v.get("automod_ignored_channels", [])),
                json.dumps(v.get("automod_ignored_roles", [])),
                v.get("music_enabled"),
                v.get("music_role_restriction_enabled"),
                json.dumps(v.get("music_allowed_roles", [])),
                json.dumps(v.get("music_allowed_users", [])),
                v.get("music_component_restriction_enabled"),
                v.get("analytics_enabled"),
                json.dumps(v.get("analytics_excluded_channels", [])),
                v.get("vc_wr_enabled"),
                v.get("join_filter_enabled"),
                v.get("join_filter_min_age_value"),
                v.get("join_filter_min_age_unit"),
                json.dumps(v.get("join_filter_username_patterns", [])),
                v.get("join_filter_username_emojis"),
                v.get("join_filter_username_homoglyphs"),
                v.get("join_filter_enforcement"),
                json.dumps(v.get("join_filters", [])),
                v.get("auto_channel_namer_enabled"),
                v.get("auto_channel_namer_left"),
                v.get("auto_channel_namer_right"),
                v.get("auto_channel_namer_font"),
                json.dumps(v.get("auto_channel_namer_exclude_ids", [])),
                v.get("plurality_enabled"),
                v.get("self_roles_enabled"),
                json.dumps(v.get("self_roles_groups", []))
            ))
        conn.commit()
    except Exception as e:
        print(f"Error saving configuration to DB: {e}")

def get_guild_config(guild_id: int | None) -> dict:
    default_cfg = {
        "prefix": DEFAULT_PREFIX, 
        "cmd": DEFAULT_CMD, 
        "channel_id": None, 
        "admin_role_id": None, 
        "shared_channel_id": None, 
        "private_sessions_enabled": False, 
        "shared_enabled": False, 
        "ne_os_enabled": False,
        "nebuff_module_enabled": False,
        "battle_enabled": False,
        "battle_default_hp": 500,
        "battle_damage_range": "0-100",
        "battle_timeout": 180,
        "minesweeper_enabled": False,
        "minesweeper_default_mines": 4,
        "warning_tracker_enabled": False,
        "warning_platforms": ["Discord"],
        "warning_severity_points": {"Low": 1, "Medium": 2, "High": 3},
        "warning_escalation_mode": "static",
        "warning_rolling_window_days": 90,
        "warning_ladder": {"2": "10-minute timeout", "3": "1-hour timeout", "5": "1-day timeout", "7": "Permanent ban"},
        "warning_log_channel_id": None,
        "warning_dm_enabled": False,
        "verification_enabled": False,
        "verification_unverified_role_id": None,
        "verification_verified_role_id": None,
        "verification_verified_role_ids": [],
        "verification_channel_id": None,
        "verification_landing_channel_id": None,
        "global_log_channel_id": None,
        "verification_log_channel_id": None,
        "verification_timeout": 0,
        "mod_role_id": None,
        "auto_roller_enabled": False,
        "auto_roller_role_id": None,
        "auto_roller_role_ids": [],
        "automod_enabled": False,
        "automod_filters": [],
        "automod_ignored_channels": [],
        "automod_ignored_roles": [],
        "music_enabled": False,
        "music_role_restriction_enabled": False,
        "music_allowed_roles": [],
        "music_allowed_users": [],
        "music_component_restriction_enabled": False,
        "analytics_enabled": False,
        "analytics_excluded_channels": [],
        "vc_wr_enabled": False,
        "join_filter_enabled": False,
        "join_filter_min_age_value": 0,
        "join_filter_min_age_unit": "days",
        "join_filter_username_patterns": [],
        "join_filter_username_emojis": False,
        "join_filter_username_homoglyphs": False,
        "join_filter_enforcement": "quarantine",
        "join_filters": [],
        "auto_channel_namer_enabled": False,
        "auto_channel_namer_left": "| -↳-",
        "auto_channel_namer_right": "",
        "auto_channel_namer_font": "normal",
        "auto_channel_namer_exclude_ids": [],
        "self_roles_enabled": False,
        "self_roles_groups": []
    }
    if guild_id is None:
        return default_cfg
    if guild_id not in guild_configs:
        guild_configs[guild_id] = default_cfg
    else:
        # Merge missing keys from default_cfg
        for k, v in default_cfg.items():
            if k not in guild_configs[guild_id]:
                guild_configs[guild_id][k] = v
    return guild_configs[guild_id]

def is_admin(author: discord.Member | discord.User, cfg: dict) -> bool:
    owner_id_str = os.getenv("OWNER_ID")
    if owner_id_str and owner_id_str.strip().isdigit():
        if author.id == int(owner_id_str.strip()):
            return True
    if not isinstance(author, discord.Member):
        return False
    if author.guild_permissions.administrator:
        return True
    role_id = cfg.get("admin_role_id")
    if role_id:
        _roles = getattr(author, '_roles', None)
        if _roles is not None and hasattr(_roles, 'has'):
            return _roles.has(role_id)
        return author.get_role(role_id) is not None
    return False

def is_mod(author: discord.Member | discord.User, cfg: dict) -> bool:
    owner_id_str = os.getenv("OWNER_ID")
    if owner_id_str and owner_id_str.strip().isdigit():
        if author.id == int(owner_id_str.strip()):
            return True
    if not isinstance(author, discord.Member):
        return False
    if is_admin(author, cfg):
        return True
    role_id = cfg.get("mod_role_id")
    if role_id:
        _roles = getattr(author, '_roles', None)
        if _roles is not None and hasattr(_roles, 'has'):
            return _roles.has(role_id)
        return author.get_role(role_id) is not None
    return False

async def log_setting_change(guild: discord.Guild, user: discord.User | discord.Member, action_desc: str):
    import datetime
    cfg = get_guild_config(guild.id)
    log_ch_id = cfg.get("global_log_channel_id")
    if log_ch_id:
        channel = guild.get_channel(log_ch_id)
        if not channel:
            try:
                channel = await guild.fetch_channel(log_ch_id)
            except Exception:
                pass
        if channel:
            if len(action_desc) > 3000:
                action_desc = action_desc[:2997] + "..."
            embed = discord.Embed(
                title="Config/Settings Updated",
                description=f"User {user.mention} ({user.name}) made a change:\n{action_desc}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

def log_setting_change_task(guild: discord.Guild, user: discord.User | discord.Member, action_desc: str):
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return loop.create_task(log_setting_change(guild, user, action_desc))
    except RuntimeError:
        pass

async def refresh_interaction(interaction: discord.Interaction, embed: discord.Embed, view: discord.ui.View = None, content: str = None):
    if interaction.response.is_done():
        await interaction.edit_original_response(content=content, embed=embed, view=view)
    else:
        await interaction.response.edit_message(content=content, embed=embed, view=view)

def safe_join_items(items: list[str], max_len: int = 1000) -> str:
    if not items:
        return "None"
    joined = ", ".join(items)
    if len(joined) <= max_len:
        return joined
    
    res = []
    current_len = 0
    for item in items:
        addition = (", " if res else "") + item
        if current_len + len(addition) + 25 > max_len:
            break
        res.append(item)
        current_len += len(addition)
    
    remaining = len(items) - len(res)
    if remaining > 0:
        return ", ".join(res) + f" ... (and {remaining} more)"
    return ", ".join(res)