import os
import sys
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Mock discord dependencies for importing and testing
class MockView:
    def __init__(self, *args, **kwargs):
        pass
    def add_item(self, item):
        pass

class MockButton:
    def __init__(self, *args, **kwargs):
        pass

class MockModal:
    def __init__(self, *args, **kwargs):
        pass
    def __init_subclass__(cls, **kwargs):
        pass
    def add_item(self, item):
        pass

class MockButtonDescriptor:
    def __init__(self, func, **kwargs):
        self.func = func
        self.style = kwargs.get("style")
        self.label = kwargs.get("label")
        self.row = kwargs.get("row")
    def __get__(self, instance, owner):
        if instance is None:
            return self
        class BoundMockButton:
            def __init__(self, desc, inst):
                self.desc = desc
                self.inst = inst
                self.style = desc.style
                self.label = desc.label
                self.row = desc.row
            def __call__(self, *args, **kwargs):
                return self.desc.func(self.inst, *args, **kwargs)
        return BoundMockButton(self, instance)

def mock_button_decorator(*args, **kwargs):
    def decorator(func):
        return MockButtonDescriptor(func, **kwargs)
    return decorator

class MockEmbedFooter:
    def __init__(self, text=None, icon_url=None):
        self.text = text
        self.icon_url = icon_url

class MockEmbed:
    def __init__(self, title=None, description=None, color=None, timestamp=None):
        self.title = title
        self.description = description
        self.color = color
        self.timestamp = timestamp
        self.fields = []
        self.footer = None
    def add_field(self, name, value, inline=True):
        self.fields.append({"name": name, "value": value, "inline": inline})
    def set_footer(self, text=None, icon_url=None):
        self.footer = MockEmbedFooter(text=text, icon_url=icon_url)

class MockSelect:
    def __init__(self, *args, **kwargs):
        pass

class MockRoleSelect:
    def __init__(self, *args, **kwargs):
        pass

class MockChannelSelect:
    def __init__(self, *args, **kwargs):
        pass

class MockUserSelect:
    def __init__(self, *args, **kwargs):
        pass

class MockMember:
    id = None
    guild_permissions = None
    roles = None
    name = None
    display_name = None
    mention = None
    created_at = None

class MockTextInput:
    def __init__(self, *args, **kwargs):
        self.value = kwargs.get("default", "")

class MockUser:
    pass

mock_discord = MagicMock()
mock_discord.Member = MockMember
mock_discord.User = MockUser
mock_discord.Embed = MockEmbed
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.ui.Button = MockButton
mock_discord.ui.Modal = MockModal
mock_discord.ui.Select = MockSelect
mock_discord.ui.RoleSelect = MockRoleSelect
mock_discord.ui.ChannelSelect = MockChannelSelect
mock_discord.ui.UserSelect = MockUserSelect
mock_discord.ui.TextInput = MockTextInput
mock_discord.ui.button = mock_button_decorator
mock_discord.app_commands = MagicMock()
mock_discord.ButtonStyle = MagicMock()
mock_discord.Color = MagicMock()

sys.modules['discord'] = mock_discord
sys.modules['discord.app_commands'] = mock_discord.app_commands
sys.modules['discord.ui'] = mock_discord.ui

mock_empty = MagicMock()
sys.modules['commands_registry_handlers_module'] = mock_empty
sys.modules['battle_module'] = mock_empty
sys.modules['minesweeper_module'] = mock_empty
sys.modules['editor_module'] = mock_empty
sys.modules['session_module'] = mock_empty
sys.modules['utility_module'] = mock_empty

import configuration_module

import automod_module
import join_filtering_module
import admin_ui_module

def run_async(coro):
    return asyncio.run(coro)

    configuration_module.guild_configs.clear()
    if os.path.exists(configuration_module.CONFIG_FILE):
        try:
            os.remove(configuration_module.CONFIG_FILE)
        except Exception:
            pass

def test_recommended_filters_defaults():
    configuration_module.load_config()
    
    # Check default recommended automod filters
    assert len(configuration_module.recommended_automod_filters) >= 3
    assert configuration_module.recommended_automod_filters[0]["name"] == "Profanity Filter"
    assert configuration_module.recommended_automod_filters[1]["name"] == "Invite Links"
    
    # Check default recommended join filters
    assert len(configuration_module.recommended_join_filters) >= 3
    assert configuration_module.recommended_join_filters[0]["name"] == "Spambot Gate"

def test_copy_recommended_automod_filters():
    configuration_module.load_config()
    
    view = automod_module.ManageRecommendedFiltersView(guild_id=123)
    view.selected_index = 0  # Profanity Filter
    
    interaction = MagicMock()
    interaction.guild.id = 123
    interaction.user = MagicMock()
    interaction.response.send_message = AsyncMock()
    
    run_async(view.add_selected(interaction, MagicMock()))
    
    cfg = configuration_module.get_guild_config(123)
    assert len(cfg["automod_filters"]) == 1
    assert cfg["automod_filters"][0]["name"] == "Profanity Filter"
    
    # Check add all
    view2 = automod_module.ManageRecommendedFiltersView(guild_id=123)
    run_async(view2.add_all(interaction, MagicMock()))
    cfg2 = configuration_module.get_guild_config(123)
    # Remaining 2 filters should be added, total should be 3
    assert len(cfg2["automod_filters"]) == 3

def test_copy_recommended_join_filters():
    configuration_module.load_config()
    
    view = join_filtering_module.ManageRecommendedJoinFiltersView(guild_id=123)
    view.selected_index = 0  # Spambot Gate
    
    interaction = MagicMock()
    interaction.guild.id = 123
    interaction.user = MagicMock()
    interaction.response.send_message = AsyncMock()
    
    run_async(view.add_selected(interaction, MagicMock()))
    
    cfg = configuration_module.get_guild_config(123)
    assert len(cfg["join_filters"]) == 1
    assert cfg["join_filters"][0]["name"] == "Spambot Gate"

def test_list_based_join_filtering():
    configuration_module.load_config()
    
    cfg = configuration_module.get_guild_config(123)
    cfg["join_filter_enabled"] = True
    cfg["join_filters"] = [
        {
            "id": "test_filter_1",
            "name": "Advertiser Gate",
            "enabled": True,
            "keywords": ["*nitro*"],
            "enforcement_action": "kick"
        }
    ]
    
    member = MagicMock()
    member.guild.id = 123
    member.id = 777
    member.name = "LegitUser"
    member.created_at = datetime.datetime.now(datetime.timezone.utc)
    
    # Should not match
    res = run_async(join_filtering_module.handle_member_join(member))
    assert res is False
    
    member.name = "Free_nitro_user"
    member.top_role.position = 1
    member.send = AsyncMock()
    member.kick = AsyncMock()
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    bot_member.guild_permissions.kick_members = True
    member.guild.me = bot_member
    
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        res2 = run_async(join_filtering_module.handle_member_join(member))
        assert res2 is True
        member.kick.assert_called_once()

def test_nebuff_recommended_filters_manager():
    configuration_module.load_config()
    
    view = admin_ui_module.NebuffRecommendedFiltersView()
    embed = view.build_embed()
    
    assert "Recommended Filters Manager" in embed.title
    
    # Verify no emojis in embed text
    assert "" not in embed.title and "" not in embed.title
    assert "️" not in embed.description

def test_automod_allowed_enclosure():
    # Test spacing-insensitive allowed enclosure: c u m b is allowed because cumb is allowed and cum is banned
    banned_pats = [(False, "cum", False, False)]
    allowed_pats = [(False, "cumb", False, False)]
    
    # Text: c u m b (with spaces)
    spaced_str = "c u m b"
    # Matches on spaced_str should allow it because both match using make_bypass_regex
    assert automod_module.has_unallowed_match(spaced_str, banned_pats, allowed_pats) is False
    
    # Text: c.u.m.b (with dots)
    dotted_str = "c u m b"
    assert automod_module.has_unallowed_match(dotted_str, banned_pats, allowed_pats) is False
    
    # Test Main coon/Maine Coon enclosure
    banned_coon = [(False, "coon", False, False)]
    allowed_coon = [(False, "maine coon", False, False)]
    spaced_coon = "m a i n e   c o o n"
    assert automod_module.has_unallowed_match(spaced_coon, banned_coon, allowed_coon) is False
    
    # Test repeating character matching: niiigggeeer is caught by nigger
    banned_nigger = [(False, "nigger", False, False)]
    repeated_nigger = "niiigggeeer"
    assert automod_module.has_unallowed_match(repeated_nigger, banned_nigger, []) is True
    
    # Test ciggarettes containing igga substring enclosure
    banned_igga = [(False, "igga", True, True)]
    allowed_cigg = [(False, "ciggarettes", False, False)]
    assert automod_module.has_unallowed_match("ciggarettes", banned_igga, allowed_cigg) is False

