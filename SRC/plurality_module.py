import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import asyncio
from discord import ui
from configuration_module import get_guild_config, save_config, MAIN_SERVER_ID, AVATAR_CHANNEL_ID

plurality_data: dict[str, dict] = {}

def load_plurality_data():
    global plurality_data
    plurality_data.clear()
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Select users with systems
        cursor.execute("SELECT user_id, system_name, fronting_member FROM users WHERE system_name IS NOT NULL;")
        user_rows = cursor.fetchall()
        for u in user_rows:
            u_id = u["user_id"]
            plurality_data[u_id] = {
                "system_name": u["system_name"],
                "fronting_member": u["fronting_member"],
                "members": {}
            }
            
            cursor.execute("SELECT id, short_name, display_name, avatar_url, avatar_msg_id, avatar_chan_id FROM members WHERE user_id = ?;", (u_id,))
            mem_rows = cursor.fetchall()
            for m in mem_rows:
                s_name = m["short_name"]
                m_id = m["id"]
                
                # Select proxy tag
                cursor.execute("SELECT proxy_tag FROM proxy_tags WHERE member_id = ?;", (m_id,))
                tag_row = cursor.fetchone()
                proxy_tag = tag_row["proxy_tag"] if tag_row else None
                
                plurality_data[u_id]["members"][s_name] = {
                    "display_name": m["display_name"],
                    "avatar_url": m["avatar_url"],
                    "avatar_msg_id": m["avatar_msg_id"],
                    "avatar_chan_id": m["avatar_chan_id"],
                    "proxy_tag": proxy_tag
                }
    except Exception as e:
        print(f"Error loading plurality data: {e}")

def save_plurality_data():
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Clear members and proxy_tags (cascaded from users deletion or manually deleted)
        # To keep it simple and clean, let's update users and rewrite members for active systems
        for user_id, sys_info in plurality_data.items():
            cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?);", (user_id,))
            cursor.execute("""
            UPDATE users
            SET system_name = ?, fronting_member = ?
            WHERE user_id = ?;
            """, (sys_info.get("system_name"), sys_info.get("fronting_member"), user_id))
            
            # Delete members not in active dict
            cursor.execute("SELECT id, short_name FROM members WHERE user_id = ?;", (user_id,))
            existing_mems = cursor.fetchall()
            active_mems = sys_info.get("members", {})
            for em in existing_mems:
                if em["short_name"] not in active_mems:
                    cursor.execute("DELETE FROM members WHERE id = ?;", (em["id"],))
                    
            # Insert or update active members
            for short_name, m_info in active_mems.items():
                cursor.execute("""
                INSERT OR REPLACE INTO members (user_id, short_name, display_name, avatar_url, avatar_msg_id, avatar_chan_id)
                VALUES (?, ?, ?, ?, ?, ?);
                """, (
                    user_id,
                    short_name,
                    m_info.get("display_name"),
                    m_info.get("avatar_url"),
                    m_info.get("avatar_msg_id"),
                    m_info.get("avatar_chan_id")
                ))
                member_db_id = cursor.lastrowid
                if not member_db_id:
                    # Row was replaced/updated, fetch the id
                    cursor.execute("SELECT id FROM members WHERE user_id = ? AND short_name = ?;", (user_id, short_name))
                    member_db_id = cursor.fetchone()["id"]
                    
                proxy_tag = m_info.get("proxy_tag")
                if proxy_tag:
                    cursor.execute("INSERT OR REPLACE INTO proxy_tags (member_id, proxy_tag) VALUES (?, ?);", (member_db_id, proxy_tag))
                else:
                    cursor.execute("DELETE FROM proxy_tags WHERE member_id = ?;", (member_db_id,))
                    
        # Handle systems that are completely deleted (i.e. user_id present in DB users but not in plurality_data)
        cursor.execute("SELECT user_id FROM users WHERE system_name IS NOT NULL;")
        db_users = cursor.fetchall()
        for du in db_users:
            u_id = du["user_id"]
            if u_id not in plurality_data:
                cursor.execute("UPDATE users SET system_name = NULL, fronting_member = NULL WHERE user_id = ?;", (u_id,))
                cursor.execute("DELETE FROM members WHERE user_id = ?;", (u_id,))
                
        conn.commit()
    except Exception as e:
        print(f"Error saving plurality data: {e}")

load_plurality_data()

class PluralityConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

        cfg = get_guild_config(guild_id)
        is_enabled = cfg.get("plurality_enabled", False)

        self.toggle_plurality.style = discord.ButtonStyle.primary
        self.toggle_plurality.label = "Disable Plurality" if is_enabled else "Enable Plurality"

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        is_enabled = cfg.get("plurality_enabled", False)

        embed = discord.Embed(
            title="Nebot Module: Plurality Management",
            description="Toggle proxy settings and webhook deployment options for plural systems and identity structures.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Status", value="Enabled" if is_enabled else "Disabled", inline=False)
        return embed

    @ui.button(label="Toggle Plurality", style=discord.ButtonStyle.primary, row=0)
    async def toggle_plurality(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        current = cfg.get("plurality_enabled", False)
        cfg["plurality_enabled"] = not current
        save_config()

        button.label = "Disable Plurality" if not current else "Enable Plurality"
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=0)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        from admin_ui_module import ModuleSelectView
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)


def setup_plurality_commands(tree: app_commands.CommandTree):

    system_group = app_commands.Group(name="system", description="System management commands")
    member_group = app_commands.Group(name="member", description="Alter member management commands")

    @system_group.command(name="register", description="Register a new plural system")
    async def system_register(interaction: discord.Interaction, name: str):
        user_id = str(interaction.user.id)
        if user_id in plurality_data:
            await interaction.response.send_message("You already have a system registered.", ephemeral=True)
            return

        plurality_data[user_id] = {
            "system_name": name,
            "members": {}
        }
        save_plurality_data()
        await interaction.response.send_message(f"System '{name}' registered successfully.", ephemeral=True)

    @member_group.command(name="add", description="Add an alter member to your system")
    async def member_add(interaction: discord.Interaction, short_name: str, display_name: str):
        user_id = str(interaction.user.id)
        if user_id not in plurality_data:
            await interaction.response.send_message("You do not have a system registered. Use /system register first.", ephemeral=True)
            return

        system = plurality_data[user_id]
        if short_name in system["members"]:
            await interaction.response.send_message(f"Member '{short_name}' already exists.", ephemeral=True)
            return

        if len(display_name) > 80:
            await interaction.response.send_message("Display name must be 80 characters or fewer.", ephemeral=True)
            return

        system["members"][short_name] = {
            "display_name": display_name,
            "avatar_url": None,
            "proxy_tag": None
        }
        save_plurality_data()
        await interaction.response.send_message(f"Member '{display_name}' ({short_name}) added successfully.", ephemeral=True)

    @member_group.command(name="avatar", description="Set the avatar URL for an alter member")
    async def member_avatar(interaction: discord.Interaction, short_name: str, url: str):
        user_id = str(interaction.user.id)
        if user_id not in plurality_data:
            await interaction.response.send_message("You do not have a system registered.", ephemeral=True)
            return

        system = plurality_data[user_id]
        if short_name not in system["members"]:
            await interaction.response.send_message(f"Member '{short_name}' not found.", ephemeral=True)
            return

        system["members"][short_name]["avatar_url"] = url
        save_plurality_data()
        await interaction.response.send_message(f"Avatar updated for member '{short_name}'.", ephemeral=True)

    @member_group.command(name="proxy", description="Set proxy tags (e.g. '[text]' or 'm:text')")
    async def member_proxy(interaction: discord.Interaction, short_name: str, proxy_tag: str):
        user_id = str(interaction.user.id)
        if user_id not in plurality_data:
            await interaction.response.send_message("You do not have a system registered.", ephemeral=True)
            return

        system = plurality_data[user_id]
        if short_name not in system["members"]:
            await interaction.response.send_message(f"Member '{short_name}' not found.", ephemeral=True)
            return

        if 'text' not in proxy_tag:
            await interaction.response.send_message("Proxy tag must contain the word 'text' (e.g. '[text]', 'm:text').", ephemeral=True)
            return

        display_name = system["members"][short_name]["display_name"]
        if len(display_name) + len(proxy_tag) > 80:
            await interaction.response.send_message("Display name and proxy tag combined length must be 80 characters or fewer.", ephemeral=True)
            return

        system["members"][short_name]["proxy_tag"] = proxy_tag
        save_plurality_data()
        await interaction.response.send_message(f"Proxy tag updated for member '{short_name}'.", ephemeral=True)

    tree.add_command(system_group)
    tree.add_command(member_group)

webhook_cache: dict[int, discord.Webhook] = {}

async def get_webhook_for_channel(channel: discord.abc.GuildChannel) -> discord.Webhook:
    if isinstance(channel, discord.Thread):
        target_channel = channel.parent
        if not target_channel:
            try:
                target_channel = channel.guild.get_channel(channel.parent_id) or await channel.guild.fetch_channel(channel.parent_id)
            except Exception:
                target_channel = None
    else:
        target_channel = channel

    if not target_channel:
        raise ValueError("Could not resolve target channel (thread parent may be missing or inaccessible).")

    if target_channel.id in webhook_cache:
        try:
            return webhook_cache[target_channel.id]
        except Exception:
            pass

    webhooks = await target_channel.webhooks()
    for wh in webhooks:
        if wh.token:
            webhook_cache[target_channel.id] = wh
            return wh

    wh = await target_channel.create_webhook(name="Nebot Proxy Webhook")
    webhook_cache[target_channel.id] = wh
    return wh

async def log_plurality_error(guild: discord.Guild, client: discord.Client, error_text: str):
    cfg = get_guild_config(guild.id)
    log_ch_id = cfg.get("global_log_channel_id")
    sent = False
    
    if log_ch_id:
        try:
            log_ch = guild.get_channel(log_ch_id) or await client.fetch_channel(log_ch_id)
            if log_ch:
                await log_ch.send(f"️ **Plurality Module Error in {guild.name}:**\n{error_text}")
                sent = True
        except Exception as e:
            print(f"[Plurality] Failed to log error to channel {log_ch_id}: {e}")
            
    if not sent:
        try:
            owner = guild.owner or await guild.fetch_member(guild.owner_id)
            if owner:
                await owner.send(f"️ **Plurality Module Error in your server '{guild.name}':**\n{error_text}")
        except Exception as e:
            print(f"[Plurality] Failed to DM owner {guild.owner_id}: {e}")

async def get_or_create_avatar_channel(guild: discord.Guild, client: discord.Client) -> discord.TextChannel:
    if MAIN_SERVER_ID and AVATAR_CHANNEL_ID:
        try:
            main_guild = client.get_guild(MAIN_SERVER_ID) or await client.fetch_guild(MAIN_SERVER_ID)
            if main_guild:
                chan = main_guild.get_channel(AVATAR_CHANNEL_ID) or await client.fetch_channel(AVATAR_CHANNEL_ID)
                if chan and isinstance(chan, discord.TextChannel):
                    return chan
        except Exception as e:
            print(f"[Plurality] Failed to fetch global avatar storage channel: {e}")
            
    for channel in guild.text_channels:
        if channel.name == "nebot-avatars":
            return channel
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
    }
    return await guild.create_text_channel("nebot-avatars", overwrites=overwrites, reason="Nebot Plurality Avatar Storage")

avatar_url_cache = {} # Key: message_id, value: (url, timestamp)

async def resolve_avatar_url(guild: discord.Guild, member_info: dict, client: discord.Client) -> str:
    msg_id = member_info.get("avatar_msg_id")
    chan_id = member_info.get("avatar_chan_id")
    
    if msg_id and chan_id:
        import time
        now = time.time()
        if msg_id in avatar_url_cache:
            url, ts = avatar_url_cache[msg_id]
            if now - ts < 80000: # Cache for 22 hours
                return url
                
        try:
            chan = client.get_channel(chan_id) or await client.fetch_channel(chan_id)
            if chan:
                msg = await chan.fetch_message(msg_id)
                if msg.attachments:
                    url = msg.attachments[0].url
                    avatar_url_cache[msg_id] = (url, now)
                    return url
        except Exception as e:
            err_msg = f"Failed to fetch avatar message {msg_id} in channel {chan_id}: {e}"
            print(f"[Plurality] {err_msg}")
            await log_plurality_error(guild, client, err_msg)
            
    url_val = member_info.get("avatar_url")
    if url_val:
        if url_val.startswith("http"):
            return url_val
        if os.path.exists(url_val):
            try:
                avatar_chan = await get_or_create_avatar_channel(guild, client)
                file = discord.File(url_val, filename="avatar.png")
                msg = await avatar_chan.send(content="Migrated legacy avatar", file=file)
                member_info["avatar_msg_id"] = msg.id
                member_info["avatar_chan_id"] = avatar_chan.id
                member_info["avatar_url"] = None
                save_plurality_data()
                return msg.attachments[0].url
            except Exception as e:
                err_msg = f"Failed to migrate legacy avatar {url_val}: {e}"
                print(f"[Plurality] {err_msg}")
                await log_plurality_error(guild, client, err_msg)
    return None

async def send_hidden_response(message: discord.Message, text: str):
    if not message.guild:
        await message.reply(text)
    else:
        try:
            await message.delete()
        except:
            pass
        try:
            await message.channel.send(f"{message.author.mention}, {text}", delete_after=5)
        except:
            pass

async def handle_plurality_commands(message: discord.Message) -> bool:
    content = message.content.strip()
    parts = content.split()
    if not parts or parts[0].lower() != "ap":
        return False
        
    user_id = str(message.author.id)
    if user_id not in plurality_data:
        if not message.guild:
            await message.reply("You do not have a plurality system registered yet. Use `/dash` in a server to get started!")
            return True
        return False
        
    system = plurality_data[user_id]
    
    if len(parts) == 1:
        fronting = system.get("fronting_member")
        if fronting:
            disp = system["members"].get(fronting, {}).get("display_name", fronting)
            await send_hidden_response(message, f"current fronting member is **{disp}** (`{fronting}`)")
        else:
            await send_hidden_response(message, "no member is currently set as fronting.")
        return True
        
    target_short = parts[1].lower()
    if target_short in ["none", "clear"]:
        system["fronting_member"] = None
        save_plurality_data()
        if message.guild:
            try:
                await message.delete()
            except:
                pass
        else:
            await message.reply("Fronting member cleared!")
        return True
        
    if target_short in system.get("members", {}):
        system["fronting_member"] = target_short
        save_plurality_data()
        if message.guild:
            try:
                await message.delete()
            except:
                pass
        else:
            disp = system["members"][target_short].get("display_name", target_short)
            await message.reply(f"Fronting member set to **{disp}** (`{target_short}`)!")
        return True
    else:
        members = system.get("members", {})
        if members:
            member_list = ", ".join([f"`{name}`" for name in members.keys()])
            await send_hidden_response(message, f"member `{target_short}` not found. Your members: {member_list}")
        else:
            await send_hidden_response(message, f"member `{target_short}` not found. You don't have any members registered yet!")
        return True

async def handle_plurality_message(message: discord.Message, client: discord.Client) -> bool:
    print(f"[Plurality Debug] on_message received: {repr(message.content)} in #{message.channel.name if message.channel else 'None'} (Type: {type(message.channel)})")
    if message.author.bot:
        print("[Plurality Debug] Ignored: author is a bot")
        return False
    if not message.guild:
        print("[Plurality Debug] Ignored: no guild")
        return False
    if not isinstance(message.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel)):
        print(f"[Plurality Debug] Ignored: channel is not a supported text channel type ({type(message.channel)})")
        return False

    cfg = get_guild_config(message.guild.id)
    plurality_enabled = cfg.get("plurality_enabled", False)
    print(f"[Plurality Debug] plurality_enabled status: {plurality_enabled}")
    if not plurality_enabled:
        return False

    if message.reference and message.reference.message_id:
        ref_msg_id = str(message.reference.message_id)
        if ref_msg_id in proxied_messages:
            msg_info = proxied_messages[ref_msg_id]
            if msg_info.get("author_id") == message.author.id:
                content = message.content.strip().lower()
                if content == "delete":
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await send_delete_confirmation(message, ref_msg_id, client)
                    return True
                elif content == "edit":
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await send_edit_confirmation(message, ref_msg_id, client)
                    return True

    user_id = str(message.author.id)
    print(f"[Plurality Debug] Message author ID: {user_id}")
    if user_id not in plurality_data:
        print("[Plurality Debug] Ignored: author ID not in plurality_data")
        return False

    system = plurality_data[user_id]
    content = message.content.strip()

    if not content:
        print("[Plurality Debug] Ignored: message content is empty")
        return False

    matched_member = None
    cleaned_content = content

    for short_name, member in system["members"].items():
        proxy_tag = member.get("proxy_tag")
        if not proxy_tag:
            continue

        parts = proxy_tag.split("text", 1)
        prefix = parts[0]
        suffix = parts[1] if len(parts) > 1 else ""

        if content.startswith(prefix) and content.endswith(suffix):
            matched_member = member
            cleaned_content = content[len(prefix):]
            if suffix:
                cleaned_content = cleaned_content[:-len(suffix)]
            print(f"[Plurality Debug] Matched member {short_name} via tag {proxy_tag}")
            break

    if not matched_member:
        fronting_short = system.get("fronting_member")
        print(f"[Plurality Debug] No tag matched. Fronting member: {fronting_short}")
        if fronting_short and fronting_short in system["members"]:
            matched_member = system["members"][fronting_short]
            cleaned_content = content
            print(f"[Plurality Debug] Auto-proxy matched fronting member: {fronting_short}")

    if not matched_member:
        print("[Plurality Debug] Ignored: no matched member and no fronting member")
        return False

    try:
        await message.delete()
        print("[Plurality Debug] Original message deleted successfully")
    except discord.Forbidden as e:
        print(f"[Plurality Error] Forbidden to delete message: {e}")
        await log_plurality_error(
            message.guild, 
            client, 
            f"Failed to delete original message for {message.author.mention} (`{message.author.id}`) in <#{message.channel.id}>. Discord API response: `{e}`. Make sure the bot has the 'Manage Messages' permission."
        )
        return True
    except discord.HTTPException as e:
        print(f"[Plurality Error] Failed to delete message: {e}")
        await log_plurality_error(
            message.guild, 
            client, 
            f"Failed to delete original message for {message.author.mention} (`{message.author.id}`) in <#{message.channel.id}>. Discord API response: `{e}`"
        )
        return True

    try:
        display_name = matched_member["display_name"]
        system_tag = system.get("system_tag")
        if system_tag:
            display_name = f"{display_name} {system_tag}"

        avatar_url = await resolve_avatar_url(message.guild, matched_member, client)

        reply_prefix = ""
        if message.reference and message.reference.message_id:
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                if ref_msg:
                    author_mention = ref_msg.author.mention
                    reply_prefix = f"**↳ Replying to** {author_mention} *([Jump to Message](<{ref_msg.jump_url}>))*\n"
            except Exception as e:
                print(f"[Plurality] Failed to fetch reply message: {e}")

        wh = await get_webhook_for_channel(message.channel)
        
        send_kwargs = {
            "content": f"{reply_prefix}{cleaned_content}",
            "username": display_name,
            "avatar_url": avatar_url
        }
        if isinstance(message.channel, discord.Thread):
            send_kwargs["thread"] = message.channel

        send_kwargs["wait"] = True
        sent_msg = await wh.send(**send_kwargs)
        if sent_msg and hasattr(sent_msg, "id"):
            add_proxied_message(
                msg_id=str(sent_msg.id),
                author_id=message.author.id,
                content=cleaned_content,
                reply_prefix=reply_prefix,
                channel_id=message.channel.id
            )
        print(f"[Plurality Debug] Webhook message sent successfully for member: {display_name}")
        return True
    except discord.Forbidden as e:
        print(f"[Plurality Error] Bot lacks 'Manage Webhooks' permission to send the webhook message: {e}")
        await log_plurality_error(
            message.guild, 
            client, 
            f"Failed to send webhook message in <#{message.channel.id}>. Discord API response: `{e}`. Make sure the bot has 'Manage Webhooks' permission."
        )
    except discord.NotFound:
        print("[Plurality Error] Webhook not found.")
        target_id = message.channel.parent_id if isinstance(message.channel, discord.Thread) else message.channel.id
        if target_id in webhook_cache:
            del webhook_cache[target_id]
    except discord.HTTPException as e:
        print(f"[Plurality Error] Webhook send failed: {e}")
        await log_plurality_error(
            message.guild, 
            client, 
            f"Failed to send webhook message in <#{message.channel.id}>. Discord API response: `{e}`"
        )
    return True


class PluralityConfigUserView(ui.View):
    def __init__(self, guild_id: int, user: discord.Member):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.refresh_items()

    def refresh_items(self):
        self.clear_items()
        user_id = str(self.user.id)
        
        has_system = user_id in plurality_data
        if not has_system:
            btn_reg = ui.Button(label="Register System", style=discord.ButtonStyle.success, row=0)
            btn_reg.callback = self.register_system
            self.add_item(btn_reg)
        else:
            system = plurality_data[user_id]
            members = system.get("members", {})
            
            if members:
                options = []
                front_options = []
                for short_name, m_info in list(members.items())[:25]:
                    disp = m_info.get("display_name", short_name)
                    options.append(discord.SelectOption(
                        label=disp,
                        value=short_name,
                        description=f"Short: {short_name} | Tag: {m_info.get('proxy_tag', 'None')}"
                    ))
                    is_front = system.get("fronting_member") == short_name
                    front_options.append(discord.SelectOption(
                        label=disp,
                        value=short_name,
                        emoji="" if is_front else None,
                        description=f"Set {disp} as fronting member"
                    ))
                
                # Add Option to clear fronting
                front_options.append(discord.SelectOption(
                    label="Clear Fronting",
                    value="clear_fronting",
                    emoji="",
                    description="Clear current fronting member"
                ))
                
                select = ui.Select(placeholder="Select a Member to manage...", options=options, row=0)
                select.callback = self.select_member
                self.add_item(select)
                
                select_front = ui.Select(placeholder="Quick Set Fronting...", options=front_options, row=1)
                select_front.callback = self.quick_set_fronting
                self.add_item(select_front)
                
            btn_add = ui.Button(label="Add Member", style=discord.ButtonStyle.primary, row=2)
            btn_add.callback = self.add_member
            self.add_item(btn_add)
            
            btn_rename = ui.Button(label="Rename System", style=discord.ButtonStyle.secondary, row=2)
            btn_rename.callback = self.rename_system
            self.add_item(btn_rename)

            btn_tag = ui.Button(label="Set System Tag", style=discord.ButtonStyle.secondary, row=2)
            btn_tag.callback = self.set_system_tag
            self.add_item(btn_tag)
            
            btn_delete = ui.Button(label="Delete System", style=discord.ButtonStyle.danger, row=2)
            btn_delete.callback = self.delete_system
            self.add_item(btn_delete)
            
        btn_back = ui.Button(label="Back to Dashboard", style=discord.ButtonStyle.danger, row=3)
        btn_back.callback = self.back_to_dashboard
        self.add_item(btn_back)

    def build_embed(self) -> discord.Embed:
        user_id = str(self.user.id)
        cfg = get_guild_config(self.guild_id)
        plurality_enabled = cfg.get("plurality_enabled", False)
        
        embed = discord.Embed(
            title="Plurality Profile Manager",
            color=discord.Color.blurple()
        )
        
        status_note = ""
        if not plurality_enabled:
            status_note = "\n*Note: Plurality message proxying is currently disabled by admins in this server.*"
            
        if user_id not in plurality_data:
            embed.description = (
                "You do not have a plurality system registered yet.\n\n"
                "Registering a system allows you to define different identity profiles (members) "
                "with custom names and avatars. When you send a message with your configured proxy tag, "
                "the bot will replace your message using webhooks to match the member's identity!"
                f"{status_note}"
            )
        else:
            system = plurality_data[user_id]
            system_name = system.get("system_name", "Unnamed System")
            system_tag = system.get("system_tag", "None")
            fronting_short = system.get("fronting_member")
            fronting_name = "None"
            if fronting_short and fronting_short in system["members"]:
                fronting_name = system["members"][fronting_short].get("display_name", fronting_short)
            members = system.get("members", {})
            
            desc = (
                f"**System Name:** {system_name}\n"
                f"**System Tag:** {system_tag}\n"
                f"**Fronting Member:** {fronting_name}\n"
                f"**Total Members:** {len(members)}\n"
                f"{status_note}\n\n"
                "**Your Members:**\n"
            )
            if not members:
                desc += "*No members registered yet. Click 'Add Member' to create one!*"
            else:
                for idx, (short_name, m_info) in enumerate(members.items()):
                    disp = m_info.get("display_name", short_name)
                    tag = m_info.get("proxy_tag", "*No tag set*")
                    has_av = "Yes" if m_info.get("avatar_url") else "No"
                    desc += f"{idx+1}. **{disp}** (`{short_name}`) — Tag: `{tag}` | Avatar: `{has_av}`\n"
            embed.description = desc
            
        return embed

    async def register_system(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PluralityRegisterSystemModal(self))

    async def add_member(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PluralityAddMemberModal(self))

    async def rename_system(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PluralityRenameSystemModal(self))

    async def set_system_tag(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PluralitySetSystemTagModal(self))

    async def delete_system(self, interaction: discord.Interaction):
        confirm_view = PluralityConfirmDeleteSystemView(self.guild_id, self.user)
        embed = confirm_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=confirm_view)

    async def select_member(self, interaction: discord.Interaction):
        short_name = interaction.data["values"][0]
        member_view = PluralityMemberDetailView(self.guild_id, self.user, short_name)
        embed = member_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=member_view)

    async def quick_set_fronting(self, interaction: discord.Interaction):
        user_id = str(self.user.id)
        if user_id not in plurality_data:
            await interaction.response.send_message("You don't have a system created yet.", ephemeral=True)
            return
            
        select_val = interaction.data["values"][0]
        if select_val == "clear_fronting":
            plurality_data[user_id]["fronting_member"] = None
        else:
            plurality_data[user_id]["fronting_member"] = select_val
            
        save_plurality_data()
        
        self.refresh_items()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def back_to_dashboard(self, interaction: discord.Interaction):
        from admin_ui_module import UserDashboardView
        dashboard = UserDashboardView(self.guild_id, self.user)
        embed = await dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

class PluralityRegisterSystemModal(ui.Modal, title="Register Plural System"):
    system_name = ui.TextInput(label="System Name", placeholder="e.g. The Cosmos System", required=True, max_length=100)
    
    def __init__(self, parent_view: PluralityConfigUserView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(self.parent_view.user.id)
        plurality_data[user_id] = {
            "system_name": self.system_name.value,
            "members": {}
        }
        save_plurality_data()
        self.parent_view.refresh_items()
        embed = self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class PluralityRenameSystemModal(ui.Modal, title="Rename Plural System"):
    system_name = ui.TextInput(label="New System Name", placeholder="e.g. The Nebula System", required=True, max_length=100)
    
    def __init__(self, parent_view: PluralityConfigUserView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(self.parent_view.user.id)
        if user_id in plurality_data:
            plurality_data[user_id]["system_name"] = self.system_name.value
            save_plurality_data()
        self.parent_view.refresh_items()
        embed = self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class PluralitySetSystemTagModal(ui.Modal, title="Set System Tag"):
    system_tag = ui.TextInput(label="System Tag (appended to display names)", placeholder="e.g. [SYS] or | Cosmos", required=False, max_length=20)
    
    def __init__(self, parent_view: PluralityConfigUserView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(self.parent_view.user.id)
        if user_id in plurality_data:
            val = self.system_tag.value.strip() or None
            plurality_data[user_id]["system_tag"] = val
            save_plurality_data()
        self.parent_view.refresh_items()
        embed = self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class PluralityAddMemberModal(ui.Modal, title="Add Member"):
    short_name = ui.TextInput(label="Short Name / Key", placeholder="e.g. m1 (no spaces)", required=True, max_length=20)
    display_name = ui.TextInput(label="Display Name", placeholder="e.g. Member One", required=True, max_length=80)
    
    def __init__(self, parent_view: PluralityConfigUserView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(self.parent_view.user.id)
        if user_id not in plurality_data:
            await interaction.response.send_message("System not found.", ephemeral=True)
            return
            
        short = self.short_name.value.strip().lower()
        if not short:
            await interaction.response.send_message("Invalid short name.", ephemeral=True)
            return
            
        system = plurality_data[user_id]
        if short in system["members"]:
            await interaction.response.send_message(f"Member with short name '{short}' already exists.", ephemeral=True)
            return
            
        system["members"][short] = {
            "display_name": self.display_name.value,
            "avatar_url": None,
            "proxy_tag": None
        }
        save_plurality_data()
        self.parent_view.refresh_items()
        embed = self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class PluralityMemberDetailView(ui.View):
    def __init__(self, guild_id: int, user: discord.Member, short_name: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.short_name = short_name
        self.refresh_items()

    def refresh_items(self):
        self.clear_items()
        user_id = str(self.user.id)
        system = plurality_data.get(user_id, {})
        fronting = system.get("fronting_member") == self.short_name

        btn_disp = ui.Button(label="Edit Display Name", style=discord.ButtonStyle.secondary, row=0)
        btn_disp.callback = self.edit_display_name
        self.add_item(btn_disp)

        btn_tag = ui.Button(label="Edit Proxy Tag", style=discord.ButtonStyle.secondary, row=0)
        btn_tag.callback = self.edit_proxy_tag
        self.add_item(btn_tag)

        btn_av = ui.Button(label="Upload Avatar", style=discord.ButtonStyle.secondary, row=0)
        btn_av.callback = self.upload_avatar
        self.add_item(btn_av)

        if fronting:
            btn_front = ui.Button(label="Clear Fronting", style=discord.ButtonStyle.danger, row=1)
        else:
            btn_front = ui.Button(label="Set as Fronting", style=discord.ButtonStyle.success, row=1)
        btn_front.callback = self.toggle_fronting
        self.add_item(btn_front)

        btn_del = ui.Button(label="Delete Member", style=discord.ButtonStyle.danger, row=1)
        btn_del.callback = self.delete_member
        self.add_item(btn_del)

        btn_back = ui.Button(label="Back", style=discord.ButtonStyle.danger, row=1)
        btn_back.callback = self.back
        self.add_item(btn_back)

    def build_embed(self) -> discord.Embed:
        user_id = str(self.user.id)
        system = plurality_data.get(user_id, {})
        member_info = system.get("members", {}).get(self.short_name, {})
        fronting = system.get("fronting_member") == self.short_name
        
        embed = discord.Embed(
            title=f"Member Profile: {member_info.get('display_name', self.short_name)}",
            color=discord.Color.blurple()
        )
        avatar_val = member_info.get('avatar_url')
        avatar_msg_id = member_info.get('avatar_msg_id')
        if avatar_msg_id:
            avatar_str = "Uploaded to Discord Storage (Active)"
        else:
            avatar_str = "Uploaded to server" if avatar_val and not avatar_val.startswith("http") else (avatar_val or 'Not Set')
        fronting_str = "Yes" if fronting else "No"
        
        embed.description = (
            f"**Short Name:** `{self.short_name}`\n"
            f"**Display Name:** {member_info.get('display_name', 'None')}\n"
            f"**Proxy Tag:** `{member_info.get('proxy_tag') or 'Not Set'}`\n"
            f"**Avatar:** {avatar_str}\n"
            f"**Fronting:** {fronting_str}\n\n"
            "*Tips: Proxy tags should contain the word 'text' to indicate where your message body goes, e.g. `[text]` or `m:text`.*"
        )
        return embed

    async def edit_display_name(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PluralityEditMemberDisplayNameModal(self))

    async def edit_proxy_tag(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PluralityEditMemberProxyModal(self))

    async def upload_avatar(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Please upload or send your avatar image in this channel within the next 60 seconds. "
            "Make sure it is sent as a message attachment.",
            ephemeral=True
        )
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.attachments
            
        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=60.0)
            attachment = msg.attachments[0]
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                await interaction.followup.send("Invalid file type. Please upload an image file.", ephemeral=True)
            else:
                await interaction.followup.send("Saving avatar... Please wait.", ephemeral=True)
                
                # Upload to our hidden avatars channel
                avatar_chan = await get_or_create_avatar_channel(interaction.guild, interaction.client)
                file = await attachment.to_file()
                avatar_msg = await avatar_chan.send(
                    content=f"Avatar for user {interaction.user.id}, member {self.short_name}",
                    file=file
                )
                
                user_id = str(self.user.id)
                plurality_data[user_id]["members"][self.short_name]["avatar_msg_id"] = avatar_msg.id
                plurality_data[user_id]["members"][self.short_name]["avatar_chan_id"] = avatar_chan.id
                plurality_data[user_id]["members"][self.short_name]["avatar_url"] = None
                save_plurality_data()
                
                await interaction.followup.send("Avatar uploaded and saved successfully!", ephemeral=True)
                
                try:
                    await msg.delete()
                except Exception:
                    pass
                    
                embed = self.build_embed()
                await interaction.message.edit(embed=embed, view=self)
        except asyncio.TimeoutError:
            await interaction.followup.send("Upload timed out.", ephemeral=True)

    async def toggle_fronting(self, interaction: discord.Interaction):
        user_id = str(self.user.id)
        if user_id in plurality_data:
            current = plurality_data[user_id].get("fronting_member")
            if current == self.short_name:
                plurality_data[user_id]["fronting_member"] = None
            else:
                plurality_data[user_id]["fronting_member"] = self.short_name
            save_plurality_data()
            self.refresh_items()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    async def delete_member(self, interaction: discord.Interaction):
        user_id = str(self.user.id)
        if user_id in plurality_data and self.short_name in plurality_data[user_id]["members"]:
            del plurality_data[user_id]["members"][self.short_name]
            # If deleted member was fronting, clear it
            if plurality_data[user_id].get("fronting_member") == self.short_name:
                plurality_data[user_id]["fronting_member"] = None
            save_plurality_data()
            
        parent = PluralityConfigUserView(self.guild_id, self.user)
        embed = parent.build_embed()
        await interaction.response.edit_message(embed=embed, view=parent)

    async def back(self, interaction: discord.Interaction):
        parent = PluralityConfigUserView(self.guild_id, self.user)
        embed = parent.build_embed()
        await interaction.response.edit_message(embed=embed, view=parent)

class PluralityEditMemberDisplayNameModal(ui.Modal, title="Edit Display Name"):
    display_name = ui.TextInput(label="Display Name", placeholder="e.g. Member One", required=True, max_length=80)
    
    def __init__(self, parent_view: PluralityMemberDetailView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(self.parent_view.user.id)
        if user_id in plurality_data and self.parent_view.short_name in plurality_data[user_id]["members"]:
            plurality_data[user_id]["members"][self.parent_view.short_name]["display_name"] = self.display_name.value
            save_plurality_data()
        embed = self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class PluralityEditMemberProxyModal(ui.Modal, title="Edit Proxy Tag"):
    proxy_tag = ui.TextInput(label="Proxy Tag (must contain 'text')", placeholder="e.g. [text]", required=True, max_length=40)
    
    def __init__(self, parent_view: PluralityMemberDetailView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(self.parent_view.user.id)
        tag = self.proxy_tag.value.strip()
        if "text" not in tag:
            await interaction.response.send_message("Proxy tag must contain the word 'text' (e.g. '[text]', 'm:text').", ephemeral=True)
            return
            
        if user_id in plurality_data and self.parent_view.short_name in plurality_data[user_id]["members"]:
            display_name = plurality_data[user_id]["members"][self.parent_view.short_name]["display_name"]
            if len(display_name) + len(tag) > 80:
                await interaction.response.send_message("Display name and proxy tag combined length must be 80 characters or fewer.", ephemeral=True)
                return
            plurality_data[user_id]["members"][self.parent_view.short_name]["proxy_tag"] = tag
            save_plurality_data()
        embed = self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class PluralityConfirmDeleteSystemView(ui.View):
    def __init__(self, guild_id: int, user: discord.Member):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Delete Plurality System?",
            description="Are you absolutely sure you want to delete your plurality system registration? This will delete all registered members and settings. This action is irreversible.",
            color=discord.Color.red()
        )
        return embed

    @ui.button(label="Yes, Delete System", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(self.user.id)
        if user_id in plurality_data:
            del plurality_data[user_id]
            save_plurality_data()
        parent = PluralityConfigUserView(self.guild_id, self.user)
        embed = parent.build_embed()
        await interaction.response.edit_message(embed=embed, view=parent)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        parent = PluralityConfigUserView(self.guild_id, self.user)
        embed = parent.build_embed()
        await interaction.response.edit_message(embed=embed, view=parent)


proxied_messages: dict[str, dict] = {}

def load_proxied_messages():
    global proxied_messages
    proxied_messages.clear()
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM proxied_messages;")
        rows = cursor.fetchall()
        for r in rows:
            m_id = r["message_id"]
            proxied_messages[m_id] = {
                "author_id": r["author_id"],
                "content": r["content"],
                "reply_prefix": r["reply_prefix"],
                "channel_id": r["channel_id"],
                "timestamp": r["timestamp"]
            }
    except Exception as e:
        print(f"Error loading proxied messages: {e}")

def save_proxied_messages():
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Rewrite all messages to keep clean
        cursor.execute("DELETE FROM proxied_messages;")
        for m_id, v in proxied_messages.items():
            cursor.execute("""
            INSERT OR REPLACE INTO proxied_messages (message_id, author_id, content, reply_prefix, channel_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (m_id, v["author_id"], v["content"], v["reply_prefix"], v["channel_id"], v["timestamp"]))
        conn.commit()
    except Exception as e:
        print(f"Error saving proxied messages: {e}")

def add_proxied_message(msg_id: str, author_id: int, content: str, reply_prefix: str, channel_id: int):
    import time
    now = time.time()
    
    # Prune old messages (> 24 hours) from local memory
    keys_to_remove = []
    for k, v in proxied_messages.items():
        if now - v.get("timestamp", 0) > 86400:
            keys_to_remove.append(k)
    for k in keys_to_remove:
        proxied_messages.pop(k, None)
        
    # Restrict map size to 1000 in memory
    if len(proxied_messages) >= 1000:
        sorted_items = sorted(proxied_messages.items(), key=lambda item: item[1].get("timestamp", 0))
        num_to_remove = len(proxied_messages) - 999
        for i in range(num_to_remove):
            proxied_messages.pop(sorted_items[i][0], None)
            
    proxied_messages[msg_id] = {
        "author_id": author_id,
        "content": content,
        "reply_prefix": reply_prefix,
        "channel_id": channel_id,
        "timestamp": now
    }
    
    # Fast save to SQLite
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Fast write message
        cursor.execute("""
        INSERT OR REPLACE INTO proxied_messages (message_id, author_id, content, reply_prefix, channel_id, timestamp)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (msg_id, author_id, content, reply_prefix, channel_id, now))
        
        # Prune DB messages older than 24 hours or if DB row count is too large
        cursor.execute("DELETE FROM proxied_messages WHERE ? - timestamp > 86400;", (now,))
        conn.commit()
    except Exception as e:
        print(f"Error executing fast save for proxied message in DB: {e}")

load_proxied_messages()


class PluralityDeleteConfirmView(ui.View):
    def __init__(self, user: discord.Member, webhook_msg_id: str, client: discord.Client):
        super().__init__(timeout=60.0)
        self.user = user
        self.webhook_msg_id = webhook_msg_id
        self.client = client
        self.message = None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass

    @ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("You are not allowed to interact with this button.", ephemeral=True)
            return

        msg_info = proxied_messages.get(self.webhook_msg_id)
        if msg_info:
            channel_id = msg_info["channel_id"]
            try:
                channel = self.client.get_channel(channel_id) or await self.client.fetch_channel(channel_id)
                if channel:
                    wh = await get_webhook_for_channel(channel)
                    if wh:
                        kwargs = {}
                        if isinstance(channel, discord.Thread):
                            kwargs["thread"] = channel
                        await wh.delete_message(int(self.webhook_msg_id), **kwargs)
            except Exception as e:
                print(f"[Plurality Error] Failed to delete proxied message: {e}")

            if self.webhook_msg_id in proxied_messages:
                del proxied_messages[self.webhook_msg_id]
                save_proxied_messages()

        try:
            await interaction.message.delete()
        except Exception:
            pass

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("You are not allowed to interact with this button.", ephemeral=True)
            return

        try:
            await interaction.message.delete()
        except Exception:
            pass


class PluralityEditConfirmView(ui.View):
    def __init__(self, user: discord.Member, webhook_msg_id: str, client: discord.Client):
        super().__init__(timeout=60.0)
        self.user = user
        self.webhook_msg_id = webhook_msg_id
        self.client = client
        self.message = None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass

    @ui.button(label="Edit", style=discord.ButtonStyle.primary)
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("You are not allowed to interact with this button.", ephemeral=True)
            return

        msg_info = proxied_messages.get(self.webhook_msg_id)
        if not msg_info:
            await interaction.response.send_message("Message not found or no longer editable.", ephemeral=True)
            try:
                await interaction.message.delete()
            except Exception:
                pass
            return

        modal = PluralityEditMessageModal(self.webhook_msg_id, msg_info["content"], self.client, self.message)
        await interaction.response.send_modal(modal)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("You are not allowed to interact with this button.", ephemeral=True)
            return

        try:
            await interaction.message.delete()
        except Exception:
            pass


class PluralityEditMessageModal(ui.Modal, title="Edit Proxied Message"):
    def __init__(self, webhook_msg_id: str, current_content: str, client: discord.Client, confirm_message: discord.Message):
        super().__init__()
        self.webhook_msg_id = webhook_msg_id
        self.client = client
        self.confirm_message = confirm_message
        
        self.content_input = ui.TextInput(
            label="Edit your message content",
            style=discord.TextStyle.paragraph,
            default=current_content,
            required=True,
            max_length=2000
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        msg_info = proxied_messages.get(self.webhook_msg_id)
        if not msg_info:
            await interaction.response.send_message("Message info not found.", ephemeral=True)
            return

        new_text = self.content_input.value
        channel_id = msg_info["channel_id"]
        
        try:
            channel = self.client.get_channel(channel_id) or await self.client.fetch_channel(channel_id)
            if channel:
                wh = await get_webhook_for_channel(channel)
                if wh:
                    kwargs = {
                        "content": f"{msg_info.get('reply_prefix', '')}{new_text}"
                    }
                    if isinstance(channel, discord.Thread):
                        kwargs["thread"] = channel
                    await wh.edit_message(int(self.webhook_msg_id), **kwargs)
                    proxied_messages[self.webhook_msg_id]["content"] = new_text
                    save_proxied_messages()
                    await interaction.response.send_message("Message edited successfully!", ephemeral=True)
                else:
                    await interaction.response.send_message("Webhook not found.", ephemeral=True)
            else:
                await interaction.response.send_message("Channel not found.", ephemeral=True)
        except Exception as e:
            print(f"[Plurality Error] Failed to edit message: {e}")
            await interaction.response.send_message(f"Failed to edit message: {e}", ephemeral=True)

        if self.confirm_message:
            try:
                await self.confirm_message.delete()
            except Exception:
                pass


async def send_delete_confirmation(message: discord.Message, webhook_msg_id: str, client: discord.Client):
    view = PluralityDeleteConfirmView(message.author, webhook_msg_id, client)
    conf_msg = await message.channel.send(
        content=f"{message.author.mention}, are you sure you want to delete this message?",
        view=view
    )
    view.message = conf_msg


async def send_edit_confirmation(message: discord.Message, webhook_msg_id: str, client: discord.Client):
    view = PluralityEditConfirmView(message.author, webhook_msg_id, client)
    conf_msg = await message.channel.send(
        content=f"{message.author.mention}, do you want to edit this message?",
        view=view
    )
    view.message = conf_msg
