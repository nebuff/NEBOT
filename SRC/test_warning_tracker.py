import os
import sys
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Mock discord dependencies for importing and testing warning_tracker_module
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
    _roles = None
    def get_role(self, role_id):
        return MagicMock()

class MockUser:
    pass

mock_discord = MagicMock()
mock_discord.Member = MockMember
mock_discord.User = MockUser
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.ui.Button = MockButton
mock_discord.ui.Modal = MockModal
mock_discord.ui.RoleSelect = MockRoleSelect
mock_discord.ui.ChannelSelect = MockChannelSelect
mock_discord.ui.UserSelect = MockUserSelect
def mock_describe_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

mock_discord.ui.button = mock_describe_decorator
mock_discord.app_commands = MagicMock()
mock_discord.app_commands.describe = mock_describe_decorator
mock_discord.app_commands.autocomplete = mock_describe_decorator
mock_discord.ButtonStyle = MagicMock()
mock_discord.Color = MagicMock()

sys.modules['discord'] = mock_discord
sys.modules['discord.app_commands'] = mock_discord.app_commands
sys.modules['discord.ui'] = mock_discord.ui

import test_db_helper
DB_TEST_FILE = test_db_helper.DB_TEST_FILE
test_db_helper.init_test_db()

# Configure test database file before importing warning_tracker_module
import warning_tracker_module

def run_async(coro):
    return asyncio.run(coro)

def test_db_saving_and_loading():
    print("Testing warning tracker database saving and loading...")
    t1 = [{"platform": "Discord", "identifier": "123", "display_name": "UserA"}]
    t2 = [
        {"platform": "Twitch", "identifier": "usera", "display_name": "usera"},
        {"platform": "Discord", "identifier": "456", "display_name": "UserA_Alt"}
    ]
    t3 = [{"platform": "Discord", "identifier": "789", "display_name": "UserB"}]

    r1 = run_async(warning_tracker_module.add_warning_record(
        guild_id=111, targets=t1, details="test 1", severity="Low", points=1, action_taken="None"
    ))
    r2 = run_async(warning_tracker_module.add_warning_record(
        guild_id=111, targets=t2, details="test 2", severity="Medium", points=2, action_taken="None"
    ))
    r3 = run_async(warning_tracker_module.add_warning_record(
        guild_id=222, targets=t3, details="test 3", severity="High", points=3, action_taken="10-minute timeout"
    ))
    
    assert len(r1["linked_accounts"]) == 1
    assert r2["points"] == 2
    assert r3["guild_id"] == 222

    # Query UserA by main Discord account
    warnings_a_discord = run_async(warning_tracker_module.get_user_warnings(111, t1))
    assert len(warnings_a_discord) == 1
    assert warnings_a_discord[0]["details"] == "test 1"

    # Query UserA by Twitch / alt Discord accounts (should match record 2)
    warnings_a_twitch = run_async(warning_tracker_module.get_user_warnings(111, [{"platform": "Twitch", "identifier": "usera", "display_name": "usera"}]))
    assert len(warnings_a_twitch) == 1
    assert warnings_a_twitch[0]["details"] == "test 2"

    # Query UserA by both main & Twitch accounts (should match both r1 and r2!)
    warnings_a_both = run_async(warning_tracker_module.get_user_warnings(111, t1 + t2))
    assert len(warnings_a_both) == 2
    
    print("Database saving/loading tests passed.")

def test_active_points_calculation():
    print("Testing warning tracker active points and rolling window...")
    guild_id = 999
    targets = [
        {"platform": "Discord", "identifier": "111", "display_name": "bad_user"},
        {"platform": "Twitch", "identifier": "bad_twitch", "display_name": "bad_twitch"}
    ]

    # Add warning today (3 points)
    run_async(warning_tracker_module.add_warning_record(
        guild_id=guild_id, targets=targets, details="recent warning", severity="High", points=3, action_taken="None"
    ))
    
    # Add warning 100 days ago (2 points)
    old_warning = run_async(warning_tracker_module.add_warning_record(
        guild_id=guild_id, targets=[targets[0]], details="old warning", severity="Medium", points=2, action_taken="None"
    ))

    # Tweak old warning timestamp directly in SQLite
    import sqlite3
    conn = sqlite3.connect(DB_TEST_FILE)
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(days=100)).isoformat()
    conn.execute("UPDATE warnings SET timestamp = ? WHERE id = ?;", (old_ts, old_warning["id"]))
    conn.commit()
    conn.close()

    # Test Static Mode
    points_static, recs_static = run_async(warning_tracker_module.get_active_points_and_records(guild_id, targets, "static", 90))
    assert points_static == 5, f"Expected 5 points in static mode, got {points_static}"
    assert len(recs_static) == 2

    # Test Rolling Mode (window = 90 days)
    points_rolling, recs_rolling = run_async(warning_tracker_module.get_active_points_and_records(guild_id, targets, "rolling", 90))
    assert points_rolling == 3, f"Expected 3 points in rolling mode, got {points_rolling}"
    assert len(recs_rolling) == 1
    print("Active points and rolling window tests passed.")

def test_ladder_milestone_escalation():
    print("Testing ladder progression actions...")
    warning_ladder = {
        "2": "10-minute timeout",
        "5": "1-day timeout",
        "7": "Permanent ban"
    }

    # Helper function to mimic our matching logic
    def get_action_for_points(points):
        applicable_action = "None"
        highest_milestone = 0
        for pt_str, act in warning_ladder.items():
            try:
                pt = int(pt_str)
                if points >= pt and pt > highest_milestone:
                    highest_milestone = pt
                    applicable_action = act
            except ValueError:
                continue
        return applicable_action

    assert get_action_for_points(1) == "None"
    assert get_action_for_points(2) == "10-minute timeout"
    assert get_action_for_points(3) == "10-minute timeout"
    assert get_action_for_points(4) == "10-minute timeout"
    assert get_action_for_points(5) == "1-day timeout"
    assert get_action_for_points(6) == "1-day timeout"
    assert get_action_for_points(7) == "Permanent ban"
    assert get_action_for_points(10) == "Permanent ban"
    print("Ladder progression escalation tests passed.")

def test_moderation_action_execution():
    print("Testing execution of moderation actions on multiple Discord accounts...")
    member1 = MagicMock()
    member1.name = "OffendingUser1"
    member1.mention = "<@123>"
    member1.timeout = AsyncMock()
    member1.ban = AsyncMock()

    member2 = MagicMock()
    member2.name = "OffendingUser2"
    member2.mention = "<@456>"
    member2.timeout = AsyncMock()
    member2.ban = AsyncMock()

    guild = MagicMock()
    guild.get_member = MagicMock(return_value=None)
    guild.fetch_member = AsyncMock()
    def mock_fetch_member(uid):
        if uid == 123:
            return member1
        if uid == 456:
            return member2
        raise Exception("Not found")
    guild.fetch_member.side_effect = mock_fetch_member

    targets = [
        {"platform": "Discord", "identifier": "123", "display_name": "OffendingUser1"},
        {"platform": "Discord", "identifier": "456", "display_name": "OffendingUser2"},
        {"platform": "Twitch", "identifier": "twitch_user", "display_name": "twitch_user"}
    ]

    # Test 10-minute timeout on both Discord targets
    res1 = run_async(warning_tracker_module.execute_moderation_action(
        guild, targets, "10-minute timeout", "Test Timeout"
    ))
    member1.timeout.assert_called_once()
    member2.timeout.assert_called_once()
    assert "Applied 10-minute timeout" in res1

    # Test ban on both Discord targets
    res2 = run_async(warning_tracker_module.execute_moderation_action(
        guild, targets, "Permanent ban", "Test Ban"
    ))
    member1.ban.assert_called_once_with(reason="Test Ban")
    member2.ban.assert_called_once_with(reason="Test Ban")
    assert "Banned OffendingUser1" in res2
    assert "Banned OffendingUser2" in res2

    print("Moderation action execution tests passed.")

def test_crud_edit_and_delete():
    print("Testing warning CRUD edit and delete functions...")
    # Clean DB table
    import sqlite3
    conn = sqlite3.connect(DB_TEST_FILE)
    conn.execute("DELETE FROM warnings;")
    conn.commit()
    conn.close()
        
    targets = [{"platform": "Discord", "identifier": "123", "display_name": "UserA"}]
    record = run_async(warning_tracker_module.add_warning_record(
        guild_id=111, targets=targets, details="original infraction details", severity="Low", points=1, action_taken="None"
    ))
    warning_id = record["id"]

    # Test editing warning
    success_edit, msg_edit = run_async(warning_tracker_module.edit_warning_record(
        guild_id=111, warning_id=warning_id, new_details="edited infraction details", new_points=5
    ))
    assert success_edit
    assert "updated successfully" in msg_edit

    # Load and verify edit
    warnings = run_async(warning_tracker_module.get_user_warnings(111, targets))
    assert len(warnings) == 1
    assert warnings[0]["details"] == "edited infraction details"
    assert warnings[0]["points"] == 5

    # Test deleting warning
    success_del, msg_del = run_async(warning_tracker_module.delete_warning_record(
        guild_id=111, warning_id=warning_id
    ))
    assert success_del
    assert "deleted successfully" in msg_del

    # Load and verify delete
    warnings_after_del = run_async(warning_tracker_module.get_user_warnings(111, targets))
    assert len(warnings_after_del) == 0
    print("Warning CRUD edit/delete tests passed.")

def test_notifications():
    print("Testing warning log channel posting and user DM alerts...")
    mock_config = {
        "warning_log_channel_id": 98765,
        "warning_dm_enabled": True
    }
    
    interaction = MagicMock()
    interaction.guild_id = 777
    interaction.guild.name = "Test Server"
    
    log_channel = MagicMock()
    log_channel.send = AsyncMock()
    
    warned_member = MagicMock()
    warned_member.send = AsyncMock()
    
    interaction.guild.get_channel = MagicMock(return_value=log_channel)
    interaction.guild.fetch_member = AsyncMock(return_value=warned_member)

    # Patch get_guild_config to return our mock_config
    with patch("warning_tracker_module.get_guild_config", return_value=mock_config):
        record = {
            "id": "mock_warning_id",
            "guild_id": 777,
            "linked_accounts": [{"platform": "Discord", "identifier": "555", "display_name": "WarnedUser"}],
            "details": "Spamming",
            "severity": "Low",
            "points": 1
        }
        
        run_async(warning_tracker_module.handle_warning_notifications(interaction, record, "10-minute timeout"))
        
        # Verify log channel received send() call
        log_channel.send.assert_called_once()
        # Verify warned user received DM
        expected_dm = "Test Server added a warning to your account for Spamming.\nAction taken: 10-minute timeout"
        warned_member.send.assert_called_once_with(expected_dm)
        
    print("Notifications alerts tests passed.")

def test_warning_notifications_fallback_log():
    print("Testing warning notifications fallback to global log channel...")
    mock_config = {
        "warning_log_channel_id": None,
        "global_log_channel_id": 1234567,
        "warning_dm_enabled": False
    }
    
    interaction = MagicMock()
    interaction.guild_id = 777
    interaction.guild.name = "Test Server"
    
    global_log_channel = MagicMock()
    global_log_channel.send = AsyncMock()
    
    interaction.guild.get_channel = MagicMock(return_value=global_log_channel)

    # Patch get_guild_config to return our mock_config
    with patch("warning_tracker_module.get_guild_config", return_value=mock_config):
        record = {
            "id": "mock_warning_id",
            "guild_id": 777,
            "linked_accounts": [{"platform": "Discord", "identifier": "555", "display_name": "WarnedUser"}],
            "details": "Spamming",
            "severity": "Low",
            "points": 1
        }
        
        run_async(warning_tracker_module.handle_warning_notifications(interaction, record, "10-minute timeout"))
        
        # Verify global log channel received send() call
        global_log_channel.send.assert_called_once()
        
    print("Warning notifications fallback log test passed.")

def test_moderator_role_permissions():
    print("Testing Moderator role check helper and permissions...")
    from configuration_module import is_mod
    
    cfg = {
        "admin_role_id": 111,
        "mod_role_id": 222
    }
    
    # User is Admin (has admin role)
    admin_role = MagicMock()
    admin_role.id = 111
    admin_user = MockMember()
    admin_user.guild_permissions = MagicMock()
    admin_user.guild_permissions.administrator = False
    admin_user.roles = [admin_role]
    admin_user.get_role = lambda rid: admin_role if rid == 111 else None
    assert is_mod(admin_user, cfg) == True
    
    # User is Moderator (has mod role)
    mod_role = MagicMock()
    mod_role.id = 222
    mod_user = MockMember()
    mod_user.guild_permissions = MagicMock()
    mod_user.guild_permissions.administrator = False
    mod_user.roles = [mod_role]
    mod_user.get_role = lambda rid: mod_role if rid == 222 else None
    assert is_mod(mod_user, cfg) == True
    
    # User is regular user
    regular_user = MockMember()
    regular_user.guild_permissions = MagicMock()
    regular_user.guild_permissions.administrator = False
    regular_user.roles = []
    regular_user.get_role = lambda rid: None
    assert is_mod(regular_user, cfg) == False

    print("Moderator role permission tests passed.")

def test_moderator_command_permissions():
    print("Testing Moderator command permissions...")
    from configuration_module import is_mod
    
    registered_commands = {}
    mock_tree = MagicMock()
    def mock_command_decorator(*args, **kwargs):
        name = kwargs.get("name") or (args[0] if args else "unknown")
        def decorator(func):
            registered_commands[name] = func
            return func
        return decorator
    mock_tree.command = mock_command_decorator
    
    warning_tracker_module.setup_warning_tracker_commands(mock_tree)
    
    slash_warning = registered_commands.get("warning")
    slash_warning_view = registered_commands.get("warning-view")
    slash_warning_edit = registered_commands.get("warning-edit")
    slash_warning_delete = registered_commands.get("warning-delete")
    
    assert slash_warning is not None
    assert slash_warning_view is not None
    assert slash_warning_edit is not None
    assert slash_warning_delete is not None
    
    # Configure mock configuration: moderator role is 222
    mock_config = {
        "admin_role_id": 111,
        "mod_role_id": 222,
        "warning_tracker_enabled": True
    }
    
    # Create a mock Moderator user
    mod_role = MagicMock()
    mod_role.id = 222
    mod_user = MockMember()
    mod_user.id = 67890
    mod_user.guild_permissions = MagicMock()
    mod_user.guild_permissions.administrator = False
    mod_user.roles = [mod_role]
    mod_user.get_role = lambda rid: mod_role if rid == 222 else None
    
    # Create mock interaction
    interaction = MagicMock()
    interaction.guild_id = 777
    interaction.user = mod_user
    interaction.response = AsyncMock()
    
    with patch("warning_tracker_module.get_guild_config", return_value=mock_config):
        # Moderator running `/warning`
        with patch("warning_tracker_module.get_user_warnings", return_value=[]):
            run_async(slash_warning(interaction, discord_user=MagicMock()))
            if interaction.response.send_message.called:
                args, kwargs = interaction.response.send_message.call_args
                msg_text = args[0] if args else kwargs.get("content", "")
                assert "Permission denied" not in msg_text
        
        interaction.response.send_message.reset_mock()
        
        # Moderator running `/warning-view`
        with patch("warning_tracker_module.get_user_warnings", return_value=[]):
            run_async(slash_warning_view(interaction, discord_user=MagicMock()))
            args, kwargs = interaction.response.send_message.call_args
            msg_text = args[0] if args else kwargs.get("content", "")
            assert "Permission denied" not in msg_text
            assert "No warnings found" in msg_text

        interaction.response.send_message.reset_mock()

        # Moderator running `/warning-edit` (should deny)
        run_async(slash_warning_edit(interaction, warning_id="123"))
        args, kwargs = interaction.response.send_message.call_args
        msg_text = args[0] if args else kwargs.get("content", "")
        assert "Permission denied" in msg_text

        interaction.response.send_message.reset_mock()

        # Moderator running `/warning-delete` (should deny)
        run_async(slash_warning_delete(interaction, warning_id="123"))
        args, kwargs = interaction.response.send_message.call_args
        msg_text = args[0] if args else kwargs.get("content", "")
        assert "Permission denied" in msg_text

    print("Moderator command permissions tests passed.")

def test_moderator_role_selection_ui_and_command():
    print("Testing Moderator role selection UI and slash command...")
    import admin_ui_module
    
    # Test set-mod-role slash command
    registered_commands = {}
    mock_tree = MagicMock()
    def mock_command_decorator(*args, **kwargs):
        name = kwargs.get("name") or (args[0] if args else "unknown")
        def decorator(func):
            registered_commands[name] = func
            return func
        return decorator
    mock_tree.command = mock_command_decorator
    
    admin_ui_module.setup_admin_commands(mock_tree)
    slash_set_mod_role = registered_commands.get("set-mod-role")
    assert slash_set_mod_role is not None
    
    # Test setting as admin
    admin_user = MagicMock(spec=MockMember)
    admin_user.guild_permissions.administrator = True
    
    interaction = MagicMock()
    interaction.guild_id = 777
    interaction.user = admin_user
    interaction.response = AsyncMock()
    
    mock_config = {"admin_role_id": None, "mod_role_id": None}
    
    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        
        # Test setting a role
        mock_role = MagicMock()
        mock_role.id = 555
        mock_role.name = "HelperMod"
        
        run_async(slash_set_mod_role(interaction, role=mock_role))
        assert mock_config["mod_role_id"] == 555
        assert mock_save.called
        
        mock_save.reset_mock()
        
        # Test clearing the role (role=None)
        run_async(slash_set_mod_role(interaction, role=None))
        assert mock_config["mod_role_id"] is None
        assert mock_save.called
        
    # Test permission denied for regular user
    regular_user = MagicMock(spec=MockMember)
    regular_user.guild_permissions.administrator = False
    regular_user.roles = []
    interaction.user = regular_user
    interaction.response.send_message.reset_mock()
    
    with patch("admin_ui_module.get_guild_config", return_value=mock_config):
        run_async(slash_set_mod_role(interaction, role=mock_role))
        args, kwargs = interaction.response.send_message.call_args
        msg_text = args[0] if args else kwargs.get("content", "")
        assert "Permission denied" in msg_text

    # Test ModeratorRoleSelect component callback
    from admin_ui_module import ModeratorRoleSelect
    select = ModeratorRoleSelect(guild_id=777)
    select.view = MagicMock()
    select.view.refresh = AsyncMock()
    select.values = [mock_role]
    
    interaction.user = admin_user
    interaction.response.edit_message = AsyncMock()
    
    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(select.callback(interaction))
        assert mock_config["mod_role_id"] == 555
        assert mock_save.called
        assert select.view.refresh.called

    # Test Clear Moderator Role button click
    from admin_ui_module import GlobalConfigDashboard
    dashboard = GlobalConfigDashboard(guild_id=777)
    dashboard.refresh = AsyncMock()
    
    interaction.response.send_message = AsyncMock()
    
    mock_config["mod_role_id"] = 555
    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(dashboard.clear_mod_role(interaction, MagicMock()))
        assert mock_config["mod_role_id"] is None
        assert mock_save.called
        assert dashboard.refresh.called

    print("Moderator role selection UI and slash command tests passed.")

def test_unified_settings_dropdown_selection():
    print("Testing unified settings dropdown selection system...")
    
    mock_config = {
        "admin_role_id": None,
        "mod_role_id": None,
        "global_log_channel_id": None,
        "channel_id": None,
        "shared_channel_id": None,
        "warning_log_channel_id": None,
    }

    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.guild.fetch_member = AsyncMock()

    # Test AdminRoleSelect
    from admin_ui_module import AdminRoleSelect
    mock_role = MagicMock()
    mock_role.id = 111
    mock_role.name = "AdminRole"
    
    select = AdminRoleSelect(guild_id=777)
    select.view = MagicMock()
    select.view.refresh = AsyncMock()
    select.values = [mock_role]

    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(select.callback(interaction))
        assert mock_config["admin_role_id"] == 111
        assert mock_save.called
        assert select.view.refresh.called

    # Test GlobalLogChannelSelect
    from admin_ui_module import GlobalLogChannelSelect
    mock_channel = MagicMock()
    mock_channel.id = 222
    mock_channel.name = "global-log"

    select_channel = GlobalLogChannelSelect(guild_id=777)
    select_channel.view = MagicMock()
    select_channel.view.refresh = AsyncMock()
    select_channel.values = [mock_channel]

    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(select_channel.callback(interaction))
        assert mock_config["global_log_channel_id"] == 222
        assert mock_save.called
        assert select_channel.view.refresh.called

    # Test NeOSAdminChannelSelect and NeOSSharedChannelSelect
    from admin_ui_module import NeOSAdminChannelSelect, NeOSSharedChannelSelect
    mock_admin_ch = MagicMock()
    mock_admin_ch.id = 333
    mock_shared_ch = MagicMock()
    mock_shared_ch.id = 444

    sel_admin_ch = NeOSAdminChannelSelect(guild_id=777)
    sel_admin_ch.view = MagicMock()
    sel_admin_ch.view.refresh = AsyncMock()
    sel_admin_ch.values = [mock_admin_ch]

    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(sel_admin_ch.callback(interaction))
        assert mock_config["channel_id"] == 333
        assert mock_save.called
        assert sel_admin_ch.view.refresh.called

    sel_shared_ch = NeOSSharedChannelSelect(guild_id=777)
    sel_shared_ch.view = MagicMock()
    sel_shared_ch.view.refresh = AsyncMock()
    sel_shared_ch.values = [mock_shared_ch]

    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(sel_shared_ch.callback(interaction))
        assert mock_config["shared_channel_id"] == 444
        assert mock_save.called
        assert sel_shared_ch.view.refresh.called

    # Test WarningLogChannelSelect
    from admin_ui_module import WarningLogChannelSelect
    mock_warn_ch = MagicMock()
    mock_warn_ch.id = 555

    sel_warn_ch = WarningLogChannelSelect(guild_id=777)
    sel_warn_ch.view = MagicMock()
    sel_warn_ch.view.refresh = AsyncMock()
    sel_warn_ch.values = [mock_warn_ch]

    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(sel_warn_ch.callback(interaction))
        assert mock_config["warning_log_channel_id"] == 555
        assert mock_save.called
        assert sel_warn_ch.view.refresh.called

    # Test QuickUserWarningSelect and QuickUserViewSelect
    from admin_ui_module import QuickUserWarningSelect, QuickUserViewSelect
    mock_member = MagicMock()
    mock_member.id = 9999
    mock_member.display_name = "TargetUser"

    sel_quick_warn = QuickUserWarningSelect(guild_id=777)
    sel_quick_warn.values = [mock_member]

    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("warning_tracker_module.get_user_warnings", return_value=[]) as mock_get_warns:
        run_async(sel_quick_warn.callback(interaction))
        assert mock_get_warns.called

    sel_quick_view = QuickUserViewSelect(guild_id=777)
    sel_quick_view.values = [mock_member]

    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("warning_tracker_module.get_user_warnings", return_value=[]) as mock_get_warns:
        run_async(sel_quick_view.callback(interaction))
        assert mock_get_warns.called

    # Test Clear buttons
    from admin_ui_module import GlobalConfigDashboard, NeOSConfigDashboard, WarningTrackerDashboard
    
    # Global Config Clear buttons
    glb_dash = GlobalConfigDashboard(guild_id=777)
    glb_dash.refresh = AsyncMock()
    
    mock_config["admin_role_id"] = 111
    mock_config["global_log_channel_id"] = 222
    
    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(glb_dash.clear_admin_role(interaction, MagicMock()))
        assert mock_config["admin_role_id"] is None
        assert mock_save.called
        assert glb_dash.refresh.called
        
        run_async(glb_dash.clear_global_log(interaction, MagicMock()))
        assert mock_config["global_log_channel_id"] is None
        assert mock_save.called

    # NeOS Clear buttons
    neos_dash = NeOSConfigDashboard(guild_id=777)
    neos_dash.refresh = AsyncMock()
    
    mock_config["channel_id"] = 333
    mock_config["shared_channel_id"] = 444
    
    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(neos_dash.clear_admin_channel(interaction, MagicMock()))
        assert mock_config["channel_id"] is None
        assert mock_save.called
        assert neos_dash.refresh.called
        
        run_async(neos_dash.clear_shared_channel(interaction, MagicMock()))
        assert mock_config["shared_channel_id"] is None
        assert mock_save.called

    # Warning Tracker Clear buttons
    warn_dash = WarningTrackerDashboard(guild_id=777)
    warn_dash.refresh = AsyncMock()
    
    mock_config["warning_log_channel_id"] = 555
    
    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save:
        run_async(warn_dash.clear_log_channel(interaction, MagicMock()))
        assert mock_config["warning_log_channel_id"] is None
        assert mock_save.called
        assert warn_dash.refresh.called

    print("Unified settings dropdown selection system tests passed.")

def test_dynamic_moderation_actions():
    print("Testing dynamic action parsing, execution and logging...")
    from warning_tracker_module import parse_moderation_action, execute_moderation_action
    
    act, dur = parse_moderation_action("5-minute timeout")
    assert act == "timeout" and dur == datetime.timedelta(minutes=5)
    
    act, dur = parse_moderation_action("12h")
    assert act == "timeout" and dur == datetime.timedelta(hours=12)
    
    act, dur = parse_moderation_action("3 days")
    assert act == "timeout" and dur == datetime.timedelta(days=3)
    
    act, dur = parse_moderation_action("2 weeks")
    assert act == "timeout" and dur == datetime.timedelta(weeks=2)
    
    act, dur = parse_moderation_action("kick")
    assert act == "kick" and dur is None
    
    act, dur = parse_moderation_action("Permanent ban")
    assert act == "ban" and dur is None
    
    act, dur = parse_moderation_action("None")
    assert act == "none" and dur is None

    member = MagicMock()
    member.name = "DynamicUser"
    member.mention = "<@999>"
    member.timeout = AsyncMock()
    member.kick = AsyncMock()
    member.ban = AsyncMock()

    guild = MagicMock()
    guild.get_member = MagicMock(return_value=None)
    guild.name = "Test Server"
    guild.id = 1234
    guild.fetch_member = AsyncMock(return_value=member)

    targets = [{"platform": "Discord", "identifier": "999", "display_name": "DynamicUser"}]

    res1 = run_async(execute_moderation_action(
        guild, targets, "5-minute timeout", "Test custom duration"
    ))
    member.timeout.assert_called_once_with(datetime.timedelta(minutes=5), reason="Test custom duration")
    assert "Applied 5-minute timeout" in res1

    res2 = run_async(execute_moderation_action(
        guild, targets, "kick", "Test kick"
    ))
    member.kick.assert_called_once_with(reason="Test kick")
    assert "Kicked DynamicUser" in res2

    mock_config = {
        "warning_log_channel_id": 9876,
        "global_log_channel_id": None
    }
    log_channel = MagicMock()
    log_channel.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=log_channel)

    with patch("warning_tracker_module.get_guild_config", return_value=mock_config):
        run_async(execute_moderation_action(guild, targets, "ban", "Test logging"))
        log_channel.send.assert_called_once()
        args, kwargs = log_channel.send.call_args
        embed = kwargs.get("embed") or args[0]
        embed_args, embed_kwargs = mock_discord.Embed.call_args
        assert embed_kwargs.get("title") == "Moderation Action Executed"

    print("Dynamic action parsing, execution and logging tests passed.")

def test_discord_id_support():
    print("Testing Discord ID resolution and command integration...")
    guild = MagicMock()
    guild.get_member = MagicMock(return_value=None)
    client = MagicMock()

    # Resolves guild member
    member = MagicMock()
    member.id = 11111
    member.name = "GuildMember"
    guild.get_member = MagicMock(return_value=member)

    target1 = run_async(warning_tracker_module.make_discord_id_target(guild, client, "11111"))
    assert target1["platform"] == "Discord"
    assert target1["identifier"] == "11111"
    assert target1["display_name"] == "GuildMember"
    guild.get_member.assert_called_once_with(11111)

    # Resolves client user (not in guild)
    guild.get_member = MagicMock(return_value=None)
    user = MagicMock()
    user.id = 22222
    user.name = "ClientUser"
    client.fetch_user = AsyncMock(return_value=user)

    target2 = run_async(warning_tracker_module.make_discord_id_target(guild, client, "22222"))
    assert target2["platform"] == "Discord"
    assert target2["identifier"] == "22222"
    assert target2["display_name"] == "ClientUser"
    client.fetch_user.assert_called_once_with(22222)

    # Fallback when fetch fails
    client.fetch_user = AsyncMock(side_effect=Exception("Not found"))
    target3 = run_async(warning_tracker_module.make_discord_id_target(guild, client, "33333"))
    assert target3["platform"] == "Discord"
    assert target3["identifier"] == "33333"
    assert target3["display_name"] == "ID: 33333"

    # Command integration
    registered_commands = {}
    mock_tree = MagicMock()
    def mock_command_decorator(*args, **kwargs):
        name = kwargs.get("name") or (args[0] if args else "unknown")
        def decorator(func):
            registered_commands[name] = func
            return func
        return decorator
    mock_tree.command = mock_command_decorator

    warning_tracker_module.setup_warning_tracker_commands(mock_tree)
    slash_warning = registered_commands.get("warning")
    slash_warning_view = registered_commands.get("warning-view")

    assert slash_warning is not None
    assert slash_warning_view is not None

    mock_config = {
        "admin_role_id": 111,
        "mod_role_id": 222,
        "warning_tracker_enabled": True
    }

    mod_role = MagicMock()
    mod_role.id = 222
    mod_user = MagicMock(spec=MockMember)
    mod_user.id = 67890
    mod_user.guild_permissions.administrator = False
    mod_user.roles = [mod_role]

    interaction = MagicMock()
    interaction.guild_id = 777
    interaction.guild = guild
    interaction.client = client
    interaction.user = mod_user
    interaction.response = AsyncMock()
    # Test running `/warning` with discord_id and discord_id_2
    guild.get_member = MagicMock(return_value=None)
    async def dynamic_fetch(uid):
        u = MagicMock()
        u.id = int(uid)
        u.name = f"User_{uid}"
        return u
    client.fetch_user = AsyncMock(side_effect=dynamic_fetch)
    with patch("warning_tracker_module.get_guild_config", return_value=mock_config), \
         patch("warning_tracker_module.get_user_warnings", return_value=[]) as mock_get_warn:
        run_async(slash_warning(interaction, discord_id="22222", discord_id_2="44444"))
        
        # Verify get_user_warnings was called with targets including both resolved IDs
        mock_get_warn.assert_called_once()
        args, kwargs = mock_get_warn.call_args
        targets_passed = args[1] if len(args) > 1 else kwargs.get("targets")
        assert len(targets_passed) == 2
        assert targets_passed[0]["identifier"] == "22222"
        assert targets_passed[1]["identifier"] == "44444"

    # Test running `/warning-view` with discord_id
    interaction.response.send_message.reset_mock()
    with patch("warning_tracker_module.get_guild_config", return_value=mock_config), \
         patch("warning_tracker_module.get_user_warnings", return_value=[]) as mock_get_warn:
        run_async(slash_warning_view(interaction, discord_id="22222"))
        interaction.response.send_message.assert_called_once()
        args, kwargs = interaction.response.send_message.call_args
        msg = args[0] if args else kwargs.get("content", "")
        assert "No warnings found for 'User_22222'" in msg

    print("Discord ID resolution and command integration tests passed.")

if __name__ == "__main__":
    test_db_saving_and_loading()
    print("-" * 40)
    test_active_points_calculation()
    print("-" * 40)
    test_ladder_milestone_escalation()
    print("-" * 40)
    test_moderation_action_execution()
    print("-" * 40)
    test_crud_edit_and_delete()
    print("-" * 40)
    test_notifications()
    print("-" * 40)
    test_warning_notifications_fallback_log()
    print("-" * 40)
    test_moderator_role_permissions()
    print("-" * 40)
    test_moderator_command_permissions()
    print("-" * 40)
    test_moderator_role_selection_ui_and_command()
    print("-" * 40)
    test_unified_settings_dropdown_selection()
    print("-" * 40)
    test_dynamic_moderation_actions()
    print("-" * 40)
    test_discord_id_support()
    print("-" * 40)
    print("ALL WARNING TRACKER LOGIC TESTS PASSED!")
