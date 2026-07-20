import sys
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Mock discord dependencies for importing and testing automod_module
class MockView:
    def __init__(self, *args, **kwargs):
        pass
    def add_item(self, item):
        pass
    def clear_items(self):
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

class MockRole:
    def __init__(self, id, name):
        self.id = id
        self.name = name

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

class MockClient:
    def __init__(self, *args, **kwargs):
        pass
    def event(self, func):
        return func

class MockThread:
    pass

mock_discord = MagicMock()
mock_discord.Member = MockMember
mock_discord.Client = MockClient
mock_discord.Thread = MockThread
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
sys.modules['commands_registry_handlers_module'] = mock_empty
sys.modules['battle_module'] = mock_empty
sys.modules['minesweeper_module'] = mock_empty
sys.modules['editor_module'] = mock_empty
sys.modules['session_module'] = mock_empty
sys.modules['utility_module'] = mock_empty

import automod_module

def run_async(coro):
    return asyncio.run(coro)

def test_text_normalization():
    print("Testing text normalization & leetspeak mapping...")
    # Test lowercase and basic leetspeak translation
    spaced, merged, condensed = automod_module.normalize_text("Sw3@r W0rd.")
    assert spaced == "swear word", f"Expected 'swear word', got '{spaced}'"
    assert merged == "swear word", f"Expected 'swear word', got '{merged}'"
    assert condensed == "swearword", f"Expected 'swearword', got '{condensed}'"

    # Test spacing bypass
    spaced, merged, condensed = automod_module.normalize_text("s w e a r   w-o-r-d")
    assert spaced == "s w e a r w o r d", f"Expected 's w e a r w o r d', got '{spaced}'"
    assert merged == "swear word", f"Expected 'swear word', got '{merged}'"
    assert condensed == "swearword", f"Expected 'swearword', got '{condensed}'"

    # Test nested word boundaries (avoid matching "ass" in "class")
    spaced, merged, condensed = automod_module.normalize_text("class glass")
    assert "class" in spaced
    assert "class" in merged
    assert "glass" in spaced
    
    print("Text normalization tests passed.")

def test_bypass_checks():
    print("Testing AutoMod bypass check configurations...")
    guild = MagicMock()
    guild.id = 1234
    
    channel = MockChannel(555, "general")
    role1 = MockRole(101, "Admin")
    role2 = MockRole(102, "Member")
    
    author = MockMember(999, "UserA", roles=[role2])
    
    message = MagicMock()
    message.guild = guild
    message.channel = channel
    message.author = author
    message.content = "badword"
    message.delete = AsyncMock()

    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "filter1",
                "name": "Bad Words",
                "enabled": True,
                "keywords": ["badword"],
                "enforcement_action": "Delete Message Only"
            }
        ],
        "automod_ignored_channels": [555],  # Channel is ignored
        "automod_ignored_roles": [101]
    }

    # Test channel bypass
    with patch("automod_module.get_guild_config", return_value=mock_config):
        res = run_async(automod_module.handle_automod_message(message))
        assert res is False, "AutoMod should bypass for ignored channels"
        message.delete.assert_not_called()

    # Test role bypass
    mock_config["automod_ignored_channels"] = []
    mock_config["automod_ignored_roles"] = [102]  # User's role is now ignored
    with patch("automod_module.get_guild_config", return_value=mock_config):
        res = run_async(automod_module.handle_automod_message(message))
        assert res is False, "AutoMod should bypass for ignored roles"
        message.delete.assert_not_called()

    # Test active interception when not bypassed
    mock_config["automod_ignored_roles"] = []
    with patch("automod_module.get_guild_config", return_value=mock_config):
        res = run_async(automod_module.handle_automod_message(message))
        assert res is True, "AutoMod should intercept when not bypassed"
        message.delete.assert_called_once()
        
    print("Bypass check tests passed.")

def test_literal_and_regex_matching():
    print("Testing literal and regex filtration matchers...")
    guild = MagicMock()
    guild.id = 1234
    message = MagicMock()
    message.guild = guild
    message.channel = MockChannel(555, "general")
    message.author = MockMember(999, "UserA")
    message.delete = AsyncMock()

    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f1",
                "name": "Literal Filter",
                "enabled": True,
                "keywords": ["swear", "r:phish.*link"],
                "enforcement_action": "Delete Message Only"
            }
        ]
    }

    # Test literal match (with spacing bypass)
    message.content = "s w e a r words"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True
        
    # Test regex match
    message.delete.reset_mock()
    message.content = "Check out this phishing-link here!"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True
        message.delete.assert_called_once()

    # Test false match (whole word boundary check)
    message.delete.reset_mock()
    message.content = "This is a class action suit"
    mock_config["automod_filters"][0]["keywords"] = ["ass"]
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False
        message.delete.assert_not_called()

    print("Literal and regex matching tests passed.")

def test_collision_precedence():
    print("Testing collision precedence matching weights...")
    guild = MagicMock()
    guild.id = 1234
    message = MagicMock()
    message.guild = guild
    message.channel = MockChannel(555, "general")
    message.author = MockMember(999, "UserA")
    message.delete = AsyncMock()
    message.content = "trigger both words"

    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f_low",
                "name": "Low Tier Swear",
                "enabled": True,
                "keywords": ["both"],
                "enforcement_action": "Delete Message Only"
            },
            {
                "id": "f_high",
                "name": "Severe Slur",
                "enabled": True,
                "keywords": ["words"],
                "enforcement_action": "Delete + Direct Penalty",
                "direct_penalty": "Permanent Ban"
            }
        ]
    }

    # Verify the high penalty action (Ban) executes instead of the low one (Delete Only)
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.trigger_automod_direct_penalty", new_callable=AsyncMock) as mock_direct:
        
        res = run_async(automod_module.handle_automod_message(message))
        assert res is True
        mock_direct.assert_called_once()
        args, _ = mock_direct.call_args
        assert args[2] == "Severe Slur"
        assert args[3] == "Permanent Ban"  # Direct penalty parameter

    print("Collision precedence tests passed.")

def test_warning_tracker_integration():
    print("Testing Warning Tracker integration logic...")
    guild = MagicMock()
    guild.id = 1234
    guild.get_channel = MagicMock(return_value=None)
    
    member = MockMember(999, "Offender")
    
    mock_config = {
        "warning_tracker_enabled": True,
        "warning_severity_points": {"High": 3},
        "warning_escalation_mode": "static",
        "warning_ladder": {"5": "Permanent ban"},
        "warning_log_channel_id": 111,
        "warning_dm_enabled": True
    }

    mock_targets = [{"platform": "Discord", "identifier": "999", "display_name": "Offender"}]
    
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("warning_tracker_module.make_discord_target", return_value=mock_targets[0]), \
         patch("warning_tracker_module.get_active_points_and_records", return_value=(2, [])), \
         patch("warning_tracker_module.execute_moderation_action", return_value="Timeout applied") as mock_exec, \
         patch("warning_tracker_module.add_warning_record", return_value={"id": "warn_123", "severity": "High", "points": 3, "details": "AutoMod violation"}) as mock_add:
        
        res = run_async(automod_module.trigger_automod_warning(guild, member, "FilterName", "High", "offending text"))
        assert "applied" in res
        # High severity (3 points) + active points (2) = 5 points -> matches ladder threshold "5" (Permanent ban)
        mock_exec.assert_called_once_with(guild, mock_targets, "Permanent ban", "AutoMod Violation for filter 'FilterName': offending text", moderator="AutoMod")
        mock_add.assert_called_once()

    print("Warning Tracker integration tests passed.")

def test_graceful_degradation():
    print("Testing graceful degradation fallback logging...")
    guild = MagicMock()
    guild.id = 1234
    guild.get_channel = MagicMock(return_value=None)
    member = MockMember(999, "Offender")

    # Scenario: Warning Tracker is disabled
    mock_config = {
        "warning_tracker_enabled": False,
        "global_log_channel_id": 222
    }

    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.log_fallback_automod_violation", new_callable=AsyncMock) as mock_fallback:
        
        # Should not raise errors, should fall back cleanly
        res = run_async(automod_module.trigger_automod_warning(guild, member, "FilterName", "High", "offending text"))
        assert "disabled" in res
        mock_fallback.assert_not_called()  # This check was warning tracker disable callback in automod_module.trigger_automod_warning

    # Check handle_automod_message fallback trigger
    message = MagicMock()
    message.guild = guild
    message.author = member
    message.content = "badword"
    message.delete = AsyncMock()
    
    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f_deg",
                "name": "Bad Words",
                "enabled": True,
                "keywords": ["badword"],
                "enforcement_action": "Delete + Warn User",
                "warning_severity": "High"
            }
        ],
        "warning_tracker_enabled": False,
        "global_log_channel_id": 222
    }
    
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.log_fallback_automod_violation", new_callable=AsyncMock) as mock_fallback:
        
        res = run_async(automod_module.handle_automod_message(message))
        assert res is True
        mock_fallback.assert_called_once()

    # Scenario: Warning Tracker is enabled (should not trigger fallback)
    mock_config["warning_tracker_enabled"] = True
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.trigger_automod_warning", new_callable=AsyncMock, return_value="Warning applied. Action: Warning. Status: Success.") as mock_warn, \
         patch("automod_module.log_fallback_automod_violation", new_callable=AsyncMock) as mock_fallback:
        
        res = run_async(automod_module.handle_automod_message(message))
        assert res is True
        mock_warn.assert_called_once()
        mock_fallback.assert_not_called()

    print("Graceful degradation fallback tests passed.")

def test_edit_filters():
    print("Testing AutoMod filter editing (keywords, action, severity)...")
    mock_config = {
        "automod_filters": [
            {
                "id": "f_edit",
                "name": "Test Edit Filter",
                "enabled": True,
                "keywords": ["old"],
                "enforcement_action": "Delete Message Only",
                "warning_severity": None,
                "direct_penalty": None
            }
        ]
    }
    
    # Test EditKeywordsModal
    modal = automod_module.EditKeywordsModal(guild_id=1234, filter_id="f_edit", current_kws=["old"])
    modal.keywords_input.value = "new, patterns, r:phish.*"
    
    interaction = MagicMock()
    interaction.response = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.message = MagicMock()
    interaction.message.edit = AsyncMock()
    
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.save_config") as mock_save, \
         patch("configuration_module.log_setting_change") as mock_log:
        
        run_async(modal.on_submit(interaction))
        
        # Verify keywords were parsed, stripped and updated
        assert mock_config["automod_filters"][0]["keywords"] == ["new", "patterns", "r:phish.*"]
        assert mock_save.called
        
    # Test EditEnforcementActionView
    view_action = automod_module.EditEnforcementActionView(guild_id=1234, filter_id="f_edit")
    mock_user = MagicMock()
    mock_user.guild = MagicMock()
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.save_config") as mock_save, \
         patch("configuration_module.log_setting_change") as mock_log:
        view_action.update_action(mock_user, "Delete Message Only")
        assert mock_config["automod_filters"][0]["enforcement_action"] == "Delete Message Only"
        assert mock_config["automod_filters"][0]["warning_severity"] is None
        assert mock_config["automod_filters"][0]["direct_penalty"] is None
        assert mock_save.called

    # Test EditSelectSeverityView
    view_severity = automod_module.EditSelectSeverityView(guild_id=1234, filter_id="f_edit")
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.save_config") as mock_save, \
         patch("configuration_module.log_setting_change") as mock_log:
        view_severity.update_severity(mock_user, "High")
        assert mock_config["automod_filters"][0]["enforcement_action"] == "Delete + Warn User"
        assert mock_config["automod_filters"][0]["warning_severity"] == "High"
        assert mock_config["automod_filters"][0]["direct_penalty"] is None
        assert mock_save.called

    # Test EditSelectPenaltyView
    view_penalty = automod_module.EditSelectPenaltyView(guild_id=1234, filter_id="f_edit")
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.save_config") as mock_save, \
         patch("configuration_module.log_setting_change") as mock_log:
        view_penalty.update_penalty(mock_user, "Permanent Ban")
        assert mock_config["automod_filters"][0]["enforcement_action"] == "Delete + Direct Penalty"
        assert mock_config["automod_filters"][0]["warning_severity"] is None
        assert mock_config["automod_filters"][0]["direct_penalty"] == "Permanent Ban"
        assert mock_save.called

    print("Filter editing tests passed.")

def test_filter_specific_exclusions():
    print("Testing filter-specific role and user exclusions...")
    guild = MagicMock()
    guild.id = 1234
    
    role1 = MockRole(101, "Admin")
    role2 = MockRole(102, "Moderator")
    
    # User has role2 (Moderator)
    author = MockMember(999, "UserA", roles=[role2])
    
    message = MagicMock()
    message.guild = guild
    message.author = author
    message.content = "badword"
    message.delete = AsyncMock()

    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f_excl",
                "name": "Bad Words",
                "enabled": True,
                "keywords": ["badword"],
                "enforcement_action": "Delete Message Only",
                "ignored_roles": [102], # Filter ignores Moderator role
                "ignored_users": []
            }
        ]
    }

    # Test role bypass
    with patch("automod_module.get_guild_config", return_value=mock_config):
        res = run_async(automod_module.handle_automod_message(message))
        assert res is False, "AutoMod should bypass filter for filter-specific ignored roles"
        message.delete.assert_not_called()

    # Test user bypass
    mock_config["automod_filters"][0]["ignored_roles"] = []
    mock_config["automod_filters"][0]["ignored_users"] = [999] # Filter ignores user 999
    with patch("automod_module.get_guild_config", return_value=mock_config):
        res = run_async(automod_module.handle_automod_message(message))
        assert res is False, "AutoMod should bypass filter for filter-specific ignored users"
        message.delete.assert_not_called()

    # Test channel bypass
    mock_config["automod_filters"][0]["ignored_users"] = []
    mock_config["automod_filters"][0]["ignored_channels"] = [555] # Filter ignores channel 555
    message.channel = MockChannel(555, "general")
    with patch("automod_module.get_guild_config", return_value=mock_config):
        res = run_async(automod_module.handle_automod_message(message))
        assert res is False, "AutoMod should bypass filter for filter-specific ignored channels"
        message.delete.assert_not_called()

    # Test active check when not bypassed
    mock_config["automod_filters"][0]["ignored_channels"] = []
    with patch("automod_module.get_guild_config", return_value=mock_config):
        res = run_async(automod_module.handle_automod_message(message))
        assert res is True, "AutoMod should intercept when user/role/channel is not ignored by this filter"
        message.delete.assert_called_once()
        
    print("Filter-specific exclusions tests passed.")

def test_delete_only_logging():
    print("Testing delete-only AutoMod logging...")
    guild = MagicMock()
    guild.id = 1234
    member = MockMember(999, "Offender")
    message = MagicMock()
    message.guild = guild
    message.author = member
    message.content = "badword"
    message.delete = AsyncMock()

    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f_del",
                "name": "Bad Words",
                "enabled": True,
                "keywords": ["badword"],
                "enforcement_action": "Delete Message Only"
            }
        ],
        "global_log_channel_id": 222
    }

    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.log_automod_delete_only", new_callable=AsyncMock) as mock_log:
        
        res = run_async(automod_module.handle_automod_message(message))
        assert res is True
        mock_log.assert_called_once_with(guild, member, "Bad Words", "badword")

    print("Delete-only AutoMod logging tests passed.")

def test_bold_offending_words():
    print("Testing bolding of offending words...")
    
    # Simple literal keyword
    res = automod_module.bold_offending_words("This is badword.", {"keywords": ["badword"]})
    assert res == "This is **badword**.", f"Expected 'This is **badword**.', got '{res}'"
    
    # Spaced literal keyword
    res = automod_module.bold_offending_words("This is b a d w o r d.", {"keywords": ["badword"]})
    assert res == "This is **b a d w o r d**.", f"Expected 'This is **b a d w o r d**.', got '{res}'"
    
    # Leet + spaced literal keyword
    res = automod_module.bold_offending_words("This is b @ d w 0 r d.", {"keywords": ["badword"]})
    assert res == "This is **b @ d w 0 r d**.", f"Expected 'This is **b @ d w 0 r d**.', got '{res}'"
    
    # Regex keyword
    res = automod_module.bold_offending_words("This is a phish link.", {"keywords": ["r:phish.*link"]})
    assert res == "This is a **phish link**.", f"Expected 'This is a **phish link**.', got '{res}'"
    
    print("Bolding of offending words tests passed.")

def test_safe_join_items():
    print("Testing safe_join_items helper...")
    from configuration_module import safe_join_items
    
    # Empty list
    assert safe_join_items([]) == "None"
    
    # Short list
    assert safe_join_items(["a", "b", "c"]) == "a, b, c"
    
    # Very long list exceeding limit
    long_list = [f"kw_{i}" for i in range(500)]
    result = safe_join_items(long_list, max_len=100)
    assert len(result) <= 100
    assert "..." in result
    assert "(and" in result
    
    print("safe_join_items tests passed.")

def test_allowed_words_and_regex():
    print("Testing whitelisting with allowed words and allowed regex...")
    
    guild = MagicMock()
    guild.id = 1234
    message = MagicMock()
    message.guild = guild
    message.channel = MockChannel(555, "general")
    message.author = MockMember(999, "UserA")
    message.delete = AsyncMock()

    # Banned word: "rape", Allowed word: "grape"
    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f_allowed_word",
                "name": "Banned Words with Exceptions",
                "enabled": True,
                "keywords": ["r:rape", "a:grape"],
                "enforcement_action": "Delete Message Only"
            }
        ]
    }

    # Case 1a: Message contains only the allowed word "grape" (which contains "rape" substring)
    message.content = "I eat some grape."
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False

    # Case 1b: Message contains both "rape" and "grape"
    message.content = "rape is bad, but grape is good"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    # Case 2: Allowed regex a:r:
    mock_config["automod_filters"][0]["keywords"] = ["r:ass", "a:r:class.*"]
    message.content = "I attend standard class today."
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False

    message.content = "you are an ass in the class"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    # Test bold_offending_words with allowed words
    res = automod_module.bold_offending_words("rape and grape", {"keywords": ["r:rape", "a:grape"]})
    assert res == "**rape** and grape", f"Expected '**rape** and grape', got '{res}'"

    res = automod_module.bold_offending_words("an ass in class", {"keywords": ["r:ass", "a:r:class.*"]})
    assert res == "an **ass** in class", f"Expected 'an **ass** in class', got '{res}'"

    print("Allowed words and regex whitelisting tests passed.")

def test_wildcard_and_whole_word_matching():
    print("Testing wildcard and whole-word keyword matching semantics...")
    guild = MagicMock()
    guild.id = 1234
    message = MagicMock()
    message.guild = guild
    message.channel = MockChannel(555, "general")
    message.author = MockMember(999, "UserA")
    message.delete = AsyncMock()

    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f_test",
                "name": "Asterisk Semantics Test",
                "enabled": True,
                "keywords": ["*ass*", "**swear**", "bad"],
                "enforcement_action": "Delete Message Only"
            }
        ]
    }

    # Test single asterisks wildcard: "*ass*"
    # This should match even when inside other words like "class" or "glass" or "ass"
    message.content = "I am in class"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    message.content = "ass"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    # Test double asterisks whole word: "**swear**"
    # This should only match whole word, not as a substring
    message.content = "I am swearing"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False

    message.content = "don't swear here"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    # Test plain keyword whole word: "bad"
    # This should only match whole word, not as a substring (e.g. "downbad" or "badly")
    message.content = "that is downbad"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False

    message.content = "that is bad"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    # Test single-sided wildcard: "*bi0" (starts with wildcard, ends with whole-word boundary)
    mock_config["automod_filters"][0]["keywords"] = ["*bi0"]
    message.content = "recheck my bi0"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    message.content = "check my bi0s"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False

    # Test single-sided wildcard: "squirting*" (starts with whole-word boundary, ends with wildcard)
    mock_config["automod_filters"][0]["keywords"] = ["squirting*"]
    message.content = "she's squirting!"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    message.content = "notsquirting at all"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False

    # Test regional indicator emojis (         )
    # 6a. Default behavior (filter_emojis = False): should not match
    mock_config["automod_filters"][0]["keywords"] = ["*check my bio*"]
    mock_config["automod_filters"][0]["filter_emojis"] = False
    message.content = "please 🇨 🇭 🇪 🇨 🇰 🇲 🇾 🇧 🇮 🇴"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False

    # 6b. With filter_emojis = True: should match!
    mock_config["automod_filters"][0]["filter_emojis"] = True
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    # Test regional indicator homoglyphs (Cyrillic a = \u0430, e = \u0435)
    # 7a. Default behavior (filter_homoglyphs = False, filter_emojis = False): should not match
    mock_config["automod_filters"][0]["keywords"] = ["*check my bio*"]
    mock_config["automod_filters"][0]["filter_emojis"] = False
    mock_config["automod_filters"][0]["filter_homoglyphs"] = False
    # Content has Cyrillic 'e' (\u0435) in check and Cyrillic 'a' (\u0430) in my
    message.content = "please ch\u0435ck my bio"
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is False

    # 7b. With filter_homoglyphs = True: should match!
    mock_config["automod_filters"][0]["filter_homoglyphs"] = True
    with patch("automod_module.get_guild_config", return_value=mock_config):
        assert run_async(automod_module.handle_automod_message(message)) is True

    print("Wildcard and whole-word keyword matching tests passed.")


def test_prepare_message_for_word_check():
    print("Testing prepare_message_for_word_check (other-bot algorithm)...")
    cases = [
        ("!play", " play play !play"),
        ("wew", "wew"),
        ("we*w", "we w wew we*w"),
        ("we**w", "we  w wew we**w"),
    ]
    for inp, expected in cases:
        res = automod_module.prepare_message_for_word_check(inp)
        assert res == expected, f"For {repr(inp)}, expected {repr(expected)}, got {repr(res)}"
    print("prepare_message_for_word_check tests passed.")


def test_on_message_edit():
    print("Testing on_message_edit event handling hook...")
    import main_entrypoint
    
    with patch("automod_module.handle_automod_message", new_callable=AsyncMock) as mock_handle:
        before = MagicMock()
        before.content = "hello"
        after = MagicMock()
        after.content = "hello"
        after.author = MockMember(999, "UserA")
        
        run_async(main_entrypoint.on_message_edit(before, after))
        mock_handle.assert_not_called()
        
        after.content = "badword"
        run_async(main_entrypoint.on_message_edit(before, after))
        mock_handle.assert_called_once_with(after)
        
    print("on_message_edit event tests passed.")


def test_nickname_moderation():
    print("Testing nickname change auto-moderation checking...")
    guild = MagicMock()
    guild.id = 1234
    
    member = MockMember(999, "UserA")
    member.guild = guild
    member.roles = []
    member.nick = "badword"
    member.edit = AsyncMock()
    
    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f_nick",
                "name": "Bad Words Nickname",
                "enabled": True,
                "keywords": ["badword"],
                "enforcement_action": "Delete Message Only"
            }
        ]
    }
    
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.log_automod_delete_only", new_callable=AsyncMock) as mock_log:
         
        res = run_async(automod_module.handle_automod_nickname(member))
        assert res is True
        member.edit.assert_called_once_with(nick=None, reason="AutoMod Nickname Violation: Bad Words Nickname")
        mock_log.assert_called_once()
        
    print("Nickname moderation tests passed.")


def test_join_moderation():
    print("Testing joining member username and global name auto-moderation...")
    guild = MagicMock()
    guild.id = 1234
    
    member = MockMember(999, "badword")
    member.guild = guild
    member.global_name = "Good Display Name"
    
    mock_config = {
        "automod_enabled": True,
        "automod_filters": [
            {
                "id": "f_join",
                "name": "Bad Words Join",
                "enabled": True,
                "keywords": ["badword"],
                "enforcement_action": "Delete + Direct Penalty",
                "direct_penalty": "Permanent Ban"
            }
        ]
    }
    
    with patch("automod_module.get_guild_config", return_value=mock_config), \
         patch("automod_module.trigger_automod_direct_penalty", new_callable=AsyncMock) as mock_direct:
         
        res = run_async(automod_module.handle_automod_join(member))
        assert res is True
        mock_direct.assert_called_once_with(guild, member, "Bad Words Join", "Permanent Ban", "Offending Username: 'badword' | Global Name: 'Good Display Name'")
        
    print("Join moderation tests passed.")


def test_condition_tags():
    print("Testing condition tags (c:age, c:bot, c:attachment, c:thread)...")
    member = MockMember(999, "UserA")
    # C:bot / c:human
    member.bot = True
    assert automod_module.evaluate_condition("c:bot", member) is True
    assert automod_module.evaluate_condition("c:human", member) is False
    member.bot = False
    assert automod_module.evaluate_condition("c:bot", member) is False
    assert automod_module.evaluate_condition("c:human", member) is True
    
    member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
    assert automod_module.evaluate_condition("c:age:60", member) is True
    assert automod_module.evaluate_condition("c:age:10", member) is False
    
    member.joined_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
    assert automod_module.evaluate_condition("c:member_age:60", member) is True
    assert automod_module.evaluate_condition("c:member_age:10", member) is False
    
    # C:attachment / c:no_attachment
    message = MagicMock()
    message.attachments = []
    assert automod_module.evaluate_condition("c:attachment", member, message) is False
    assert automod_module.evaluate_condition("c:no_attachment", member, message) is True
    message.attachments = [MagicMock()]
    assert automod_module.evaluate_condition("c:attachment", member, message) is True
    assert automod_module.evaluate_condition("c:no_attachment", member, message) is False
    
    # C:thread / c:no_thread
    message.channel = MockThread()
    assert automod_module.evaluate_condition("c:thread", member, message) is True
    assert automod_module.evaluate_condition("c:no_thread", member, message) is False
    message.channel = MockChannel(555, "general")
    assert automod_module.evaluate_condition("c:thread", member, message) is False
    assert automod_module.evaluate_condition("c:no_thread", member, message) is True
    
    print("Condition tags tests passed.")


def test_trigger_tags():
    print("Testing trigger tags (t:mentions, t:caps, t:length, t:invite, t:link, t:phishing, t:spam)...")
    member = MockMember(999, "UserA")
    message = MagicMock()
    message.author = member
    
    message.content = "abc"
    assert run_async(automod_module.evaluate_trigger("t:length:5", member, message)) is False
    message.content = "abcdef"
    assert run_async(automod_module.evaluate_trigger("t:length:5", member, message)) is True
    
    m1 = MagicMock()
    m1.id = 111
    message.mentions = [m1]
    assert run_async(automod_module.evaluate_trigger("t:mentions:2", member, message)) is False
    m2 = MagicMock()
    m2.id = 222
    message.mentions = [m1, m2]
    assert run_async(automod_module.evaluate_trigger("t:mentions:2", member, message)) is True
    
    message.content = "Hello"
    assert run_async(automod_module.evaluate_trigger("t:caps:50", member, message)) is False
    message.content = "HELLO"
    assert run_async(automod_module.evaluate_trigger("t:caps:80", member, message)) is True
    
    message.content = "check my server discord.gg/abc"
    assert run_async(automod_module.evaluate_trigger("t:invite", member, message)) is True
    message.content = "no invite here"
    assert run_async(automod_module.evaluate_trigger("t:invite", member, message)) is False
    
    message.content = "visit https://google.com"
    assert run_async(automod_module.evaluate_trigger("t:link", member, message)) is True
    message.content = "no link here"
    assert run_async(automod_module.evaluate_trigger("t:link", member, message)) is False
    
    message.content = "get free-nitro here!"
    assert run_async(automod_module.evaluate_trigger("t:phishing", member, message)) is True
    message.content = "just normal text"
    assert run_async(automod_module.evaluate_trigger("t:phishing", member, message)) is False
    
    msg_history = []
    for _ in range(5):
        m_old = MagicMock()
        m_old.created_at = datetime.datetime.now(datetime.timezone.utc)
        m_old.author.id = 999
        m_old.content = "spam content"
        m_old.attachments = []
        msg_history.append(m_old)
        
    class AsyncHistory:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            self.items_iter = iter(self.items)
            return self
        async def __anext__(self):
            try:
                return next(self.items_iter)
            except StopIteration:
                raise StopAsyncIteration
                
    message.content = "spam content"
    message.attachments = []
    message.channel.history = MagicMock(return_value=AsyncHistory(msg_history))
    
    assert run_async(automod_module.evaluate_trigger("t:spam:5:30", member, message)) is True
    assert run_async(automod_module.evaluate_trigger("t:spam:10:30", member, message)) is False
    
    print("Trigger tags tests passed.")


def test_tags_integration():
    print("Testing tags integration inside check_text_against_keywords...")
    member = MockMember(999, "UserA")
    member.bot = True
    
    keywords = ["c:bot", "t:length:5"]
    message = MagicMock()
    message.content = "abc"
    
    assert run_async(automod_module.check_text_against_keywords("abc", keywords, member=member, message=message)) is False
    
    message.content = "abcdef"
    assert run_async(automod_module.check_text_against_keywords("abcdef", keywords, member=member, message=message)) is True
    
    member.bot = False
    assert run_async(automod_module.check_text_against_keywords("abcdef", keywords, member=member, message=message)) is False
    
    print("Tags integration tests passed.")


if __name__ == "__main__":
    test_text_normalization()
    print("-" * 40)
    test_bypass_checks()
    print("-" * 40)
    test_literal_and_regex_matching()
    print("-" * 40)
    test_collision_precedence()
    print("-" * 40)
    test_warning_tracker_integration()
    print("-" * 40)
    test_graceful_degradation()
    print("-" * 40)
    test_edit_filters()
    print("-" * 40)
    test_filter_specific_exclusions()
    print("-" * 40)
    test_delete_only_logging()
    print("-" * 40)
    test_bold_offending_words()
    print("-" * 40)
    test_safe_join_items()
    print("-" * 40)
    test_allowed_words_and_regex()
    print("-" * 40)
    test_wildcard_and_whole_word_matching()
    print("-" * 40)
    test_prepare_message_for_word_check()
    print("-" * 40)
    test_on_message_edit()
    print("-" * 40)
    test_nickname_moderation()
    print("-" * 40)
    test_join_moderation()
    print("-" * 40)
    test_condition_tags()
    print("-" * 40)
    test_trigger_tags()
    print("-" * 40)
    test_tags_integration()
    print("-" * 40)
    print("ALL AUTOMOD UNIT TESTS PASSED!")
