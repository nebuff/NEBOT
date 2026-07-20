import re
import discord

from configuration_module import get_guild_config

# 1 nebuff = 4 foot 6 inches = 54 inches
NEBUFF_INCHES = 54.0

async def handle_nebuff_message(message: discord.Message) -> bool:
    """
    Checks if a message contains a measurement and if the nebuff module is enabled.
    Returns True if a message was sent, False otherwise.
    """
    if message.author.bot or message.guild is None:
        return False

    cfg = get_guild_config(message.guild.id)
    if not cfg.get("nebuff_module_enabled", False):
        return False

    text = message.content.lower()

    # We will look for all possible matches and respond to the first valid one we find
    # First, check if they are speaking in nebuffs - convert to metric (meters)
    nebuff_pattern = r"(\d+(?:\.\d+)?)\s*(nebuffs?|nebuff's)\b"
    matches = list(re.finditer(nebuff_pattern, text))
    if matches:
        match = matches[0]
        val = float(match.group(1))
        # 1 nebuff = 54 inches = 1.3716 meters
        meters = val * 1.3716

        try:
            # We want to format this with up to 2 decimal places if needed, but not forcing it
            await message.reply(f"That would be {round(meters, 2)} meters")
            return True
        except discord.HTTPException:
            return False

    # Check for X'Y" (also supporting reversed quotes like X"Y')
    quote_pattern = r"(\d+)\s*['\"]\s*(\d+)(?:\s*(?:\"|'|in|inches|inch))?"
    matches = list(re.finditer(quote_pattern, text))
    if matches:
        match = matches[0]
        feet = float(match.group(1))
        inches = float(match.group(2))
        total_inches = feet * 12 + inches
        nebuffs = total_inches / NEBUFF_INCHES

        try:
            await message.reply(f"That would be {round(nebuffs, 2)} nebuff's")
            return True
        except discord.HTTPException:
            return False

    # Check for unit matches: f, ft, feet, m, meters, meter, cm, in, inches, inch
    unit_pattern = r"(\d+(?:\.\d+)?)\s*(cm|m|meter|meters|in|inches|inch|ft|feet|f)\b"
    matches = list(re.finditer(unit_pattern, text))
    if matches:
        match = matches[0]
        val = float(match.group(1))
        unit = match.group(2)
        total_inches = 0
        if unit == 'cm':
            total_inches = val / 2.54
        elif unit in ('m', 'meter', 'meters'):
            total_inches = val * 100 / 2.54
        elif unit in ('in', 'inches', 'inch'):
            total_inches = val
        elif unit in ('ft', 'feet', 'f'):
            total_inches = val * 12

        nebuffs = total_inches / NEBUFF_INCHES

        try:
            await message.reply(f"That would be {round(nebuffs, 2)} nebuff's")
            return True
        except discord.HTTPException:
            return False

    return False
