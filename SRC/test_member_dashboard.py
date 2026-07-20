import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Setup in-memory mock for discord modules
class MockView:
    def __init__(self, *args, **kwargs):
        self.children = []
    def add_item(self, item):
        self.children.append(item)
    def clear_items(self):
        self.children.clear()
    async def wait(self):
        pass
    def stop(self):
        pass

class MockButton:
    def __init__(self, *args, **kwargs):
        self.label = kwargs.get("label", "")
        self.style = kwargs.get("style", None)
        self.row = kwargs.get("row", 0)
class MockModal:
    def __init__(self, *args, **kwargs):
        pass
    def __init_subclass__(cls, **kwargs):
        pass
    def add_item(self, item):
        pass

class MockMember:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.display_name = name
        self.guild = MagicMock()
        self.guild.id = 12345
        self.guild.name = "Test Guild"
        self.guild.voice_client = None

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    @property
    def display_avatar(self):
        mock_avatar = MagicMock()
        mock_avatar.url = "http://example.com/avatar.png"
        return mock_avatar

class MockEmbed:
    def __init__(self, *args, **kwargs):
        self.title = kwargs.get("title", None)
        self.description = kwargs.get("description", None)
        self.color = kwargs.get("color", None)
        self.fields = []
    def add_field(self, name, value, inline=True):
        self.fields.append({"name": name, "value": value, "inline": inline})
    def set_thumbnail(self, url):
        self.thumbnail_url = url

mock_discord = MagicMock()
mock_discord.Member = MockMember
mock_discord.Embed = MockEmbed
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.ui.Button = MockButton
mock_discord.ui.Modal = MockModal
mock_discord.ButtonStyle = MagicMock()
mock_discord.Color = MagicMock()

def mock_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

mock_discord.ui.button = mock_decorator
mock_discord.app_commands = MagicMock()
mock_discord.app_commands.describe = mock_decorator
mock_discord.app_commands.choices = mock_decorator

sys.modules['discord'] = mock_discord
sys.modules['discord.app_commands'] = mock_discord.app_commands
sys.modules['discord.ui'] = mock_discord.ui
sys.modules['discord.ext'] = MagicMock()
sys.modules['discord.ext.commands'] = MagicMock()

import pytest
from admin_ui_module import (
    UserDashboardView,
    MemberAnalyticsDashboardView,
    MemberMusicDashboardView,
    MemberGamesView,
    MemberStatsView
)
from plurality_module import (
    PluralityConfigUserView,
    plurality_data
)

@pytest.mark.asyncio
async def test_member_dashboard_build_embed():
    user = MockMember(12345, "john_doe")
    with patch("admin_ui_module.get_guild_config", return_value={"plurality_enabled": True, "music_enabled": True}):
        plurality_data.clear()
        dashboard = UserDashboardView(12345, user)
        embed = await dashboard.build_embed()
        assert embed.title == "Nebot Member Control Panel"
        assert "<@12345>" in embed.description
        assert len(dashboard.children) == 5

@pytest.mark.asyncio
async def test_plurality_config_user_view_unregistered():
    user = MockMember(12345, "john_doe")
    plurality_data.clear()
    
    with patch("plurality_module.get_guild_config", return_value={"plurality_enabled": True}):
        view = PluralityConfigUserView(12345, user)
        embed = view.build_embed()
        assert "You do not have a plurality system registered yet" in embed.description
        # Register System button is available
        assert len(view.children) == 2  # Register + Back to Dashboard

@pytest.mark.asyncio
async def test_plurality_config_user_view_registered():
    user = MockMember(12345, "john_doe")
    plurality_data["12345"] = {
        "system_name": "Nebula System",
        "members": {
            "m1": {
                "display_name": "Member One",
                "avatar_url": None,
                "proxy_tag": "[text]"
            }
        }
    }
    
    with patch("plurality_module.get_guild_config", return_value={"plurality_enabled": True}):
        view = PluralityConfigUserView(12345, user)
        embed = view.build_embed()
        assert "Nebula System" in embed.description
        assert "Member One" in embed.description
        # Has members select menu, add member, rename system, set system tag, delete system, back to dashboard
        assert len(view.children) == 6

@pytest.mark.asyncio
async def test_member_analytics_view():
    user = MockMember(12345, "john_doe")
    
    with patch("admin_ui_module.get_guild_config", return_value={"analytics_enabled": True}), \
         patch("analytics_module.load_analytics_records", new_callable=AsyncMock, return_value={}):
        view = MemberAnalyticsDashboardView(12345, user)
        embed = await view.build_embed()
        assert "Server Analytics Report" in embed.title
        assert len(view.children) == 2  # Toggle + Back

@pytest.mark.asyncio
async def test_member_music_view():
    user = MockMember(12345, "john_doe")
    
    with patch("admin_ui_module.get_guild_config", return_value={"music_enabled": True}):
        view = MemberMusicDashboardView(12345, user)
        embed = await view.build_embed()
        assert "Nebot Music Player" in embed.title
        assert len(view.children) == 2  # Play Song + Back (no active voice client)

@pytest.mark.asyncio
async def test_member_games_view():
    user = MockMember(12345, "john_doe")
    
    with patch("admin_ui_module.get_guild_config", return_value={"minesweeper_enabled": True, "battle_enabled": True}):
        view = MemberGamesView(12345, user)
        embed = view.build_embed()
        assert "Nebot Game Zone" in embed.title
