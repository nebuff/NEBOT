import os
import sys
import json
import asyncio
import datetime
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

import configuration_module
import vc_wr_module

def run_async(coro):
    return asyncio.run(coro)


    for f in [configuration_module.CONFIG_FILE, vc_wr_module.VC_WR_RECORDS_FILE, vc_wr_module.VC_WR_SESSIONS_FILE]:
        if os.path.exists(f):
            os.remove(f)

import test_db_helper
test_db_helper.init_test_db()

def setup_module():
    pass

def teardown_module():
    pass

# Tests

mock_config = {
    "vc_wr_enabled": True,
    "vc_wr_allowed_channels": [222],
    "vc_wr_leaderboard_size": 5,
    "vc_wr_live_channel_id": 333,
    "vc_wr_live_message_id": None
}

@pytest.mark.asyncio
async def test_handle_voice_state_update_join_leave():
    print("Testing handle_voice_state_update for join and leave events...")

    # Setup mocks
    client = MagicMock()
    member = MagicMock()
    member.bot = False
    member.guild.id = 111
    member.id = 999
    member.send = AsyncMock()

    before_join = MagicMock()
    before_join.channel = None
    after_join = MagicMock()
    after_join.channel = MagicMock()
    after_join.channel.id = 222

    # Test Join
    with patch("vc_wr_module.update_live_message", new_callable=AsyncMock) as mock_update_live, \
         patch("vc_wr_module.get_guild_config", return_value=mock_config):
        await vc_wr_module.handle_voice_state_update(member, before_join, after_join, client)
        sessions = await vc_wr_module.load_vc_wr_sessions()
        assert "111" in sessions
        assert "999" in sessions["111"]
        mock_update_live.assert_called_once()

    # Simulate time passing and Test Leave
    # Manipulate join time so we have a duration > 0
    sessions = await vc_wr_module.load_vc_wr_sessions()
    sessions["111"]["999"] -= 100 # 100 seconds ago
    await vc_wr_module.save_vc_wr_sessions(sessions)

    before_leave = after_join
    after_leave = MagicMock()
    after_leave.channel = None

    with patch("vc_wr_module.update_live_message", new_callable=AsyncMock) as mock_update_live, \
         patch("vc_wr_module.get_guild_config", return_value=mock_config):
        await vc_wr_module.handle_voice_state_update(member, before_leave, after_leave, client)

        # Verify session is gone
        sessions = await vc_wr_module.load_vc_wr_sessions()
        assert "999" not in sessions.get("111", {})

        # Verify record is saved
        records = await vc_wr_module.load_vc_wr_records()
        assert records["111"]["999"] >= 100

        mock_update_live.assert_called_once()
        member.send.assert_called_once_with("You have just made your way into the leaderboard!")

    # Test Second Session (Cumulative Addition)
    with patch("vc_wr_module.update_live_message", new_callable=AsyncMock) as mock_update_live, \
         patch("vc_wr_module.get_guild_config", return_value=mock_config):
        await vc_wr_module.handle_voice_state_update(member, before_join, after_join, client)
        sessions = await vc_wr_module.load_vc_wr_sessions()
        assert "999" in sessions["111"]

    # Manipulate join time so we have a duration of 50 seconds
    sessions = await vc_wr_module.load_vc_wr_sessions()
    sessions["111"]["999"] -= 50
    await vc_wr_module.save_vc_wr_sessions(sessions)

    member.send.reset_mock()
    with patch("vc_wr_module.update_live_message", new_callable=AsyncMock) as mock_update_live, \
         patch("vc_wr_module.get_guild_config", return_value=mock_config):
        await vc_wr_module.handle_voice_state_update(member, before_leave, after_leave, client)

        # Verify session is gone
        sessions = await vc_wr_module.load_vc_wr_sessions()
        assert "999" not in sessions.get("111", {})

        # Verify record is saved cumulatively (100 + 50 = 150)
        records = await vc_wr_module.load_vc_wr_records()
        assert records["111"]["999"] >= 150
        assert records["111"]["999"] < 155

        # Verify they did NOT get a DM since they were already on the leaderboard
        member.send.assert_not_called()

    print("handle_voice_state_update join and leave events passed.")


@pytest.mark.asyncio
async def test_live_message_update():
    print("Testing update_live_message...")
    client = MagicMock()
    guild = MagicMock()
    client.get_guild.return_value = guild
    channel = AsyncMock()
    guild.get_channel.return_value = channel

    msg = MagicMock()
    msg.id = 555
    # Important: make send an AsyncMock itself so await works correctly returning msg
    channel.send = AsyncMock(return_value=msg)

    with patch("vc_wr_module.get_guild_config", return_value=mock_config), \
         patch("vc_wr_module.save_config"):
        await vc_wr_module.update_live_message(111, client)

    channel.send.assert_called_once()
    print("update_live_message passed.")

@pytest.mark.asyncio
async def test_stats_integration():
    print("Testing get_user_vc_wr_stats...")
    stats = await vc_wr_module.get_user_vc_wr_stats(111, 999)
    if stats.get("rank") is None:
        # Ensure we prep DB so rank matches expectations
        records = await vc_wr_module.load_vc_wr_records()
        records["111"] = records.get("111", {})
        records["111"]["999"] = 100.0
        await vc_wr_module.save_vc_wr_records(records)
        stats = await vc_wr_module.get_user_vc_wr_stats(111, 999)
    assert stats["rank"] == 1
    assert stats["record"] >= 100
    print("get_user_vc_wr_stats passed.")

if __name__ == "__main__":
    setup_module()
    try:
        run_async(test_handle_voice_state_update_join_leave())
        run_async(test_live_message_update())
        run_async(test_stats_integration())
        print("ALL VC WR TESTS PASSED!")
    finally:
        teardown_module()
