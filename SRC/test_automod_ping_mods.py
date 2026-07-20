import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Mock discord dependencies
class MockView:
    def __init__(self, *args, **kwargs): pass
    def add_item(self, item): pass

class MockButton:
    def __init__(self, *args, **kwargs): pass

class MockModal:
    def __init__(self, *args, **kwargs): pass
    def __init_subclass__(cls, **kwargs): pass
    def add_item(self, item): pass

class MockRoleSelect:
    def __init__(self, *args, **kwargs): pass

class MockChannelSelect:
    def __init__(self, *args, **kwargs): pass

class MockChannel:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.send = AsyncMock()

class MockMember:
    def __init__(self, id, name, roles=None):
        self.id = id
        self.name = name
        self.roles = roles or []
        self.mention = f"<@{id}>"
        self.timeout = AsyncMock()
        self.ban = AsyncMock()
        self.send = AsyncMock()
        self.bot = False

mock_discord = MagicMock()
mock_discord.Member = MockMember
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.ui.Button = MockButton
mock_discord.ui.Modal = MockModal
mock_discord.ui.RoleSelect = MockRoleSelect
mock_discord.ui.ChannelSelect = MockChannelSelect

def mock_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

mock_discord.ui.button = mock_decorator
mock_discord.ButtonStyle = MagicMock()
mock_discord.Color = MagicMock()
mock_discord.ChannelType = MagicMock()

sys.modules['discord'] = mock_discord
sys.modules['discord.ui'] = mock_discord.ui

mock_empty = MagicMock()
sys.modules['warning_tracker_module'] = mock_empty
sys.modules['utility_module'] = mock_empty

import automod_module

def run_async(coro):
    return asyncio.run(coro)

def test_ping_mods_logging_pings():
    print("Testing log_automod_ping_mods formatting and logging...")
    
    guild = MagicMock()
    guild.id = 777
    
    member = MockMember(12345, "offender")
    log_channel = MockChannel(999, "logs")
    
    guild.get_channel = MagicMock(return_value=log_channel)
    guild.fetch_channel = AsyncMock(return_value=log_channel)
    
    # Test when mod_role_id is configured
    with patch("automod_module.get_guild_config") as mock_cfg:
        mock_cfg.return_value = {
            "global_log_channel_id": 999,
            "mod_role_id": 4444,
            "admin_role_id": 5555
        }
        log_channel.send.reset_mock()
        run_async(automod_module.log_automod_ping_mods(guild, member, "FilterA", "bad word"))
        
        log_channel.send.assert_called_once()
        args, kwargs = log_channel.send.call_args
        assert "<@&4444>" in kwargs.get("content", "")
        
    # Test when only admin_role_id is configured
    with patch("automod_module.get_guild_config") as mock_cfg:
        mock_cfg.return_value = {
            "global_log_channel_id": 999,
            "mod_role_id": None,
            "admin_role_id": 5555
        }
        log_channel.send.reset_mock()
        run_async(automod_module.log_automod_ping_mods(guild, member, "FilterA", "bad word"))
        
        log_channel.send.assert_called_once()
        args, kwargs = log_channel.send.call_args
        assert "<@&5555>" in kwargs.get("content", "")
        
    # Test when no roles are configured (fallback to @here)
    with patch("automod_module.get_guild_config") as mock_cfg:
        mock_cfg.return_value = {
            "global_log_channel_id": 999,
            "mod_role_id": None,
            "admin_role_id": None
        }
        log_channel.send.reset_mock()
        run_async(automod_module.log_automod_ping_mods(guild, member, "FilterA", "bad word"))
        
        log_channel.send.assert_called_once()
        args, kwargs = log_channel.send.call_args
        assert "@here" in kwargs.get("content", "")
        
    print("log_automod_ping_mods tests passed.")

def test_precedence_weight():
    print("Testing precedence weight calculation...")
    
    message = MagicMock()
    message.guild.id = 777
    message.author = MockMember(123, "test_user")
    message.content = "badword"
    message.delete = AsyncMock()
    
    # Filter A has "Delete Message Only" (weight 1)
    # Filter B has "Delete + Alert Mods" (weight 2)
    # Since both match, B should win and trigger log_automod_ping_mods
    filters = [
        {
            "id": "1",
            "name": "Filter Delete Only",
            "enabled": True,
            "keywords": ["badword"],
            "enforcement_action": "Delete Message Only"
        },
        {
            "id": "2",
            "name": "Filter Alert Mods",
            "enabled": True,
            "keywords": ["badword"],
            "enforcement_action": "Delete + Alert Mods"
        }
    ]
    
    with patch("automod_module.get_guild_config") as mock_cfg, \
         patch("automod_module.log_automod_ping_mods") as mock_ping_mods, \
         patch("automod_module.notify_user_privately") as mock_notify:
        
        mock_cfg.return_value = {
            "automod_enabled": True,
            "automod_filters": filters
        }
        mock_ping_mods.return_value = None
        mock_notify.return_value = None
        
        res = run_async(automod_module.handle_automod_message(message))
        assert res is True
        
        mock_ping_mods.assert_called_once_with(message.guild, message.author, "Filter Alert Mods", "badword")
        
    print("Precedence weight tests passed.")

def main():
    test_ping_mods_logging_pings()
    test_precedence_weight()
    print("ALL AUTOMOD PING MODS TESTS PASSED!")

if __name__ == "__main__":
    main()
