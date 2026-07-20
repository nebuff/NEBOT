import os
import sys
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Define custom exception for mocking discord.Forbidden
class MockForbidden(Exception):
    pass

# Mock discord dependencies for importing and testing join_filtering_module
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
mock_discord.Forbidden = MockForbidden

sys.modules['discord'] = mock_discord
sys.modules['discord.app_commands'] = mock_discord.app_commands
sys.modules['discord.ui'] = mock_discord.ui

# Mock other custom modules that are not needed for testing
mock_empty = MagicMock()
sys.modules['commands_registry_handlers_module'] = mock_empty
sys.modules['battle_module'] = mock_empty
sys.modules['minesweeper_module'] = mock_empty
sys.modules['editor_module'] = mock_empty
sys.modules['session_module'] = mock_empty
sys.modules['admin_ui_module'] = mock_empty
sys.modules['utility_module'] = mock_empty

import join_filtering_module
from configuration_module import get_guild_config, save_config

import test_db_helper
DB_TEST_FILE = test_db_helper.DB_TEST_FILE

# Configure test database logs path

# Configure test configuration path
import configuration_module

def run_async(coro):
    return asyncio.run(coro)

    configuration_module.guild_configs.clear()
    test_db_helper.init_test_db()

    for f in [join_filtering_module.JOIN_FILTER_LOGS_FILE, configuration_module.CONFIG_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

def test_database_logging():
    print("Testing Join Filtering database saving, loading and log_enforcement_action...")
    
    run_async(join_filtering_module.log_enforcement_action(
        guild_id=123,
        user_id=456,
        username="TestUser",
        account_created_at="2026-06-28T00:00:00Z",
        age_evaluated="2d 4h",
        reason="Triggered age threshold",
        action="kick",
        status="Success"
    ))
    
    logs = run_async(join_filtering_module.load_join_filter_logs())
    assert "123" in logs
    assert len(logs["123"]) == 1
    event = logs["123"][0]
    assert event["user_id"] == 456
    assert event["username"] == "TestUser"
    assert event["action"] == "kick"
    assert event["status"] == "Success"
    print("Database logging tests passed.")

def test_handle_member_join_disabled():
    print("Testing handle_member_join when module is disabled...")
    
    cfg = get_guild_config(123)
    cfg["join_filter_enabled"] = False
    
    member = MagicMock()
    member.guild.id = 123
    
    result = run_async(join_filtering_module.handle_member_join(member))
    assert result is False
    print("handle_member_join disabled test passed.")

def test_handle_member_join_age_triggered():
    print("Testing handle_member_join age threshold screening and enforcement...")
    
    cfg = get_guild_config(123)
    cfg["join_filter_enabled"] = True
    cfg["join_filter_min_age_value"] = 3
    cfg["join_filter_min_age_unit"] = "days"
    cfg["join_filter_enforcement"] = "kick"
    
    # User created 1 day ago (fails minimum age of 3 days)
    created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    
    member = MagicMock()
    member.guild.id = 123
    member.id = 999
    member.name = "Spambot"
    member.display_name = "SpambotNick"
    member.created_at = created_at
    member.top_role.position = 1
    member.send = AsyncMock()
    member.kick = AsyncMock()
    
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    bot_member.guild_permissions.kick_members = True
    member.guild.me = bot_member
    
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        result = run_async(join_filtering_module.handle_member_join(member))
        assert result is True
        member.send.assert_called_once()
        member.kick.assert_called_once()
        assert mock_notify.called
        
    logs = run_async(join_filtering_module.load_join_filter_logs())
    assert logs["123"][0]["status"] == "Kicked Successfully"
    print("handle_member_join age triggered test passed.")

def test_handle_member_join_age_passed():
    print("Testing handle_member_join age threshold screening pass...")
    
    cfg = get_guild_config(123)
    cfg["join_filter_enabled"] = True
    cfg["join_filter_min_age_value"] = 3
    cfg["join_filter_min_age_unit"] = "days"
    cfg["join_filter_enforcement"] = "kick"
    
    # User created 5 days ago (meets minimum age of 3 days)
    created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
    
    member = MagicMock()
    member.guild.id = 123
    member.id = 888
    member.name = "LegitUser"
    member.created_at = created_at
    
    result = run_async(join_filtering_module.handle_member_join(member))
    assert result is False
    print("handle_member_join age passed test passed.")

def test_handle_member_join_username_triggered():
    print("Testing handle_member_join username pattern matching (substring and regex)...")
    
    cfg = get_guild_config(123)
    cfg["join_filter_enabled"] = True
    cfg["join_filter_min_age_value"] = 0
    # Use wildcard *bad_word* for substring test, and plain bad_word / regex
    cfg["join_filter_username_patterns"] = ["*bad_word*", "r:helper_.*"]
    cfg["join_filter_enforcement"] = "ban"
    
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    bot_member.guild_permissions.ban_members = True
    
    # Literal substring match (with wildcard keyword *bad_word*)
    member_sub = MagicMock()
    member_sub.guild.id = 123
    member_sub.guild.me = bot_member
    member_sub.id = 111
    member_sub.name = "Somebad_wordUser"
    member_sub.display_name = "Nickname"
    member_sub.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_sub.top_role.position = 1
    member_sub.ban = AsyncMock()
    
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        result = run_async(join_filtering_module.handle_member_join(member_sub))
        assert result is True
        member_sub.ban.assert_called_once()
        
    # 1b. Literal whole-word match (plain bad_word should not match substring)
    cfg["join_filter_username_patterns"] = ["bad_word"]
    member_no_match = MagicMock()
    member_no_match.guild.id = 123
    member_no_match.guild.me = bot_member
    member_no_match.id = 112
    member_no_match.name = "Somebad_wordUser"
    member_no_match.display_name = "Nickname"
    member_no_match.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_no_match.top_role.position = 1
    member_no_match.ban = AsyncMock()
    
    result = run_async(join_filtering_module.handle_member_join(member_no_match))
    assert result is False
    member_no_match.ban.assert_not_called()

    # 1c. Literal whole-word match (plain bad_word should match when separated by boundary)
    member_match = MagicMock()
    member_match.guild.id = 123
    member_match.guild.me = bot_member
    member_match.id = 113
    member_match.name = "Some bad_word User"
    member_match.display_name = "Nickname"
    member_match.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_match.top_role.position = 1
    member_match.ban = AsyncMock()

    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        result = run_async(join_filtering_module.handle_member_join(member_match))
        assert result is True
        member_match.ban.assert_called_once()

    # Restore patterns list for the regex test
    cfg["join_filter_username_patterns"] = ["*bad_word*", "r:helper_.*"]
        
    # Regex match
    member_rx = MagicMock()
    member_rx.guild.id = 123
    member_rx.guild.me = bot_member
    member_rx.id = 222
    member_rx.name = "NormalUser"
    member_rx.display_name = "helper_admin"
    member_rx.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_rx.top_role.position = 1
    member_rx.ban = AsyncMock()
    
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        result = run_async(join_filtering_module.handle_member_join(member_rx))
        assert result is True
        member_rx.ban.assert_called_once()
        
    print("handle_member_join username pattern matching test passed.")

def test_handle_member_join_quarantine():
    print("Testing handle_member_join quarantine action role state...")
    
    cfg = get_guild_config(123)
    cfg["join_filter_enabled"] = True
    cfg["join_filter_min_age_value"] = 10
    cfg["join_filter_min_age_unit"] = "hours"
    cfg["join_filter_enforcement"] = "quarantine"
    cfg["verification_unverified_role_id"] = 777
    
    created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    
    member = MagicMock()
    member.guild.id = 123
    member.id = 555
    member.name = "QuarantineTarget"
    member.created_at = created_at
    member.add_roles = AsyncMock()
    
    role = MagicMock()
    role.id = 777
    role.position = 2
    member.guild.get_role = MagicMock(return_value=role)
    
    bot_member = MagicMock()
    bot_member.top_role.position = 5
    bot_member.guild_permissions.manage_roles = True
    member.guild.me = bot_member
    
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        result = run_async(join_filtering_module.handle_member_join(member))
        assert result is True
        member.add_roles.assert_called_once_with(role, reason="Join filtering quarantine.")
        
    logs = run_async(join_filtering_module.load_join_filter_logs())
    assert logs["123"][0]["status"] == "Quarantined"
    print("handle_member_join quarantine test passed.")

def test_dashboard_ui_elements():
    print("Testing Join Filtering UI Configuration Dashboard & View state...")
    
    # Toggle Join Filter Button
    dash = join_filtering_module.JoinFilteringConfigDashboard(guild_id=123)
    dash.refresh = AsyncMock()
    
    interaction = MagicMock()
    interaction.guild.id = 123
    interaction.user = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    
    with patch("join_filtering_module.save_config") as mock_save:
        run_async(dash.toggle_filter(interaction, MagicMock()))
        cfg = get_guild_config(123)
        assert cfg["join_filter_enabled"] is True
        assert mock_save.called
        assert dash.refresh.called
        
    # Account Age Setup Modal Submit
    modal = join_filtering_module.JoinFilterAgeModal(guild_id=123)
    modal.val_input.value = " 5 "
    modal.unit_input.value = " hours "
    interaction.response.edit_message = AsyncMock()
    
    with patch("join_filtering_module.save_config") as mock_save:
        run_async(modal.on_submit(interaction))
        cfg = get_guild_config(123)
        assert cfg["join_filter_min_age_value"] == 5
        assert cfg["join_filter_min_age_unit"] == "hours"
        assert mock_save.called
        
    # Username Rules Wizard Views
    rules_view = join_filtering_module.JoinFilterUsernameRulesView(guild_id=123)
    rules_view.refresh = AsyncMock()
    
    # Clear Rules Button
    with patch("join_filtering_module.save_config") as mock_save:
        cfg["join_filter_username_patterns"] = ["test_pattern"]
        run_async(rules_view.clear_rules(interaction, MagicMock()))
        cfg = get_guild_config(123)
        assert len(cfg["join_filter_username_patterns"]) == 0
        assert mock_save.called
        assert rules_view.refresh.called
        
    # Add Rule Modal Submit
    add_modal = join_filtering_module.JoinFilterAddRuleModal(guild_id=123)
    add_modal.pattern_input.value = "spam.*bot"
    
    with patch("join_filtering_module.save_config") as mock_save:
        run_async(add_modal.on_submit(interaction))
        cfg = get_guild_config(123)
        assert "spam.*bot" in cfg["join_filter_username_patterns"]
        assert mock_save.called
        
    # Rule Select Remove Callback
    remove_select = join_filtering_module.JoinFilterRuleSelect(guild_id=123, options_list=["spam.*bot"])
    remove_select.values = ["spam.*bot"]
    
    with patch("join_filtering_module.save_config") as mock_save:
        run_async(remove_select.callback(interaction))
        cfg = get_guild_config(123)
        assert "spam.*bot" not in cfg["join_filter_username_patterns"]
        assert mock_save.called
        
    # Enforcement options sub-view
    enf_view = join_filtering_module.JoinFilterEnforcementView(guild_id=123)
    with patch("join_filtering_module.save_config") as mock_save:
        run_async(enf_view.set_enforcement(interaction, "ban"))
        cfg = get_guild_config(123)
        assert cfg["join_filter_enforcement"] == "ban"
        assert mock_save.called
        
    print("Dashboard UI elements tests passed.")

def test_asterisk_semantics_join_filters():
    print("Testing asterisk wildcard vs whole-word matching in join filters list...")
    
    cfg = get_guild_config(123)
    cfg["join_filter_enabled"] = True
    cfg["join_filters"] = [
        {
            "id": "filter_wildcard",
            "name": "Wildcard Test",
            "enabled": True,
            "keywords": ["*spam*"],
            "enforcement_action": "ban"
        },
        {
            "id": "filter_whole",
            "name": "Whole Word Test",
            "enabled": True,
            "keywords": ["**alt**", "bot"],
            "enforcement_action": "kick"
        }
    ]
    
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    bot_member.guild_permissions.ban_members = True
    bot_member.guild_permissions.kick_members = True
    
    # Wildcard match (should match substring)
    member_wc = MagicMock()
    member_wc.guild.id = 123
    member_wc.guild.me = bot_member
    member_wc.id = 881
    member_wc.name = "Legitspambot"
    member_wc.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_wc.top_role.position = 1
    member_wc.ban = AsyncMock()
    
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        res = run_async(join_filtering_module.handle_member_join(member_wc))
        assert res is True
        member_wc.ban.assert_called_once()
        
    # Whole word match negative case: "**alt**" and "bot" should not match substring
    member_no_match = MagicMock()
    member_no_match.guild.id = 123
    member_no_match.guild.me = bot_member
    member_no_match.id = 882
    member_no_match.name = "myaltaccount"
    member_no_match.display_name = "robot"
    member_no_match.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_no_match.top_role.position = 1
    member_no_match.ban = AsyncMock()
    member_no_match.kick = AsyncMock()
    
    res = run_async(join_filtering_module.handle_member_join(member_no_match))
    assert res is False
    member_no_match.ban.assert_not_called()
    member_no_match.kick.assert_not_called()
    
    # Whole word match positive case: "**alt**" matches whole word
    member_match_alt = MagicMock()
    member_match_alt.guild.id = 123
    member_match_alt.guild.me = bot_member
    member_match_alt.id = 883
    member_match_alt.name = "my alt account"
    member_match_alt.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_match_alt.top_role.position = 1
    member_match_alt.kick = AsyncMock()
    
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        res = run_async(join_filtering_module.handle_member_join(member_match_alt))
        assert res is True
        member_match_alt.kick.assert_called_once()
        
    print("Asterisk semantics in join filters test passed.")

def test_emoji_and_homoglyph_semantics_join_filters():
    print("Testing emoji and homoglyph semantics in join filters...")
    cfg = get_guild_config(123)
    cfg["join_filter_enabled"] = True
    cfg["join_filter_enforcement"] = "quarantine"
    
    bot_member = MagicMock()
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role.position = 10
    
    # Test legacy username screening with homoglyphs (Cyrillic e = \u0435)
    # 1a. Disabled by default: should not match
    cfg["join_filter_username_patterns"] = ["*check_bio*"]
    cfg["join_filter_username_homoglyphs"] = False
    
    member_homo = MagicMock()
    member_homo.guild.id = 123
    member_homo.guild.me = bot_member
    member_homo.id = 991
    member_homo.name = "ch\u0435ck_bio"
    member_homo.display_name = "Legit Member"
    member_homo.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_homo.top_role.position = 1
    
    res = run_async(join_filtering_module.handle_member_join(member_homo))
    assert res is False
    
    # 1b. Enabled: should match!
    cfg["join_filter_username_homoglyphs"] = True
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        res = run_async(join_filtering_module.handle_member_join(member_homo))
        assert res is True

    # Test list-based join filters with emojis and homoglyphs
    cfg["join_filter_username_patterns"] = [] # Clear legacy
    cfg["join_filters"] = [{
        "id": "jf_test_emoji",
        "name": "Emoji & Homo Join Filter",
        "enabled": True,
        "keywords": ["*check my bio*"],
        "enforcement_action": "kick",
        "filter_emojis": True,
        "filter_homoglyphs": True
    }]
    
    member_emoji_homo = MagicMock()
    member_emoji_homo.guild.id = 123
    member_emoji_homo.guild.me = bot_member
    member_emoji_homo.id = 992
    member_emoji_homo.name = "please 🇨 🇭 🇪 🇨 🇰 🇲 🇾 🇧 🇮 🇴"
    member_emoji_homo.display_name = "Legit display"
    member_emoji_homo.created_at = datetime.datetime.now(datetime.timezone.utc)
    member_emoji_homo.top_role.position = 1
    member_emoji_homo.kick = AsyncMock()
    
    with patch("join_filtering_module.send_join_filter_notification") as mock_notify:
        res = run_async(join_filtering_module.handle_member_join(member_emoji_homo))
        assert res is True
        member_emoji_homo.kick.assert_called_once()

    print("Emoji and homoglyph semantics in join filters test passed.")

if __name__ == "__main__":
    print("=" * 45)
    print("RUNNING JOIN FILTERING TESTING PROTOCOL")
    print("=" * 45)
    test_database_logging()
    print("-" * 40)
    test_handle_member_join_disabled()
    print("-" * 40)
    test_handle_member_join_age_triggered()
    print("-" * 40)
    test_handle_member_join_age_passed()
    print("-" * 40)
    test_handle_member_join_username_triggered()
    print("-" * 40)
    test_handle_member_join_quarantine()
    print("-" * 40)
    test_dashboard_ui_elements()
    print("-" * 40)
    test_asterisk_semantics_join_filters()
    print("-" * 40)
    test_emoji_and_homoglyph_semantics_join_filters()
    print("-" * 40)
    print("ALL JOIN FILTERING MODULE TESTS COMPLETED SUCCESSFULLY!")
