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

class MockRoleSelect:
    def __init__(self, *args, **kwargs):
        pass

class MockChannelSelect:
    def __init__(self, *args, **kwargs):
        pass

class MockUserSelect:
    def __init__(self, *args, **kwargs):
        pass

mock_discord = MagicMock()
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.ui.Button = MockButton
mock_discord.ui.RoleSelect = MockRoleSelect
mock_discord.ui.ChannelSelect = MockChannelSelect
mock_discord.ui.UserSelect = MockUserSelect
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

# Mock other custom modules that depend on raw sockets/aiohttp
mock_empty = MagicMock()
sys.modules['commands_registry_handlers_module'] = mock_empty
sys.modules['battle_module'] = mock_empty
sys.modules['minesweeper_module'] = mock_empty
sys.modules['editor_module'] = mock_empty
sys.modules['session_module'] = mock_empty
sys.modules['admin_ui_module'] = mock_empty
sys.modules['utility_module'] = mock_empty

import auto_roller_module

def run_async(coro):
    return asyncio.run(coro)

def test_auto_roller_join_logic():
    print("Testing auto-roller member join role assignment logic...")
    import main_entrypoint
    
    member = MagicMock()
    member.guild.id = 12345
    member.add_roles = AsyncMock()
    
    role_1 = MagicMock()
    role_1.id = 111
    role_1.position = 10
    
    role_2 = MagicMock()
    role_2.id = 222
    role_2.position = 20
    
    member.guild.get_role = MagicMock(side_effect=lambda rid: role_1 if rid == 111 else (role_2 if rid == 222 else None))
    
    bot_member = MagicMock()
    bot_member.top_role.position = 15
    member.guild.me = bot_member
    
    mock_config = {
        "auto_roller_enabled": True,
        "auto_roller_role_ids": [111, 222]
    }
    
    # Scenario 1: Enabled, only role_1 is below top role (position 10 < 15), role_2 is higher (20 >= 15)
    with patch("main_entrypoint.get_guild_config", return_value=mock_config):
        run_async(main_entrypoint.on_member_join(member))
        member.add_roles.assert_called_once_with(role_1)
        
    member.add_roles.reset_mock()
    
    # Scenario 2: Disabled
    mock_config["auto_roller_enabled"] = False
    with patch("main_entrypoint.get_guild_config", return_value=mock_config):
        run_async(main_entrypoint.on_member_join(member))
        member.add_roles.assert_not_called()
        
    print("Auto-roller join logic tests passed.")

def test_auto_roller_dashboard_views():
    print("Testing auto-roller dashboard view building and callback methods...")
    
    mock_config = {
        "auto_roller_enabled": False,
        "auto_roller_role_ids": [111]
    }
    
    dashboard = auto_roller_module.AutoRollerConfigDashboard(guild_id=12345)
    dashboard.refresh = AsyncMock()
    
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.response = AsyncMock()
    
    # Test Toggle Auto-Roller button click
    with patch("auto_roller_module.get_guild_config", return_value=mock_config), \
         patch("auto_roller_module.save_config") as mock_save:
        run_async(dashboard.toggle_auto_roller(interaction, MagicMock()))
        assert mock_config["auto_roller_enabled"] == True
        assert mock_save.called
        assert dashboard.refresh.called
        
    # Test Clear Auto-Roller Roles
    with patch("auto_roller_module.get_guild_config", return_value=mock_config), \
         patch("auto_roller_module.save_config") as mock_save:
        run_async(dashboard.clear_roles(interaction, MagicMock()))
        assert mock_config["auto_roller_role_ids"] == []
        assert mock_config["auto_roller_role_id"] is None
        assert mock_save.called
        assert dashboard.refresh.called

    # Test AutoRollerRolesSelect callback
    select = auto_roller_module.AutoRollerRolesSelect(guild_id=12345)
    select.view = MagicMock()
    select.view.refresh = AsyncMock()
    
    mock_role = MagicMock()
    mock_role.id = 555
    mock_role.name = "TestRole"
    select.values = [mock_role]
    
    with patch("auto_roller_module.get_guild_config", return_value=mock_config), \
         patch("auto_roller_module.save_config") as mock_save:
        run_async(select.callback(interaction))
        assert mock_config["auto_roller_role_ids"] == [555]
        assert mock_config["auto_roller_role_id"] == 555
        assert mock_save.called
        assert select.view.refresh.called
        
    print("Auto-roller dashboard views tests passed.")

def test_guild_join_welcome_dm():
    print("Testing bot guild join welcome DM logic...")
    import main_entrypoint
    
    guild = MagicMock()
    guild.name = "TestGuild"
    guild.owner_id = 99999
    
    owner = MagicMock()
    owner.send = AsyncMock()
    guild.owner = owner
    
    # Test when guild.owner is cached
    run_async(main_entrypoint.on_guild_join(guild))
    owner.send.assert_called_once()
    
    # Verify the message contents have no emojis
    sent_msg = owner.send.call_args[0][0]
    # Check for emojis or typical emoji patterns like :smile: or unicode emojis
    assert ":" not in sent_msg or "r:" in sent_msg or "a:" in sent_msg
    # Emojis regex range check
    for char in sent_msg:
        assert not (0x1F300 <= ord(char) <= 0x1F9FF or 0x2600 <= ord(char) <= 0x27BF)
        
    owner.send.reset_mock()
    
    # Test when guild.owner is not cached (None) and needs to be fetched via client
    guild.owner = None
    fetched_user = MagicMock()
    fetched_user.send = AsyncMock()
    
    main_entrypoint.client.fetch_user = AsyncMock(return_value=fetched_user)
    run_async(main_entrypoint.on_guild_join(guild))
    main_entrypoint.client.fetch_user.assert_called_once_with(99999)
    fetched_user.send.assert_called_once()
    
    print("Guild join welcome DM logic tests passed.")

if __name__ == "__main__":
    test_auto_roller_join_logic()
    print("-" * 40)
    test_auto_roller_dashboard_views()
    print("-" * 40)
    test_guild_join_welcome_dm()
    print("-" * 40)
    print("ALL AUTO-ROLLER LOGIC TESTS PASSED!")
