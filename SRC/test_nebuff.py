import pytest
import discord
from unittest.mock import AsyncMock, patch

import nebuff_module

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_disabled(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": False}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "I am 5'4\" tall"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is False
    msg.reply.assert_not_called()

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_bot_author(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = True
    msg.guild.id = 123
    msg.content = "I am 5'4\" tall"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is False
    msg.reply.assert_not_called()

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_quote_pattern(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "I am 5'4\" tall"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is True
    msg.reply.assert_called_once_with("That would be 1.19 nebuff's")

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_quote_pattern_spaced(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "I am 5' 4\" tall"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is True
    msg.reply.assert_called_once_with("That would be 1.19 nebuff's")

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_quote_pattern_reversed(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "I am 4\"2' tall"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is True
    # 4 * 12 + 2 = 50 inches. 50 / 54 = 0.925925..
    msg.reply.assert_called_once_with("That would be 0.93 nebuff's")

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_cm(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "This is 12cm wide"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is True
    # 12 cm = 4.7244 inches. 4.7244 / 54 = 0.0874..
    msg.reply.assert_called_once_with("That would be 0.09 nebuff's")

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_f(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "I have a 4f long stick"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is True
    # 4 ft = 48 inches. 48 / 54 = 0.8888..
    msg.reply.assert_called_once_with("That would be 0.89 nebuff's")

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_m(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "it's about 10 meters long"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is True
    # 10 m = 393.7 inches. 393.7 / 54 = 7.29..
    msg.reply.assert_called_once_with("That would be 7.29 nebuff's")

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_nebuffs(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "That's 14 nebuffs"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is True
    # 14 nebuffs * 1.3716 = 19.2024
    msg.reply.assert_called_once_with("That would be 19.2 meters")

@pytest.mark.asyncio
@patch('nebuff_module.get_guild_config')
async def test_handle_nebuff_message_nebuff_apostrophe_s(mock_get_guild_config):
    mock_get_guild_config.return_value = {"nebuff_module_enabled": True}
    msg = AsyncMock(spec=discord.Message)
    msg.author.bot = False
    msg.guild.id = 123
    msg.content = "That's 14 nebuff's"

    res = await nebuff_module.handle_nebuff_message(msg)
    assert res is True
    msg.reply.assert_called_once_with("That would be 19.2 meters")
