import os
import sys
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Define custom exception for mocking discord.Forbidden
class MockForbidden(Exception):
    pass

# Mock discord dependencies for importing and testing verification_module
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

def mock_button_decorator(*args, **kwargs):
    def decorator(func):
        return func
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
    mention = None

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
mock_discord.ui.button = mock_button_decorator
mock_discord.app_commands = MagicMock()
mock_discord.ButtonStyle = MagicMock()
mock_discord.Color = MagicMock()
mock_discord.Forbidden = MockForbidden

class MockClient:
    def __init__(self, *args, **kwargs):
        self.user = MagicMock()
        self.user.id = 12345
    def event(self, func):
        return func

mock_discord.Client = MockClient

sys.modules['discord'] = mock_discord
sys.modules['discord.app_commands'] = mock_discord.app_commands
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

import verification_module
from configuration_module import get_guild_config

# Configure test config file
import configuration_module

# Clean up any leftover test config file

def run_async(coro):
    return asyncio.run(coro)

def test_get_code_generation():
    print("Testing code generation and ephemeral prompt...")
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.user.id = 67890
    interaction.response = AsyncMock()
    
    # Enable verification in guild config
    cfg = get_guild_config(interaction.guild_id)
    cfg["verification_enabled"] = True
    cfg["verification_verified_role_id"] = 111
    cfg["verification_unverified_role_id"] = 222
    
    gate_view = verification_module.VerificationGateView()
    run_async(gate_view.get_code(interaction, None))
    
    cache_key = (interaction.guild_id, interaction.user.id)
    assert cache_key in verification_module.active_verification_codes
    
    correct_code, created_at = verification_module.active_verification_codes[cache_key]
    assert len(correct_code) == 4
    assert correct_code.isdigit()
    
    # Verify response send_message was called with code in description
    interaction.response.send_message.assert_called_once()
    args, kwargs = interaction.response.send_message.call_args
    embed = kwargs.get("embed")
    assert embed is not None
    assert f"'{correct_code}'" in embed.description
    print("Code generation test passed.")

def test_verification_success():
    print("Testing successful code selection verification flow...")
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.user.id = 67890
    interaction.response = AsyncMock()
    
    unverified_role = MagicMock()
    unverified_role.id = 222
    unverified_role.position = 1
    
    verified_role = MagicMock()
    verified_role.id = 111
    verified_role.position = 2
    
    member = MagicMock()
    member.name = "TestUser"
    member.roles = [unverified_role]
    member.edit = AsyncMock()
    interaction.user = member
    
    guild = MagicMock()
    guild.get_role = MagicMock(side_effect=lambda rid: verified_role if rid == 111 else unverified_role)
    
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    guild.me = bot_member
    interaction.guild = guild
    
    correct_code = "0742"  # Test leading zero conservation
    verification_module.active_verification_codes[(interaction.guild_id, interaction.user.id)] = (correct_code, time.time())
    
    select = verification_module.VerificationSelect(correct_code, [correct_code, "1111", "2222", "3333", "4444"])
        
    select.values = [correct_code]
    
    run_async(select.callback(interaction))
    
    # Session token must be flushed
    assert (interaction.guild_id, interaction.user.id) not in verification_module.active_verification_codes
    
    # Member edit should be called with correct roles
    member.edit.assert_called_once()
    called_roles = member.edit.call_args[1].get("roles")
    assert verified_role in called_roles
    assert unverified_role not in called_roles
    
    # Check successful response message
    interaction.response.edit_message.assert_called_once()
    kwargs = interaction.response.edit_message.call_args[1]
    assert "Verification successful!" in kwargs.get("content")
    print("Verification success test passed.")

def test_verification_failure():
    print("Testing incorrect code selection verification flow...")
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.user.id = 67890
    interaction.response = AsyncMock()
    
    correct_code = "0123"
    verification_module.active_verification_codes[(interaction.guild_id, interaction.user.id)] = (correct_code, time.time())
    
    select = verification_module.VerificationSelect(correct_code, [correct_code, "1111", "2222", "3333", "4444"])
    select.values = ["1111"]
    
    run_async(select.callback(interaction))
    
    # Session token must be flushed on failure too
    assert (interaction.guild_id, interaction.user.id) not in verification_module.active_verification_codes
    
    # Check failure response message
    interaction.response.edit_message.assert_called_once()
    kwargs = interaction.response.edit_message.call_args[1]
    assert "Verification failed." in kwargs.get("content")
    print("Verification failure test passed.")

def test_verification_expiry():
    print("Testing expired session verification flow...")
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.user.id = 67890
    interaction.response = AsyncMock()
    
    correct_code = "0123"
    verification_module.active_verification_codes[(interaction.guild_id, interaction.user.id)] = (correct_code, time.time() - 400)
    
    select = verification_module.VerificationSelect(correct_code, [correct_code, "1111", "2222", "3333", "4444"])
    select.values = [correct_code]
    
    run_async(select.callback(interaction))
    
    # Cache must be cleared
    assert (interaction.guild_id, interaction.user.id) not in verification_module.active_verification_codes
    
    # Check expiry response message
    interaction.response.edit_message.assert_called_once()
    kwargs = interaction.response.edit_message.call_args[1]
    assert "expired" in kwargs.get("content").lower()
    print("Verification expiry test passed.")

def test_hierarchy_failure():
    print("Testing hierarchy check failure flow...")
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.user.id = 67890
    interaction.response = AsyncMock()
    
    unverified_role = MagicMock()
    unverified_role.id = 222
    unverified_role.position = 10
    
    verified_role = MagicMock()
    verified_role.id = 111
    verified_role.position = 20  # Hierarchically too high
    
    member = MagicMock()
    member.name = "TestUser"
    member.roles = [unverified_role]
    member.edit = AsyncMock()
    interaction.user = member
    
    guild = MagicMock()
    guild.id = 12345
    guild.get_role = MagicMock(side_effect=lambda rid: verified_role if rid == 111 else unverified_role)
    
    # Bot top role is below the target role position
    bot_member = MagicMock()
    bot_member.top_role.position = 15  # Below verified_role position 20
    guild.me = bot_member
    interaction.guild = guild
    
    cfg = get_guild_config(interaction.guild_id)
    cfg["warning_log_channel_id"] = 99999
    log_channel = MagicMock()
    log_channel.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=log_channel)
    
    correct_code = "1234"
    verification_module.active_verification_codes[(interaction.guild_id, interaction.user.id)] = (correct_code, time.time())
    
    select = verification_module.VerificationSelect(correct_code, [correct_code, "1111"])
    select.values = [correct_code]
    
    run_async(select.callback(interaction))
    
    # Member.edit should NOT be called due to proactive check
    member.edit.assert_not_called()
    
    log_channel.send.assert_called_once()
    args, kwargs = log_channel.send.call_args
    embed = kwargs.get("embed")
    assert "Configuration Error" in embed.title
    
    # Response should notify user of server config error
    interaction.response.edit_message.assert_called_once()
    kwargs = interaction.response.edit_message.call_args[1]
    assert "configuration error" in kwargs.get("content").lower()
    print("Hierarchy failure test passed.")

def test_forbidden_role_swap():
    print("Testing Forbidden role swap exception flow...")
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.user.id = 67890
    interaction.response = AsyncMock()
    
    unverified_role = MagicMock()
    unverified_role.id = 222
    unverified_role.position = 1
    
    verified_role = MagicMock()
    verified_role.id = 111
    verified_role.position = 2
    
    member = MagicMock()
    member.name = "TestUser"
    member.roles = [unverified_role]
    member.edit = AsyncMock(side_effect=MockForbidden("Bot lacks permissions"))
    interaction.user = member
    
    guild = MagicMock()
    guild.id = 12345
    guild.get_role = MagicMock(side_effect=lambda rid: verified_role if rid == 111 else unverified_role)
    
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    guild.me = bot_member
    interaction.guild = guild
    
    cfg = get_guild_config(interaction.guild_id)
    cfg["warning_log_channel_id"] = 99999
    log_channel = MagicMock()
    log_channel.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=log_channel)
    
    correct_code = "1234"
    verification_module.active_verification_codes[(interaction.guild_id, interaction.user.id)] = (correct_code, time.time())
    
    select = verification_module.VerificationSelect(correct_code, [correct_code, "1111"])
    select.values = [correct_code]
    
    run_async(select.callback(interaction))
    
    log_channel.send.assert_called_once()
    args, kwargs = log_channel.send.call_args
    embed = kwargs.get("embed")
    assert "Configuration Error" in embed.title
    
    # Response should notify user of server config error
    interaction.response.edit_message.assert_called_once()
    kwargs = interaction.response.edit_message.call_args[1]
    assert "configuration error" in kwargs.get("content").lower()
    print("Forbidden role swap exception test passed.")

def test_on_member_join():
    print("Testing on_member_join event ping...")
    import main_entrypoint
    
    member = MagicMock()
    member.guild.id = 12345
    member.mention = "<@67890>"
    
    # Configure verification channel and enable verification
    cfg = get_guild_config(member.guild.id)
    cfg["verification_enabled"] = True
    cfg["verification_channel_id"] = 998877
    
    verify_channel = MagicMock()
    verify_channel.send = AsyncMock()
    
    member.guild.get_channel = MagicMock(return_value=verify_channel)
    
    run_async(main_entrypoint.on_member_join(member))
    
    # Verify that channel received the welcome ping message with delete_after=60
    verify_channel.send.assert_called_once()
    args, kwargs = verify_channel.send.call_args
    assert "<@67890>" in args[0]
    assert kwargs.get("delete_after") == 60
    print("on_member_join event ping test passed.")

def test_verification_success_fallback_log():
    print("Testing verification successful logging fallback to global log channel...")
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.user.id = 67890
    interaction.response = AsyncMock()
    
    unverified_role = MagicMock()
    unverified_role.id = 222
    unverified_role.position = 1
    
    verified_role = MagicMock()
    verified_role.id = 111
    verified_role.position = 2
    
    member = MagicMock()
    member.name = "TestUser"
    member.mention = "<@67890>"
    member.roles = [unverified_role]
    member.edit = AsyncMock()
    interaction.user = member
    
    guild = MagicMock()
    guild.get_role = MagicMock(side_effect=lambda rid: verified_role if rid == 111 else unverified_role)
    
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    guild.me = bot_member
    interaction.guild = guild
    
    # Setup configuration: verification_log_channel_id is None, fallback to global_log_channel_id
    cfg = get_guild_config(interaction.guild_id)
    cfg["verification_log_channel_id"] = None
    cfg["global_log_channel_id"] = 55555
    
    global_log_channel = MagicMock()
    global_log_channel.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=global_log_channel)
    
    correct_code = "0742"
    verification_module.active_verification_codes[(interaction.guild_id, interaction.user.id)] = (correct_code, time.time())
    
    select = verification_module.VerificationSelect(correct_code, [correct_code, "1111"])
    select.values = [correct_code]
    
    run_async(select.callback(interaction))
    
    # Verify fallback log channel received the verification log with clickable user mention
    global_log_channel.send.assert_called_once()
    args, kwargs = global_log_channel.send.call_args
    assert f"User {member.mention} has been verified" in args[0]
    print("Verification successful global fallback log test passed.")

def test_multiple_verified_roles():
    print("Testing multiple verified roles assignment flow...")
    interaction = MagicMock()
    interaction.guild_id = 12345
    interaction.user.id = 67890
    interaction.response = AsyncMock()
    
    unverified_role = MagicMock()
    unverified_role.id = 222
    unverified_role.position = 1
    
    role_1 = MagicMock()
    role_1.id = 111
    role_1.position = 2
    
    role_2 = MagicMock()
    role_2.id = 333
    role_2.position = 3
    
    member = MagicMock()
    member.name = "TestUser"
    member.roles = [unverified_role]
    member.edit = AsyncMock()
    interaction.user = member
    
    guild = MagicMock()
    guild.get_role = MagicMock(side_effect=lambda rid: role_1 if rid == 111 else (role_2 if rid == 333 else unverified_role))
    
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    guild.me = bot_member
    interaction.guild = guild
    
    # Configure test config with multiple verified role ids
    cfg = get_guild_config(interaction.guild_id)
    cfg["verification_verified_role_ids"] = [111, 333]
    cfg["verification_verified_role_id"] = None
    cfg["verification_unverified_role_id"] = 222
    
    correct_code = "0742"
    verification_module.active_verification_codes[(interaction.guild_id, interaction.user.id)] = (correct_code, time.time())
    
    select = verification_module.VerificationSelect(correct_code, [correct_code, "1111"])
    select.values = [correct_code]
    
    run_async(select.callback(interaction))
    
    member.edit.assert_called_once()
    called_roles = member.edit.call_args[1].get("roles")
    assert role_1 in called_roles
    assert role_2 in called_roles
    assert unverified_role not in called_roles
    print("Multiple verified roles flow test passed.")

def test_verification_dropdowns():
    print("Testing verification module dropdown settings...")
    mock_config = {
        "verification_unverified_role_id": None,
        "verification_verified_role_ids": [],
        "verification_verified_role_id": None,
        "verification_channel_id": None,
        "verification_landing_channel_id": None,
        "verification_log_channel_id": None,
    }

    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()

    # Unverified Role Select
    from verification_module import VerificationUnverifiedRoleSelect
    mock_role = MagicMock()
    mock_role.id = 123
    mock_role.name = "Unverified"

    sel_unver = VerificationUnverifiedRoleSelect(guild_id=777)
    sel_unver.view = MagicMock()
    sel_unver.view.refresh = AsyncMock()
    sel_unver.values = [mock_role]

    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(sel_unver.callback(interaction))
        assert mock_config["verification_unverified_role_id"] == 123
        assert mock_save.called
        assert sel_unver.view.refresh.called

    # Verified Roles Select
    from verification_module import VerificationVerifiedRolesSelect
    mock_role_v = MagicMock()
    mock_role_v.id = 456
    mock_role_v.name = "Verified"

    sel_ver = VerificationVerifiedRolesSelect(guild_id=777)
    sel_ver.view = MagicMock()
    sel_ver.view.refresh = AsyncMock()
    sel_ver.values = [mock_role_v]

    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(sel_ver.callback(interaction))
        assert mock_config["verification_verified_role_ids"] == [456]
        assert mock_config["verification_verified_role_id"] == 456
        assert mock_save.called
        assert sel_ver.view.refresh.called

    # Channel selects
    from verification_module import VerificationChannelSelect, VerificationLandingChannelSelect, VerificationLogChannelSelect
    mock_ch = MagicMock()
    mock_ch.id = 789

    sel_ch = VerificationChannelSelect(guild_id=777)
    sel_ch.view = MagicMock()
    sel_ch.view.refresh = AsyncMock()
    sel_ch.values = [mock_ch]

    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(sel_ch.callback(interaction))
        assert mock_config["verification_channel_id"] == 789
        assert mock_save.called
        assert sel_ch.view.refresh.called

    sel_landing = VerificationLandingChannelSelect(guild_id=777)
    sel_landing.view = MagicMock()
    sel_landing.view.refresh = AsyncMock()
    sel_landing.values = [mock_ch]

    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(sel_landing.callback(interaction))
        assert mock_config["verification_landing_channel_id"] == 789
        assert mock_save.called
        assert sel_landing.view.refresh.called

    sel_log = VerificationLogChannelSelect(guild_id=777)
    sel_log.view = MagicMock()
    sel_log.view.refresh = AsyncMock()
    sel_log.values = [mock_ch]

    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(sel_log.callback(interaction))
        assert mock_config["verification_log_channel_id"] == 789
        assert mock_save.called
        assert sel_log.view.refresh.called

    # Clear buttons
    from verification_module import VerificationRolesView, VerificationChannelsView

    roles_view = VerificationRolesView(guild_id=777)
    roles_view.refresh = AsyncMock()

    mock_config["verification_unverified_role_id"] = 123
    mock_config["verification_verified_role_ids"] = [456]
    mock_config["verification_verified_role_id"] = 456

    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(roles_view.clear_unverified_role(interaction, MagicMock()))
        assert mock_config["verification_unverified_role_id"] is None
        assert mock_save.called
        assert roles_view.refresh.called

        run_async(roles_view.clear_verified_roles(interaction, MagicMock()))
        assert mock_config["verification_verified_role_ids"] == []
        assert mock_config["verification_verified_role_id"] is None
        assert mock_save.called

    channels_view = VerificationChannelsView(guild_id=777)
    channels_view.refresh = AsyncMock()

    mock_config["verification_channel_id"] = 789
    mock_config["verification_landing_channel_id"] = 789
    mock_config["verification_log_channel_id"] = 789

    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(channels_view.clear_verification_channel(interaction, MagicMock()))
        assert mock_config["verification_channel_id"] is None
        assert mock_save.called
        assert channels_view.refresh.called

        run_async(channels_view.clear_landing_channel(interaction, MagicMock()))
        assert mock_config["verification_landing_channel_id"] is None
        assert mock_save.called

        run_async(channels_view.clear_log_channel(interaction, MagicMock()))
        assert mock_config["verification_log_channel_id"] is None
        assert mock_save.called

    print("Verification module dropdown settings tests passed.")

def test_verification_dashboard_multiple_roles():
    print("Testing verification dashboard multiple roles display...")
    mock_config = {
        "verification_unverified_role_id": 222,
        "verification_verified_role_ids": [111, 333],
        "verification_verified_role_id": 111,
        "verification_channel_id": None,
        "verification_landing_channel_id": None,
        "verification_log_channel_id": None,
        "verification_enabled": True,
    }
    
    dashboard = verification_module.VerificationConfigDashboard(guild_id=777)
    
    with patch("verification_module.get_guild_config", return_value=mock_config):
        embed = dashboard.build_embed()
        
    verified_field = None
    for field in embed.fields:
        if field["name"] == "Verified Roles":
            verified_field = field
            break
            
    assert verified_field is not None
    assert "<@&111>" in verified_field["value"]
    assert "<@&333>" in verified_field["value"]
    print("Verification dashboard multiple roles display test passed.")

def test_verification_timeout_modal():
    print("Testing verification timeout settings modal...")
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.message = MagicMock()
    interaction.message.edit = AsyncMock()
    
    mock_config = {
        "verification_timeout": 0,
        "verification_enabled": True,
        "verification_unverified_role_id": None,
        "verification_verified_role_ids": [],
        "verification_verified_role_id": None,
        "verification_channel_id": None,
        "verification_landing_channel_id": None,
        "verification_log_channel_id": None,
    }
    
    from verification_module import VerificationTimeoutModal
    modal = VerificationTimeoutModal(guild_id=777)
    modal.input.value = " 120 "
    
    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(modal.on_submit(interaction))
        assert mock_config["verification_timeout"] == 120
        assert mock_save.called
        
    modal.input.value = "abc"
    interaction.response.send_message.reset_mock()
    with patch("verification_module.get_guild_config", return_value=mock_config), \
         patch("verification_module.save_config") as mock_save:
        run_async(modal.on_submit(interaction))
        interaction.response.send_message.assert_called_once()
        args, kwargs = interaction.response.send_message.call_args
        assert "must be a non-negative integer" in args[0].lower()
    print("Verification timeout settings modal tests passed.")

def test_verification_timeout_kick_unverified():
    print("Testing verification timeout: kick unverified user...")
    member = MagicMock()
    member.id = 99999
    member.guild.id = 12345
    
    unverified_role = MagicMock()
    unverified_role.id = 222
    member.roles = [unverified_role]
    
    guild = MagicMock()
    guild.get_member = MagicMock(return_value=member)
    member.guild = guild
    member.kick = AsyncMock()
    
    log_channel = MagicMock()
    log_channel.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=log_channel)
    
    cfg = get_guild_config(member.guild.id)
    cfg["verification_enabled"] = True
    cfg["verification_timeout"] = 300
    cfg["verification_unverified_role_id"] = 222
    cfg["verification_verified_role_ids"] = [111]
    cfg["verification_log_channel_id"] = 8888
    
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        run_async(verification_module.schedule_verification_kick(member, 300))
        mock_sleep.assert_called_once_with(300)
        
    member.kick.assert_called_once()
    log_channel.send.assert_called_once()
    args, kwargs = log_channel.send.call_args
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Kicked" in embed.description
    assert embed.footer.text == "Moderator: System"
    print("Verification timeout kick unverified user test passed.")

def test_verification_timeout_no_kick_verified():
    print("Testing verification timeout: verified user is not kicked...")
    member = MagicMock()
    member.id = 99999
    member.guild.id = 12345
    
    verified_role = MagicMock()
    verified_role.id = 111
    member.roles = [verified_role]
    
    guild = MagicMock()
    guild.get_member = MagicMock(return_value=member)
    member.guild = guild
    member.kick = AsyncMock()
    
    cfg = get_guild_config(member.guild.id)
    cfg["verification_enabled"] = True
    cfg["verification_timeout"] = 300
    cfg["verification_unverified_role_id"] = 222
    cfg["verification_verified_role_ids"] = [111]
    
    with patch("asyncio.sleep", new_callable=AsyncMock):
        run_async(verification_module.schedule_verification_kick(member, 300))
        
    member.kick.assert_not_called()
    print("Verification timeout no kick verified user test passed.")

def test_verification_timeout_on_member_join_scheduling():
    print("Testing on_member_join scheduling verification kick...")
    import main_entrypoint
    
    member = MagicMock()
    member.guild.id = 12345
    
    cfg = get_guild_config(member.guild.id)
    cfg["verification_enabled"] = True
    cfg["verification_timeout"] = 300
    cfg["verification_channel_id"] = None
    
    with patch("verification_module.schedule_verification_kick") as mock_kick:
        run_async(main_entrypoint.on_member_join(member))
        mock_kick.assert_called_once_with(member, 300)
    print("on_member_join scheduling verification kick test passed.")

if __name__ == "__main__":
    test_get_code_generation()
    print("-" * 40)
    test_verification_success()
    print("-" * 40)
    test_verification_failure()
    print("-" * 40)
    test_verification_expiry()
    print("-" * 40)
    test_hierarchy_failure()
    print("-" * 40)
    test_forbidden_role_swap()
    print("-" * 40)
    test_on_member_join()
    print("-" * 40)
    test_verification_success_fallback_log()
    print("-" * 40)
    test_multiple_verified_roles()
    print("-" * 40)
    test_verification_dropdowns()
    print("-" * 40)
    test_verification_dashboard_multiple_roles()
    print("-" * 40)
    test_verification_timeout_modal()
    print("-" * 40)
    test_verification_timeout_kick_unverified()
    print("-" * 40)
    test_verification_timeout_no_kick_verified()
    print("-" * 40)
    test_verification_timeout_on_member_join_scheduling()
    print("-" * 40)
    
        
    print("ALL VERIFICATION LOGIC TESTS PASSED!")
