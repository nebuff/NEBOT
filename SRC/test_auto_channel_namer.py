import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Mock discord dependencies
class MockView:
    def __init__(self, *args, **kwargs):
        pass
    def add_item(self, item):
        pass

class MockButton:
    def __init__(self, *args, **kwargs):
        pass

def mock_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

class MockSelect:
    def __init__(self, *args, **kwargs):
        pass

class MockCategoryChannel:
    guild = None
    name = ""
    id = 0
    async def edit(self, *args, **kwargs):
        pass

class MockTextChannel:
    guild = None
    name = ""
    id = 0
    async def edit(self, *args, **kwargs):
        pass

class MockVoiceChannel:
    guild = None
    name = ""
    id = 0
    async def edit(self, *args, **kwargs):
        pass

class MockForumChannel:
    guild = None
    name = ""
    id = 0
    async def edit(self, *args, **kwargs):
        pass

class MockStageChannel:
    guild = None
    name = ""
    id = 0
    async def edit(self, *args, **kwargs):
        pass

class MockForbidden(Exception):
    pass

class MockHTTPException(Exception):
    def __init__(self, response=None, message=None):
        self.status = 400
        self.message = message or "Mock error"
        super().__init__(self.message)

mock_discord = MagicMock()
mock_discord.CategoryChannel = MockCategoryChannel
mock_discord.TextChannel = MockTextChannel
mock_discord.VoiceChannel = MockVoiceChannel
mock_discord.ForumChannel = MockForumChannel
mock_discord.StageChannel = MockStageChannel
mock_discord.Forbidden = MockForbidden
mock_discord.HTTPException = MockHTTPException
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.ui.Button = MockButton
mock_discord.ui.Select = MockSelect
mock_discord.ui.button = mock_decorator
mock_discord.Color = MagicMock()
mock_discord.ButtonStyle = MagicMock()

class MockClient:
    def __init__(self, *args, **kwargs):
        self.user = MagicMock()
        self.user.id = 12345
    def event(self, func):
        return func

mock_discord.Client = MockClient

sys.modules['discord'] = mock_discord
sys.modules['discord.ui'] = mock_discord.ui
import discord

# Mock other custom modules that depend on raw sockets/aiohttp
mock_empty = MagicMock()
sys.modules['commands_registry_handlers_module'] = mock_empty
sys.modules['battle_module'] = mock_empty
sys.modules['minesweeper_module'] = mock_empty
sys.modules['editor_module'] = mock_empty
sys.modules['session_module'] = mock_empty
sys.modules['admin_ui_module'] = mock_empty
sys.modules['utility_module'] = mock_empty

import auto_channel_namer_module

def run_async(coro):
    return asyncio.run(coro)

def test_font_conversions():
    print("Testing font conversion functions to/from ASCII...")
    
    assert auto_channel_namer_module.to_ascii("ᴀʙᴄ") == "abc"
    assert auto_channel_namer_module.to_ascii("𝐚𝐛𝐜") == "abc"
    assert auto_channel_namer_module.to_ascii("ⒶⒷⒸ") == "ABC"
    assert auto_channel_namer_module.to_ascii("hello") == "hello"
    
    # Test unicode spaces to ASCII spaces
    assert auto_channel_namer_module.to_ascii("a\u2005b") == "a b"
    
    assert auto_channel_namer_module.to_font("abc", "small_caps") == "ᴀʙᴄ"
    assert auto_channel_namer_module.to_font("abc", "bold") == "𝐚𝐛𝐜"
    assert auto_channel_namer_module.to_font("ABC", "circled") == "ⒶⒷⒸ"
    assert auto_channel_namer_module.to_font("abc", "unknown_font") == "abc"
    
    print("Font conversion tests passed.")

def test_core_name_extraction():
    print("Testing core channel name extraction logic...")
    
    assert auto_channel_namer_module.extract_core_name("im-cute") == "im-cute"
    
    # Prefix stripping
    assert auto_channel_namer_module.extract_core_name("| -↳-im-cute", "| -↳-") == "im-cute"
    assert auto_channel_namer_module.extract_core_name("| -✦-VC-RW", "| -✦-") == "VC-RW"
    
    # Non-alphanumeric decoration stripping
    assert auto_channel_namer_module.extract_core_name("| -↳-im-cute") == "im-cute"
    assert auto_channel_namer_module.extract_core_name("| [] Voice One") == "Voice One"
    assert auto_channel_namer_module.extract_core_name("─── HQ ───") == "HQ"
    
    # Fallback
    assert auto_channel_namer_module.extract_core_name("   ") == "channel"
    assert auto_channel_namer_module.extract_core_name("") == "channel"
    
    print("Core name extraction tests passed.")

def test_format_channel_name():
    print("Testing channel formatting logic...")
    
    # Text channel, normal font: spaces replaced with hyphens, lowercase
    res_text_normal = auto_channel_namer_module.format_channel_name(
        "Voice One", "| -↳-", "", "normal", is_text_channel=True
    )
    # The normal spaces in prefix/suffix/base get replaced with SPECIAL_SPACE (\u2005)
    # ASCII mapping will show it's formatted as expected
    assert "voice-one" in auto_channel_namer_module.to_ascii(res_text_normal)
    
    # Non-text channel (Voice/Category), small caps font
    res_voice_small_caps = auto_channel_namer_module.format_channel_name(
        "Voice One", "| -↳- ", "", "small_caps", is_text_channel=False
    )
    assert auto_channel_namer_module.to_ascii(res_voice_small_caps) == "| -↳- voice one"
    
    print("Channel formatting tests passed.")

def test_rename_all_channels_logic():
    print("Testing rename_all_channels bulk execution and permissions...")
    
    guild = MagicMock()
    guild.me = MagicMock()
    
    cat = MagicMock(spec=discord.CategoryChannel)
    cat.id = 1
    cat.name = "─── HQ ───"
    
    txt_ch = MagicMock(spec=discord.TextChannel)
    txt_ch.id = 2
    txt_ch.name = "| -↳-im-cute"
    txt_ch.edit = AsyncMock()
    
    # Channel with no permissions
    no_perm_ch = MagicMock(spec=discord.TextChannel)
    no_perm_ch.id = 3
    no_perm_ch.name = "| -↳-secret-chat"
    no_perm_ch.edit = AsyncMock()
    
    guild.categories = [cat]
    guild.channels = [txt_ch, no_perm_ch]
    
    # Set mock permissions
    def mock_permissions_for(member):
        perms = MagicMock()
        # Allow permissions for cat and txt_ch, but deny for no_perm_ch
        if member == guild.me:
            perms.manage_channels = True
        return perms
        
    cat.permissions_for = mock_permissions_for
    txt_ch.permissions_for = mock_permissions_for
    
    # Deny manage channels on no_perm_ch
    def no_perm_permissions_for(member):
        perms = MagicMock()
        perms.manage_channels = False
        return perms
    no_perm_ch.permissions_for = no_perm_permissions_for
    
    cfg = {
        "auto_channel_namer_enabled": True,
        "auto_channel_namer_left": "| -↳-",
        "auto_channel_namer_right": "",
        "auto_channel_namer_font": "normal",
        "auto_channel_namer_exclude_ids": []
    }
    
    success, total, errors = run_async(auto_channel_namer_module.rename_all_channels(guild, cfg))
    
    # Should successfully rename cat (since it's a category) and txt_ch
    # Should error/skip no_perm_ch due to permission checks
    # Total channels considered: 3 (1 cat + 2 txt channels)
    assert total == 3
    assert len(errors) == 1
    assert "Permission denied" in errors[0]
    
    print("Rename channels logic and permissions tests passed.")

if __name__ == "__main__":
    test_font_conversions()
    print("-" * 40)
    test_core_name_extraction()
    print("-" * 40)
    test_format_channel_name()
    print("-" * 40)
    test_rename_all_channels_logic()
    print("-" * 40)
    print("ALL AUTO CHANNEL NAMER LOGIC TESTS PASSED!")
