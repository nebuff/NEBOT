import discord
from discord import ui, app_commands
import asyncio
from configuration_module import get_guild_config, save_config, refresh_interaction, log_setting_change_task

# Character translation mappings for different unicode fonts
FONTS_DATA = {
    "small_caps": {
        "lower": "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ",
        "upper": "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"
    },
    "bold": {
        "lower": "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳",
        "upper": "𝐀𝐁𝐂registered_bold_placeholder_DFGHIJKLMNOPQRSTUVWXYZ" # Let's write the correct bold mapping
    },
    "sans_bold": {
        "lower": "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇",
        "upper": "𝗔𝗕Ｃ𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭"
    },
    "sans": {
        "lower": "𝖺𝖻𝖼𝖽𝖾𝖿𝗀𝗁𝗂𝗃𝗄𝗅𝗆𝗇𝗈𝗉𝗊𝗋𝗌𝗍𝗎𝗏𝗐𝗑𝗒𝗓",
        "upper": "𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹"
    },
    "italic": {
        "lower": "𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧",
        "upper": "𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍"
    },
    "circled": {
        "lower": "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ",
        "upper": "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"
    },
    "fullwidth": {
        "lower": "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
        "upper": "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    }
}

# Fix bold uppercase placeholder:
FONTS_DATA["bold"]["upper"] = "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎Ｐ𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗Ｙ𝐙"

# Construct reverse mapping to translate fancy unicode letters back to standard ASCII
MAP_FANCY_TO_ASCII = {}
ASCII_LOWER = "abcdefghijklmnopqrstuvwxyz"
ASCII_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

for font_name, maps in FONTS_DATA.items():
    for f_char, a_char in zip(maps["upper"], ASCII_UPPER):
        MAP_FANCY_TO_ASCII[ord(f_char)] = a_char
    for f_char, a_char in zip(maps["lower"], ASCII_LOWER):
        MAP_FANCY_TO_ASCII[ord(f_char)] = a_char

# Map common mathematical symbol variations
# e.g., mathematical bold/italic/sans characters span multiple unicode blocks
# We also map various unicode spaces to regular ASCII spaces
UNICODE_SPACES = [
    "\u2000", "\u2001", "\u2002", "\u2003", "\u2004", "\u2005", 
    "\u2006", "\u2007", "\u2008", "\u2009", "\u200a", "\u200b", 
    "\u3000", "\u202f", "\u205f"
]
for space_char in UNICODE_SPACES:
    MAP_FANCY_TO_ASCII[ord(space_char)] = " "

SPECIAL_SPACE = "\u2005"  # Four-per-em space (does not get collapsed or replaced with hyphen by Discord)

def to_ascii(text: str) -> str:
    """Converts fancy unicode characters back to standard ASCII characters."""
    if not text:
        return ""
    return text.translate(MAP_FANCY_TO_ASCII)

def to_font(text: str, font_name: str) -> str:
    """Converts standard ASCII characters to a target fancy unicode font style."""
    if font_name not in FONTS_DATA:
        return text
    
    maps = FONTS_DATA[font_name]
    trans_map = str.maketrans(
        ASCII_LOWER + ASCII_UPPER,
        maps["lower"] + maps["upper"]
    )
    return text.translate(trans_map)

def extract_core_name(name: str, left_to_strip: str = "", right_to_strip: str = "") -> str:
    """
    Extracts the core base name (actual letters) of a channel or category by stripping off
    configured prefixes/suffixes and leading/trailing decorative non-alphanumeric characters.
    """
    if not name:
        return "channel"
        
    name_ascii = to_ascii(name)
    left_ascii = to_ascii(left_to_strip)
    right_ascii = to_ascii(right_to_strip)
    
    # Strip exact match of left prefix in ASCII or original unicode
    if left_ascii and name_ascii.startswith(left_ascii):
        name_ascii = name_ascii[len(left_ascii):]
    elif left_to_strip and name.startswith(left_to_strip):
        name_ascii = to_ascii(name[len(left_to_strip):])
        
    # Strip exact match of right suffix in ASCII or original unicode
    if right_ascii and name_ascii.endswith(right_ascii):
        name_ascii = name_ascii[:-len(right_ascii)]
    elif right_to_strip and name.endswith(right_to_strip):
        name_ascii = to_ascii(name[:-len(right_to_strip)])
        
    # Now strip leading and trailing non-alphanumeric characters (decorations)
    # We keep internal alphanumeric, spaces, and hyphens/underscores
    start = 0
    while start < len(name_ascii) and not name_ascii[start].isalnum():
        start += 1
        
    end = len(name_ascii)
    while end > start and not name_ascii[end-1].isalnum():
        end -= 1
        
    core = name_ascii[start:end]
    
    # Fallback if the entire name was stripped
    if not core:
        # Strip simple spaces and return if anything remains
        core = name.strip()
        if not core:
            core = "channel"
            
    return core

def format_channel_name(base_name: str, left: str, right: str, font: str, is_text_channel: bool) -> str:
    """Formats a base name with the left prefix, right suffix, and selected font style."""
    if is_text_channel and font == "normal":
        # Standard ASCII lowercase with hyphens for text channels
        formatted_base = base_name.replace(" ", "-").lower()
        while "--" in formatted_base:
            formatted_base = formatted_base.replace("--", "-")
    else:
        formatted_base = base_name
        
    # Convert base name to selected font
    font_base = to_font(formatted_base, font)
    
    # Combine with left prefix and right suffix
    result = f"{left}{font_base}{right}"
    
    if is_text_channel:
        # Use SPECIAL_SPACE for text channels to preserve spaces in decorations
        result = result.replace(" ", SPECIAL_SPACE)
        # Clean up double hyphens that might arise
        while "--" in result:
            result = result.replace("--", "-")
            
    return result

async def rename_all_channels(guild: discord.Guild, cfg: dict) -> tuple[int, int, list[str]]:
    """
    Goes through all channels and categories in a guild and renames them according to config.
    Returns: (successful_count, total_count, error_messages)
    """
    left = cfg.get("auto_channel_namer_left", "")
    right = cfg.get("auto_channel_namer_right", "")
    font = cfg.get("auto_channel_namer_font", "normal")
    exclude_ids = cfg.get("auto_channel_namer_exclude_ids", [])
    
    success = 0
    total = 0
    errors = []
    
    # Get all categories and channels
    all_channels = []
    for cat in guild.categories:
        if cat.id not in exclude_ids:
            all_channels.append((cat, False)) # Categories support uppercase/spaces
            
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        if channel.id in exclude_ids:
            continue
            
        is_text = isinstance(channel, (discord.TextChannel, discord.ForumChannel, discord.StageChannel))
        all_channels.append((channel, is_text))
        
    total = len(all_channels)
    
    for channel, is_text in all_channels:
        # Check permissions first
        bot_member = guild.me
        permissions = channel.permissions_for(bot_member)
        
        if not permissions.manage_channels:
            errors.append(f"Permission denied to manage {channel.name} ({channel.id})")
            continue
            
        base_name = extract_core_name(channel.name, left, right)
        new_name = format_channel_name(base_name, left, right, font, is_text)
        
        # Only edit if name actually changes to avoid unnecessary rate limits
        if channel.name != new_name:
            try:
                await channel.edit(name=new_name)
                success += 1
                # Sleep a tiny bit to respect rate limits
                await asyncio.sleep(0.5)
            except discord.Forbidden:
                errors.append(f"Forbidden error on {channel.name} ({channel.id})")
            except discord.HTTPException as e:
                errors.append(f"HTTP error on {channel.name} ({channel.id}): {e.status} {e.message}")
        else:
            success += 1 # Name is already correct
            
    return success, total, errors

# --- Modals and Views for Administration Dashboard ---

class ChannelNamerPrefixSuffixModal(ui.Modal):
    def __init__(self, guild_id: int, mode: str):
        title_str = "Configure Left Prefix" if mode == "left" else "Configure Right Suffix"
        super().__init__(title=title_str)
        self.guild_id = guild_id
        self.mode = mode
        
        cfg = get_guild_config(guild_id)
        default_val = cfg.get(f"auto_channel_namer_{mode}", "")
        
        self.value_input = ui.TextInput(
            label="Prefix/Suffix Value",
            placeholder="Type decoration, e.g. | -↳- or [] (leave empty for none)",
            default=default_val,
            required=False,
            max_length=50
        )
        self.add_item(self.value_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        val = self.value_input.value or ""
        cfg = get_guild_config(self.guild_id)
        cfg[f"auto_channel_namer_{self.mode}"] = val
        save_config()
        
        log_setting_change_task(
            interaction.guild, 
            interaction.user, 
            f"Set Auto-Namer {self.mode} decoration to: `{val}`"
        )
        
        # Re-build dashboard and refresh
        dashboard = AutoChannelNamerDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await refresh_interaction(interaction, embed, view=dashboard)

class AutoChannelNamerDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(AutoChannelNamerFontSelect(guild_id))
        
    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        left = cfg.get("auto_channel_namer_left", "")
        right = cfg.get("auto_channel_namer_right", "")
        font = cfg.get("auto_channel_namer_font", "normal")
        exclude_count = len(cfg.get("auto_channel_namer_exclude_ids", []))
        
        embed = discord.Embed(
            title="Nebot Tool: Auto Channel Namer",
            description=(
                "Formats channel and category names to look professional and consistent.\n\n"
                "**How it works:**\n"
                "• Extracts the core letters of the channel name (stripping old prefixes and symbols).\n"
                "• Converts it to your chosen font style.\n"
                "• Adds your custom left and right decorations."
            ),
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Selected Font Style", value=font.replace("_", " ").title(), inline=True)
        embed.add_field(name="Left Prefix", value=f"`{left}`" if left else "*None*", inline=True)
        embed.add_field(name="Right Suffix", value=f"`{right}`" if right else "*None*", inline=True)
        embed.add_field(name="Excluded Channels", value=str(exclude_count), inline=True)
        
        preview_base = "music-discussion"
        preview_fmt = format_channel_name(preview_base, left, right, font, True)
        embed.add_field(name="Text Channel Preview", value=f"`# {preview_fmt}`", inline=False)
        
        return embed

    @ui.button(label="Configure Left Prefix", style=discord.ButtonStyle.secondary, row=0)
    async def set_left(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ChannelNamerPrefixSuffixModal(self.guild_id, "left"))

    @ui.button(label="Configure Right Suffix", style=discord.ButtonStyle.secondary, row=0)
    async def set_right(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ChannelNamerPrefixSuffixModal(self.guild_id, "right"))

    @ui.button(label="Run Bulk Rename Now", style=discord.ButtonStyle.success, row=2)
    async def run_rename(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        cfg = get_guild_config(self.guild_id)
        
        success, total, errors = await rename_all_channels(interaction.guild, cfg)
        
        log_setting_change_task(
            interaction.guild, 
            interaction.user, 
            f"Executed Auto-Namer bulk rename ({success}/{total} channels processed successfully)"
        )
        
        response_msg = f"Bulk renaming completed! Successfully processed {success} out of {total} channels."
        
        if errors:
            response_msg += (
                "\n\n️ **NEBOT Does not have full permission across all channels, "
                "Please give nebot administrator or permission to manage channels across all channels, "
                "or work will be incomplete**"
            )
            
        await interaction.followup.send(response_msg, ephemeral=True)
        
        embed = self.build_embed()
        await refresh_interaction(interaction, embed, view=self)

    @ui.button(label="Back to Tools", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        from admin_ui_module import ToolsView
        view = ToolsView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

class AutoChannelNamerFontSelect(ui.Select):
    def __init__(self, guild_id: int):
        cfg = get_guild_config(guild_id)
        current_font = cfg.get("auto_channel_namer_font", "normal")
        
        options = [
            discord.SelectOption(label="Normal (Lowercase)", value="normal", description="Standard lowercase ASCII letters"),
            discord.SelectOption(label="Small Caps", value="small_caps", description="ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡx..."),
            discord.SelectOption(label="Mathematical Bold", value="bold", description="𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱..."),
            discord.SelectOption(label="Mathematical Sans Bold", value="sans_bold", description="𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵ｉｊｋｌｍｎ𝗼ｐ𝗾𝗿𝘀𝘁𝘂..."),
            discord.SelectOption(label="Mathematical Sans", value="sans", description="𝖺𝖻𝖼𝖽𝖾𝖿𝗀𝗁𝗂𝗃𝗄𝗅𝗆𝗇𝗈𝗉𝗊𝗋𝗌𝗍𝗎..."),
            discord.SelectOption(label="Italic", value="italic", description="𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤..."),
            discord.SelectOption(label="Circled / Bubble", value="circled", description="ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠ..."),
            discord.SelectOption(label="Fullwidth", value="fullwidth", description="ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐ..."),
        ]
        
        for opt in options:
            if opt.value == current_font:
                opt.default = True
                break
                
        super().__init__(placeholder="Select Font Style...", min_values=1, max_values=1, options=options, row=1)
        self.guild_id = guild_id
        
    async def callback(self, interaction: discord.Interaction):
        font = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["auto_channel_namer_font"] = font
        save_config()
        
        log_setting_change_task(
            interaction.guild, 
            interaction.user, 
            f"Changed Auto-Namer font style to `{font}`"
        )
        
        if self.view:
            embed = self.view.build_embed()
            await refresh_interaction(interaction, embed, view=self.view)
        else:
            await interaction.response.send_message("Font style updated successfully.", ephemeral=True)

def setup_auto_channel_namer_commands(tree: app_commands.CommandTree):
    autochannelnamer_group = app_commands.Group(name="autochannelnamer", description="Auto Channel Namer Settings")

    @autochannelnamer_group.command(name="run", description="Run bulk channel and category renaming immediately")
    async def slash_autochannelnamer_run(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only command", ephemeral=True)
            
        from configuration_module import is_admin, get_guild_config
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        success, total, errors = await rename_all_channels(interaction.guild, cfg)
        
        response_msg = f"Bulk renaming completed! Successfully processed {success} out of {total} channels."
        if errors:
            response_msg += (
                "\n\n️ **NEBOT Does not have full permission across all channels, "
                "Please give nebot administrator or permission to manage channels across all channels, "
                "or work will be incomplete**"
            )
        await interaction.followup.send(response_msg, ephemeral=True)

    @autochannelnamer_group.command(name="config", description="Show Auto Channel Namer Dashboard")
    async def slash_autochannelnamer_config(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only command", ephemeral=True)
            
        from configuration_module import is_admin, get_guild_config
        cfg = get_guild_config(interaction.guild_id)
        if not is_admin(interaction.user, cfg):
            return await interaction.response.send_message("Permission denied", ephemeral=True)
            
        dashboard = AutoChannelNamerDashboard(interaction.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.send_message(embed=embed, view=dashboard, ephemeral=True)

    tree.add_command(autochannelnamer_group)
