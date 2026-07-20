import os
import json
import asyncio
import datetime
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

import configuration_module
import analytics_module
from admin_ui_module import ModuleSelectView

def run_async(coro):
    return asyncio.run(coro)

    for f in [configuration_module.CONFIG_FILE, analytics_module.ANALYTICS_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

import test_db_helper
test_db_helper.init_test_db()

def setup_module():
    pass

def teardown_module():
    pass

mock_config = {
    "analytics_enabled": True,
    "analytics_excluded_channels": [222],
    "mod_role_id": 999
}

@pytest.mark.asyncio
async def test_message_velocity():
    print("Testing message velocity tracking...")
    
    # Setup mock message
    message = MagicMock()
    message.author.bot = False
    message.guild.id = 111
    message.channel.id = 123
    
    with patch("analytics_module.get_guild_config", return_value=mock_config):
        await analytics_module.handle_message_velocity(message)
        
        # Verify it saved message count
        records = await analytics_module.load_analytics_records()
        assert "111" in records
        assert "messages" in records["111"]
        assert "123" in records["111"]["messages"]
        
        # Trigger same channel again
        await analytics_module.handle_message_velocity(message)
        records = await analytics_module.load_analytics_records()
        hour_str = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:00:00Z")
        assert records["111"]["messages"]["123"][hour_str] == 2

    # Excluded channel test
    message_excluded = MagicMock()
    message_excluded.author.bot = False
    message_excluded.guild.id = 111
    message_excluded.channel.id = 222 # Excluded in mock_config
    
    with patch("analytics_module.get_guild_config", return_value=mock_config):
        await analytics_module.handle_message_velocity(message_excluded)
        records = await analytics_module.load_analytics_records()
        assert "222" not in records["111"]["messages"]
        
    print("Message velocity tracking tests passed.")

@pytest.mark.asyncio
async def test_member_churn():
    print("Testing member join and leave tracking...")
    
    member = MagicMock()
    member.guild.id = 111
    member.id = 456
    
    with patch("analytics_module.get_guild_config", return_value=mock_config):
        await analytics_module.handle_member_join(member)
        await analytics_module.handle_member_leave(member)
        
        records = await analytics_module.load_analytics_records()
        assert "churn" in records["111"]
        assert len(records["111"]["churn"]) == 2
        assert records["111"]["churn"][0]["event"] == "join"
        assert records["111"]["churn"][0]["user_id"] == 456
        assert records["111"]["churn"][1]["event"] == "leave"
        assert records["111"]["churn"][1]["user_id"] == 456
        
    print("Member churn tracking tests passed.")

@pytest.mark.asyncio
async def test_voice_concurrency():
    print("Testing voice presence tracking...")
    
    member = MagicMock()
    member.bot = False
    member.guild.id = 111
    
    vc1 = MagicMock()
    m1 = MagicMock()
    m1.bot = False
    vc1.members = [m1]
    
    vc2 = MagicMock()
    m2 = MagicMock()
    m2.bot = False
    m3 = MagicMock()
    m3.bot = True # Bot should be ignored
    vc2.members = [m2, m3]
    
    member.guild.voice_channels = [vc1, vc2]
    
    before = MagicMock()
    before.channel = None
    after = MagicMock()
    after.channel = vc1
    
    with patch("analytics_module.get_guild_config", return_value=mock_config):
        await analytics_module.handle_voice_update(member, before, after)
        
        records = await analytics_module.load_analytics_records()
        assert "voice" in records["111"]
        # Total non-bot members = m1 + m2 = 2
        assert records["111"]["voice"][0]["count"] == 2
        
    print("Voice presence tracking tests passed.")

@pytest.mark.asyncio
async def test_analytics_slash_command():
    print("Testing /analytics slash command output layout...")
    
    hour_str = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:00:00Z")
    mock_records = {
        "111": {
            "messages": {
                "123": {
                    hour_str: 10
                }
            },
            "churn": [
                {"event": "join", "user_id": 1, "timestamp": datetime.datetime.utcnow().timestamp()},
                {"event": "leave", "user_id": 2, "timestamp": datetime.datetime.utcnow().timestamp()}
            ],
            "voice": [
                {"timestamp": datetime.datetime.utcnow().timestamp(), "count": 3},
                {"timestamp": datetime.datetime.utcnow().timestamp(), "count": 5}
            ]
        }
    }
    
    interaction = MagicMock()
    interaction.guild_id = 111
    interaction.guild.name = "Test Guild"
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    with patch("analytics_module.load_analytics_records", return_value=mock_records), \
         patch("analytics_module.is_mod", return_value=True), \
         patch("analytics_module.get_guild_config", return_value=mock_config):
         
        tree = MagicMock()
        registered_commands = {}
        def command_decorator(*args, **kwargs):
            name = kwargs.get("name")
            def decorator(func):
                registered_commands[name] = func
                return func
            return decorator
        tree.command = command_decorator
        
        analytics_module.setup_analytics_commands(tree)
        
        # Trigger Callback
        await registered_commands["analytics"](interaction, "24h")
        
        # Verify defer and send was called
        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        
        args, kwargs = interaction.followup.send.call_args
        embed = kwargs.get("embed")
        assert embed is not None
        assert "Server Analytics Report for Test Guild" in embed.title
        assert len(embed.fields) == 3
        
        # Ensure no emojis exist in fields, title, or description
        for field in embed.fields:
            assert all(ord(char) < 127 for char in field.name)
            assert all(ord(char) < 127 or char in "<#>" for char in field.value) # allow discord mention chars
            
        assert all(ord(char) < 127 for char in embed.title)
        assert all(ord(char) < 127 for char in embed.description)
        
    print("Analytics slash command layout tests passed.")

@pytest.mark.asyncio
async def test_analytics_dashboard_view():
    print("Testing AnalyticsConfigDashboard views and callbacks...")
    
    interaction = MagicMock()
    interaction.guild.id = 111
    interaction.user.id = 12345
    interaction.response.edit_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    
    # Test build embed
    dashboard = analytics_module.AnalyticsConfigDashboard(111)
    with patch("analytics_module.get_guild_config", return_value=mock_config):
        embed = dashboard.build_embed()
        assert "Nebot Module: Server Analytics" in embed.title
        assert "[ENABLED]" in embed.fields[0].value
        
    # Test toggle analytics
    mock_guild_cfg = {"analytics_enabled": True}
    with patch("analytics_module.get_guild_config", return_value=mock_guild_cfg), \
         patch("analytics_module.save_config") as mock_save, \
         patch("configuration_module.log_setting_change_task") as mock_log, \
         patch("configuration_module.refresh_interaction") as mock_refresh:
        
        cb = dashboard.toggle_analytics.callback
        await cb(interaction)
            
        assert mock_guild_cfg["analytics_enabled"] is False
        assert mock_save.called
        assert mock_log.called
        assert mock_refresh.called
        
    # Test clear historical data
    with patch("analytics_module.get_guild_config", return_value=mock_config), \
         patch("configuration_module.log_setting_change_task") as mock_log, \
         patch("configuration_module.refresh_interaction") as mock_refresh:
        
        # Set some records
        records = {"111": {"messages": {}}}
        with patch("analytics_module.load_analytics_records", return_value=records), \
             patch("analytics_module.save_analytics_records") as mock_save_rec:
             
            cb = dashboard.clear_historical_data.callback
            await cb(interaction)
                
            assert "111" not in records
            assert mock_save_rec.called
            assert mock_log.called
            assert mock_refresh.called

    # 3.5. Test Back to Modules
    with patch("admin_ui_module.ModuleSelectView") as mock_view_cls:
        mock_view = MagicMock()
        mock_view.build_embed.return_value = MagicMock()
        mock_view_cls.return_value = mock_view
        
        cb = dashboard.back_to_modules.callback
        await cb(interaction)
            
        assert mock_view.build_embed.called
        assert interaction.response.edit_message.called
            
    # Test select callback
    select = analytics_module.AnalyticsExcludedChannelsSelect(111)
    view = discord.ui.View()
    view.refresh = AsyncMock()
    view.add_item(select)
    
    mock_guild_cfg2 = {"analytics_excluded_channels": []}
    from unittest.mock import PropertyMock
    with patch.object(analytics_module.AnalyticsExcludedChannelsSelect, "values", new_callable=PropertyMock) as mock_values, \
         patch("analytics_module.get_guild_config", return_value=mock_guild_cfg2), \
         patch("analytics_module.save_config") as mock_save, \
         patch("configuration_module.log_setting_change_task") as mock_log:
         
        mock_values.return_value = [MagicMock(id=123), MagicMock(id=456)]
        
        await select.callback(interaction)
        assert mock_guild_cfg2["analytics_excluded_channels"] == [123, 456]
        assert mock_save.called
        assert mock_log.called
        select.view.refresh.assert_called_once_with(interaction)

    print("AnalyticsConfigDashboard tests passed.")

if __name__ == "__main__":
    setup_module()
    try:
        run_async(test_message_velocity())
        run_async(test_member_churn())
        run_async(test_voice_concurrency())
        run_async(test_analytics_slash_command())
        run_async(test_analytics_dashboard_view())
        print("ALL SERVER ANALYTICS TESTS PASSED!")
    finally:
        teardown_module()
