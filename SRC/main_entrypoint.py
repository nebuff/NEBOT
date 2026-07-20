import asyncio
import datetime
import discord
from discord import app_commands

# Corrected imports matching your long filenames
from configuration_module import DISCORD_TOKEN, get_guild_config, load_config, FG_RED, RESET, SESSION_TIMEOUT_SECONDS, SESSION_WARNING_BEFORE_SECONDS, SESSION_WARNING_INTERVAL_SECONDS, get_bot_status
from session_module import get_session, load_session_data, save_session_data, sessions
from editor_module import handle_editor_command
from commands_registry_handlers_module import process_command
from admin_ui_module import setup_admin_commands
from utility_module import build_prompt_line, build_help_message, safe_send, ansi_block
from battle_module import setup_battle_commands, handle_battle_message, battle_watcher
from minesweeper_module import setup_minesweeper_commands
from vc_wr_module import setup_vc_wr_commands, handle_voice_state_update, initialize_vc_sessions

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class NebotClient(discord.Client):
    async def setup_hook(self):
        load_config()
        try:
            from self_assignable_roles_module import SelfRolesMenuView
            from configuration_module import guild_configs
            for guild_id, cfg in guild_configs.items():
                if cfg.get("self_roles_enabled", False):
                    for group in cfg.get("self_roles_groups", []):
                        self.add_view(SelfRolesMenuView(guild_id, group["name"]))
            print("Self-assignable roles persistent views registered.")
        except Exception as ex:
            print(f"[ERROR] Failed to setup self-assignable roles views: {ex}")

        setup_admin_commands(tree)
        setup_battle_commands(tree)
        setup_minesweeper_commands(tree)
        setup_vc_wr_commands(tree)
        try:
            from analytics_module import setup_analytics_commands
            setup_analytics_commands(tree)
        except Exception:
            pass
        from warning_tracker_module import setup_warning_tracker_commands
        setup_warning_tracker_commands(tree)
        
        from verification_module import VerificationGateView, setup_verification_commands
        self.add_view(VerificationGateView())
        setup_verification_commands(tree)
        
        from music_module import setup_music_commands
        setup_music_commands(tree)

        from plurality_module import setup_plurality_commands
        setup_plurality_commands(tree)
        
        from auto_channel_namer_module import setup_auto_channel_namer_commands
        setup_auto_channel_namer_commands(tree)
        
        await tree.sync()
        print("Slash commands synchronized via setup_hook.")

client = NebotClient(intents=intents)
tree = app_commands.CommandTree(client)

async def session_watcher():
    await client.wait_until_ready()
    while not client.is_closed():
        now = datetime.datetime.utcnow()
        to_delete = []
        for key, session in list(sessions.items()):
            if session.is_persistent:
                continue

            age = (now - session.last_activity).total_seconds()
            remaining = SESSION_TIMEOUT_SECONDS - age
            _, channel_id, user_id = key
            if not isinstance(user_id, int): continue
            channel = client.get_channel(channel_id)

            if remaining <= 0:
                to_delete.append(key)
                if channel:
                    try:
                        await channel.send(f"<@{user_id}> your Ne-OS session has expired.")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                continue

            if remaining <= SESSION_WARNING_BEFORE_SECONDS and channel:
                if session.warning_started_at is None:
                    session.warning_started_at = now
                    try:
                        msg = await channel.send(
                            f"<@{user_id}> your Ne-OS session is ending in "
                            f"**{int(remaining)}s** — send any command to reset"
                        )
                        session.warning_message_id = msg.id
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                elif session.warning_message_id:
                    try:
                        msg = await channel.fetch_message(session.warning_message_id)
                        await msg.edit(
                            content=f"<@{user_id}> your Ne-OS session is ending in "
                                    f"**{int(remaining)}s** — send any command to reset"
                        )
                    except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                        pass

        for key in to_delete:
            sessions.pop(key, None)
        await asyncio.sleep(SESSION_WARNING_INTERVAL_SECONDS)

@client.event
async def on_ready():
    load_config()
    load_session_data()
    asyncio.create_task(initialize_vc_sessions(client))
    print(f"Nebot ready — logged in as {client.user} (id={client.user.id})")
    asyncio.create_task(session_watcher())
    await client.change_presence(activity=discord.Game(name=get_bot_status()))
    asyncio.create_task(battle_watcher(client))

@client.event
async def on_member_join(member):
    try:
        from join_filtering_module import handle_member_join
        intercepted = await handle_member_join(member)
        if intercepted:
            return
    except Exception as ex:
        print(f"[ERROR] Join filter check failed: {ex}")

    try:
        from automod_module import handle_automod_join
        intercepted = await handle_automod_join(member)
        if intercepted:
            return
    except Exception as ex:
        print(f"[ERROR] AutoMod join check failed: {ex}")

    try:
        from analytics_module import handle_member_join as analytics_join
        await analytics_join(member)
    except Exception:
        pass
    cfg = get_guild_config(member.guild.id)
    if cfg.get("verification_enabled", False):
        verify_ch_id = cfg.get("verification_channel_id")
        if verify_ch_id:
            try:
                ch = member.guild.get_channel(verify_ch_id) or await member.guild.fetch_channel(verify_ch_id)
                if ch:
                    await ch.send(f"Welcome {member.mention}! Please verify your identity here.", delete_after=60)
            except Exception:
                pass
        
        timeout = cfg.get("verification_timeout", 0)
        if timeout > 0:
            from verification_module import schedule_verification_kick
            asyncio.create_task(schedule_verification_kick(member, timeout))

    if cfg.get("auto_roller_enabled", False):
        role_ids = cfg.get("auto_roller_role_ids", [])
        single_role = cfg.get("auto_roller_role_id")
        if single_role and single_role not in role_ids:
            role_ids = [single_role] + role_ids
            
        roles_to_add = []
        for rid in role_ids:
            if rid:
                role = member.guild.get_role(rid)
                if role:
                    roles_to_add.append(role)
                    
        if roles_to_add:
            try:
                bot_member = member.guild.me or await member.guild.fetch_member(client.user.id)
                allowed_roles = [r for r in roles_to_add if r.position < bot_member.top_role.position]
                skipped_roles = [r for r in roles_to_add if r.position >= bot_member.top_role.position]
                for r in skipped_roles:
                    print(f"[ERROR] Permission error: Nebot cannot add role '{r.name}' ({r.id}) to user {member.name} ({member.id}) due to role hierarchy.")
                if allowed_roles:
                    try:
                        await member.add_roles(*allowed_roles)
                    except discord.Forbidden as ex:
                        print(f"[ERROR] Permission error: Nebot cannot add roles to user {member.name} ({member.id}) due to missing permissions: {ex}")
            except Exception as ex:
                print(f"[ERROR] Failed to add auto-roller roles: {ex}")

@client.event
async def on_member_update(before, after):
    if before.nick != after.nick and after.nick:
        try:
            from automod_module import handle_automod_nickname
            await handle_automod_nickname(after)
        except Exception as ex:
            print(f"[ERROR] AutoMod nickname check failed: {ex}")

@client.event
async def on_guild_join(guild: discord.Guild):
    from configuration_module import get_guild_config, save_config
    get_guild_config(guild.id)
    save_config()

    owner = guild.owner
    if not owner:
        try:
            owner = await client.fetch_user(guild.owner_id)
        except Exception:
            pass
    if owner:
        try:
            msg = (
                "Thanks for inviting N/BOT!!!\n\n"
                "Here is a general guide on how to administer and configure the bot:\n\n"
                "1. How to Give the Bot Admin:\n"
                "To ensure all modules function correctly, go to Server Settings -> Roles, find the N/BOT role, and enable the \"Administrator\" permission. Alternatively, ensure the bot has a role with permissions to Manage Channels, Manage Roles, Kick Members, Ban Members, and Moderate Members.\n\n"
                "2. Setup with Commands:\n"
                "Use the following slash commands to configure the bot:\n"
                "- Use /admin to configure administrative settings, toggle modules (AutoMod, Auto Roller, Verification, warning ladder thresholds), and manage global configurations.\n"
                "- Use /mod to perform moderation actions like warning, kicking, or banning members.\n\n"
                "3. AutoMod Configuration (Regex and Allowed Words):\n"
                "When setting up AutoMod keywords, you can control what matches:\n"
                "- Standard words: Enter plain text (e.g. badword).\n"
                "- Regex patterns: Prefix the pattern with \"r:\" (e.g. r:phish.*link).\n"
                "- Allowed words (Exceptions): Prefix the word with \"a:\" to prevent it from triggering the block (e.g. a:grape, so it does not trigger a block on \"rape\").\n"
                "- Allowed regex: Prefix the regex with \"a:r:\" (e.g. a:r:class.*, to allow class when \"ass\" is blocked).\n\n"
                "4. Logging Channel (Recommended):\n"
                "It is highly recommended to set up a dedicated logs channel. You can set this up using the /admin dashboard. This channel will receive detailed event logs for any AutoMod violations and moderation actions."
            )
            await owner.send(msg)
        except Exception as e:
            print(f"[ERROR] Failed to send welcome DM to guild owner of {guild.name}: {e}")

@client.event
async def on_member_remove(member):
    try:
        from analytics_module import handle_member_leave as analytics_leave
        await analytics_leave(member)
    except Exception:
        pass

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    await handle_voice_state_update(member, before, after, client)
    try:
        from analytics_module import handle_voice_update as analytics_voice_update
        await analytics_voice_update(member, before, after)
    except Exception:
        pass


@client.event
async def on_message_edit(before, after):
    if after.author.bot:
        return
    if before.content == after.content:
        return
    try:
        from automod_module import handle_automod_message
        await handle_automod_message(after)
    except Exception as ex:
        print(f"[ERROR] AutoMod message edit check failed: {ex}")

@client.event
async def on_message(message: discord.Message):
    print(f"[Main Entrypoint Debug] on_message triggered for message: {message.id} | Content: {repr(message.content)} | Author: {message.author} (Bot: {message.author.bot})")
    if message.author.bot:
        return

    # Check for plurality shortcut commands (e.g. "ap <member>")
    from plurality_module import handle_plurality_commands
    if await handle_plurality_commands(message):
        return

    try:
        from analytics_module import handle_message_velocity as analytics_message
        await analytics_message(message)
    except Exception:
        pass

    if message.content.strip() == "!debug_plurality":
        try:
            await message.channel.send(" Debug command received, analyzing...")
            from plurality_module import plurality_data
            cfg = get_guild_config(message.guild.id)
            enabled = cfg.get("plurality_enabled", False)
            uid = str(message.author.id)
            has_data = uid in plurality_data
            system = plurality_data.get(uid) or {}
            members_count = len(system.get("members", {}))
            fronting = system.get("fronting_member")
            
            debug_msg = (
                f"**Plurality Debug Info:**\n"
                f"- Plurality Enabled in Guild: `{enabled}`\n"
                f"- User Profile Exists: `{has_data}`\n"
                f"- Members Count: `{members_count}`\n"
                f"- Fronting Member: `{fronting}`\n"
            )
            for short_name, mem in system.get("members", {}).items():
                if mem:
                    debug_msg += f"  - `{short_name}`: tag=`{mem.get('proxy_tag')}`\n"
                
            await message.channel.send(debug_msg)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            await message.channel.send(f" **Debug Command Crashed:**\n```py\n{tb[:1800]}\n```")
        return

    from automod_module import handle_automod_message
    if await handle_automod_message(message):
        return

    if await handle_battle_message(message):
        return

    from nebuff_module import handle_nebuff_message
    if await handle_nebuff_message(message):
        return

    from grok_module import handle_grok_message
    if await handle_grok_message(message):
        return

    from plurality_module import handle_plurality_message
    if await handle_plurality_message(message, client):
        return

    is_dm = message.guild is None
    content = message.content.strip()
    if not content:
        return

    guild_id = message.guild.id if not is_dm else None
    cfg = get_guild_config(guild_id)
    trigger = cfg["prefix"] + cfg["cmd"]

    is_shared = not is_dm and cfg.get("shared_enabled", False) and cfg.get("shared_channel_id") == message.channel.id

    if is_dm:
        cmdline = content
        session = get_session(None, message.channel.id, message.author.id)
        session.is_persistent = True
    elif is_shared:
        if content.lower().startswith(trigger.lower()):
            cmdline = content[len(trigger):].lstrip()
        else:
            cmdline = content
        session = get_session(guild_id, message.channel.id, "shared")
        session.is_persistent = True
    elif content.lower().startswith(trigger.lower()):
        cmdline = content[len(trigger):].lstrip()
        session = get_session(guild_id, message.channel.id, message.author.id)
    else:
        return

    if not is_dm and not is_shared and not cfg.get("private_sessions_enabled", False):
        await safe_send(message.channel, f"{FG_RED}Private sessions are currently disabled on this server.{RESET}")
        return

    if not is_dm and not cfg.get("ne_os_enabled", False):
        return

    try:
        await message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass

    allowed_ch = cfg.get("channel_id")
    if not is_shared and not is_dm and allowed_ch is not None and message.channel.id != allowed_ch:
        await safe_send(message.channel, 
            ansi_block(f"{FG_RED}This is not the specified channel for Ne-OS.{RESET}\n"
                       f"Please use <#{allowed_ch}>."),
            delete_after=10
        )
        return

    if session.editor is not None:
        session.touch_activity()
        await handle_editor_command(message, session, cmdline)
        if is_dm: save_session_data()
        return

    if not cmdline:
        session.touch_activity()
        pl = build_prompt_line(message, session, trigger)
        await safe_send(message.channel, build_help_message(pl, getattr(message.author, "display_name", "user"), session, trigger))
        return

    session.touch_activity()
    session.history.append(cmdline)
    session.history = session.history[-10:]

    await process_command(message, session, cmdline, is_shared)

def copy_client_events(old_client, new_client):
    for attr in dir(old_client):
        if attr.startswith("on_") and callable(getattr(old_client, attr)):
            setattr(new_client, attr, getattr(old_client, attr))

def main():
    global client, tree
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")
    
    run_status = "first_try"
    while run_status:
        if run_status == "first_try":
            try:
                client.run(DISCORD_TOKEN)
                run_status = None
            except discord.PrivilegedIntentsRequired:
                run_status = "retry_no_members"
        
        elif run_status == "retry_no_members":
            print("Warning: Server Members Intent is not enabled in the developer portal.")
            print("Retrying with members intent disabled. Note: New member verification channel pings will be inactive.")
            
            # Instantiate fresh Client and CommandTree with members intent disabled
            intents = discord.Intents.default()
            intents.message_content = True
            intents.members = False
            
            new_client = NebotClient(intents=intents)
            new_tree = app_commands.CommandTree(new_client)
            
            copy_client_events(client, new_client)
            
            client = new_client
            tree = new_tree
            
            try:
                client.run(DISCORD_TOKEN)
                run_status = None
            except discord.PrivilegedIntentsRequired:
                run_status = "retry_no_members_no_content"
                
        elif run_status == "retry_no_members_no_content":
            print("Warning: Message Content Intent is also not enabled in the developer portal.")
            print("Retrying with both members and message content intents disabled.")
            
            # Instantiate fresh Client and CommandTree with both intents disabled
            intents = discord.Intents.default()
            intents.message_content = False
            intents.members = False
            
            new_client = NebotClient(intents=intents)
            new_tree = app_commands.CommandTree(new_client)
            
            copy_client_events(client, new_client)
            
            client = new_client
            tree = new_tree
            client.run(DISCORD_TOKEN)
            run_status = None

if __name__ == "__main__":
    main()