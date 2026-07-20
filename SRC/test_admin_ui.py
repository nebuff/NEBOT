import pytest
import discord
from unittest.mock import AsyncMock, patch, MagicMock

import admin_ui_module

@pytest.mark.asyncio
@patch("admin_ui_module.get_guild_config")
@patch("admin_ui_module.is_mod")
async def test_mod_ban_modal_permission_denied(mock_is_mod, mock_get_guild_config):
    mock_get_guild_config.return_value = {}
    mock_is_mod.return_value = False

    # Create mock interaction
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 123
    interaction.user = MagicMock()
    interaction.response = AsyncMock()

    modal = admin_ui_module.ModBanModal()

    await modal.on_submit(interaction)

    mock_is_mod.assert_called_once_with(interaction.user, {})
    interaction.response.send_message.assert_called_once_with("Permission denied.", ephemeral=True)

@pytest.mark.asyncio
@patch("admin_ui_module.get_guild_config")
@patch("admin_ui_module.is_mod")
async def test_mod_kick_modal_permission_denied(mock_is_mod, mock_get_guild_config):
    mock_get_guild_config.return_value = {}
    mock_is_mod.return_value = False

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 123
    interaction.user = MagicMock()
    interaction.response = AsyncMock()

    modal = admin_ui_module.ModKickModal()
    await modal.on_submit(interaction)

    mock_is_mod.assert_called_once_with(interaction.user, {})
    interaction.response.send_message.assert_called_once_with("Permission denied.", ephemeral=True)

@pytest.mark.asyncio
@patch("admin_ui_module.get_guild_config")
@patch("admin_ui_module.is_mod")
async def test_mod_send_warning_modal_permission_denied(mock_is_mod, mock_get_guild_config):
    mock_get_guild_config.return_value = {}
    mock_is_mod.return_value = False

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 123
    interaction.user = MagicMock()
    interaction.response = AsyncMock()

    modal = admin_ui_module.ModSendWarningModal(guild_id=123)
    await modal.on_submit(interaction)

    mock_is_mod.assert_called_once_with(interaction.user, {})
    interaction.response.send_message.assert_called_once_with("Permission denied.", ephemeral=True)

@pytest.mark.asyncio
@patch("admin_ui_module.get_guild_config")
@patch("admin_ui_module.is_mod")
async def test_mod_view_warning_modal_permission_denied(mock_is_mod, mock_get_guild_config):
    mock_get_guild_config.return_value = {}
    mock_is_mod.return_value = False

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 123
    interaction.user = MagicMock()
    interaction.response = AsyncMock()

    modal = admin_ui_module.ModViewWarningModal()
    await modal.on_submit(interaction)

    mock_is_mod.assert_called_once_with(interaction.user, {})
    interaction.response.send_message.assert_called_once_with("Permission denied.", ephemeral=True)

@pytest.mark.asyncio
@patch("admin_ui_module.get_guild_config")
@patch("admin_ui_module.is_mod")
async def test_mod_delete_warning_modal_permission_denied(mock_is_mod, mock_get_guild_config):
    mock_get_guild_config.return_value = {}
    mock_is_mod.return_value = False

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 123
    interaction.user = MagicMock()
    interaction.response = AsyncMock()

    modal = admin_ui_module.ModDeleteWarningModal()
    await modal.on_submit(interaction)

    mock_is_mod.assert_called_once_with(interaction.user, {})
    interaction.response.send_message.assert_called_once_with("Permission denied.", ephemeral=True)
