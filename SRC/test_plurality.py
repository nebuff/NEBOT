import pytest
import discord
from unittest.mock import MagicMock, AsyncMock, patch
import json
import os
import shutil

import test_db_helper
test_db_helper.init_test_db()

from plurality_module import (
    load_plurality_data,
    save_plurality_data,
    plurality_data
)

@pytest.fixture(autouse=True)
def clean_data():
    global plurality_data
    plurality_data.clear()
    test_db_helper.init_test_db()
    
    yield
    plurality_data.clear()
    import db_service
    db_service.close_db_connection()

def test_load_save_db():
    plurality_data["123"] = {
        "system_name": "Test System",
        "members": {}
    }
    save_plurality_data()

    plurality_data.clear()
    load_plurality_data()

    assert "123" in plurality_data
    assert plurality_data["123"]["system_name"] == "Test System"

def test_system_structure():
    plurality_data["456"] = {
        "system_name": "Structure Test",
        "members": {
            "m1": {
                "display_name": "Member 1",
                "avatar_url": "http://example.com/avatar.png",
                "proxy_tag": "m1:text"
            }
        }
    }
    save_plurality_data()
    plurality_data.clear()
    load_plurality_data()

    assert plurality_data["456"]["members"]["m1"]["display_name"] == "Member 1"
    assert plurality_data["456"]["members"]["m1"]["proxy_tag"] == "m1:text"


from plurality_module import (
    setup_plurality_commands,
    handle_plurality_message,
    webhook_cache
)

@pytest.fixture
def mock_tree():
    tree = MagicMock()
    setup_plurality_commands(tree)
    system_group = tree.add_command.call_args_list[0][0][0]
    member_group = tree.add_command.call_args_list[1][0][0]
    return system_group, member_group

@pytest.mark.asyncio
async def test_system_register(mock_tree):
    system_group, _ = mock_tree

    cmd = None
    for c in system_group.commands:
        if c.name == "register":
            cmd = c

    assert cmd is not None

    interaction = AsyncMock()
    interaction.user.id = 999

    await cmd.callback(interaction, "My System")

    assert "999" in plurality_data
    assert plurality_data["999"]["system_name"] == "My System"
    interaction.response.send_message.assert_called_with("System 'My System' registered successfully.", ephemeral=True)

@pytest.mark.asyncio
async def test_member_add(mock_tree):
    _, member_group = mock_tree

    cmd_add = None
    for c in member_group.commands:
        if c.name == "add":
            cmd_add = c

    assert cmd_add is not None

    interaction = AsyncMock()
    interaction.user.id = 777

    await cmd_add.callback(interaction, "m1", "Member One")
    interaction.response.send_message.assert_called_with("You do not have a system registered. Use /system register first.", ephemeral=True)

    plurality_data["777"] = {"system_name": "S", "members": {}}

    await cmd_add.callback(interaction, "m1", "Member One")
    assert "m1" in plurality_data["777"]["members"]
    assert plurality_data["777"]["members"]["m1"]["display_name"] == "Member One"

@pytest.mark.asyncio
async def test_webhook_engine_execution():
    from configuration_module import save_config, get_guild_config

    cfg = get_guild_config(10)
    cfg["plurality_enabled"] = True
    save_config()

    plurality_data["1010"] = {
        "system_name": "Sys",
        "members": {
            "m1": {
                "display_name": "Alter 1",
                "avatar_url": "http://img.com/a.png",
                "proxy_tag": "a1:text"
            },
            "m2": {
                "display_name": "Alter 2",
                "avatar_url": None,
                "proxy_tag": "[text]"
            }
        }
    }

    message = AsyncMock(spec=discord.Message)
    message.author.bot = False
    message.author.id = 1010
    message.guild.id = 10
    message.channel = AsyncMock(spec=discord.TextChannel)
    message.channel.id = 20
    message.reference = None

    wh_mock = AsyncMock(spec=discord.Webhook)
    wh_mock.token = "token123"
    message.channel.webhooks.return_value = [wh_mock]
    webhook_cache.clear()

    client = AsyncMock(spec=discord.Client)

    message.content = "a1:hello world"
    await handle_plurality_message(message, client)

    message.delete.assert_called_once()
    wh_mock.send.assert_called_once_with(
        content="hello world",
        username="Alter 1",
        avatar_url="http://img.com/a.png",
        wait=True
    )

    message.delete.reset_mock()
    wh_mock.send.reset_mock()

    message.content = "[this is a test]"
    await handle_plurality_message(message, client)

    message.delete.assert_called_once()
    wh_mock.send.assert_called_once_with(
        content="this is a test",
        username="Alter 2",
        avatar_url=None,
        wait=True
    )

@pytest.mark.asyncio
async def test_rate_limit_handling():
    from configuration_module import save_config, get_guild_config

    cfg = get_guild_config(10)
    cfg["plurality_enabled"] = True
    save_config()

    plurality_data["1010"] = {
        "system_name": "Sys",
        "members": {
            "m1": {
                "display_name": "Alter 1",
                "avatar_url": None,
                "proxy_tag": "[text]"
            }
        }
    }

    message = AsyncMock(spec=discord.Message)
    message.author.bot = False
    message.author.id = 1010
    message.guild.id = 10
    message.channel = AsyncMock(spec=discord.TextChannel)
    message.channel.id = 20
    message.content = "[spam spam]"
    message.reference = None

    wh_mock = AsyncMock(spec=discord.Webhook)
    wh_mock.token = "token123"
    wh_mock.send.side_effect = discord.HTTPException(response=MagicMock(), message="Rate limited")
    message.channel.webhooks.return_value = [wh_mock]
    webhook_cache.clear()

    client = AsyncMock(spec=discord.Client)

    # Should not raise exception
    await handle_plurality_message(message, client)
    message.delete.assert_called_once()
    wh_mock.send.assert_called_once()

@pytest.mark.asyncio
async def test_webhook_reply_handling():
    from configuration_module import save_config, get_guild_config

    cfg = get_guild_config(10)
    cfg["plurality_enabled"] = True
    save_config()

    plurality_data["1010"] = {
        "system_name": "Sys",
        "system_tag": "[SYS]",
        "members": {
            "m1": {
                "display_name": "Member 1",
                "avatar_url": None,
                "proxy_tag": "[text]"
            }
        }
    }

    message = AsyncMock(spec=discord.Message)
    message.author.bot = False
    message.author.id = 1010
    message.guild.id = 10
    message.channel = AsyncMock(spec=discord.TextChannel)
    message.channel.id = 20
    message.content = "[hello world]"

    mock_ref = MagicMock(spec=discord.MessageReference)
    mock_ref.message_id = 999
    message.reference = mock_ref

    replied_message = AsyncMock(spec=discord.Message)
    replied_message.author.mention = "<@444>"
    replied_message.jump_url = "https://discord.com/channels/10/20/999"
    message.channel.fetch_message = AsyncMock(return_value=replied_message)

    wh_mock = AsyncMock(spec=discord.Webhook)
    wh_mock.token = "token123"
    message.channel.webhooks.return_value = [wh_mock]
    webhook_cache.clear()

    client = AsyncMock(spec=discord.Client)

    await handle_plurality_message(message, client)

    message.delete.assert_called_once()
    wh_mock.send.assert_called_once_with(
        content="**↳ Replying to** <@444> *([Jump to Message](<https://discord.com/channels/10/20/999>))*\nhello world",
        username="Member 1 [SYS]",
        avatar_url=None,
        wait=True
    )

@pytest.mark.asyncio
async def test_auto_proxy_execution():
    from configuration_module import save_config, get_guild_config

    cfg = get_guild_config(10)
    cfg["plurality_enabled"] = True
    save_config()

    plurality_data["1010"] = {
        "system_name": "Sys",
        "fronting_member": "m1",
        "members": {
            "m1": {
                "display_name": "Member 1",
                "avatar_url": None,
                "proxy_tag": "[text]"
            }
        }
    }

    message = AsyncMock(spec=discord.Message)
    message.author.bot = False
    message.author.id = 1010
    message.guild.id = 10
    message.channel = AsyncMock(spec=discord.TextChannel)
    message.channel.id = 20
    message.content = "this message has no tags but should auto proxy"
    message.reference = None

    wh_mock = AsyncMock(spec=discord.Webhook)
    wh_mock.token = "token123"
    message.channel.webhooks.return_value = [wh_mock]
    webhook_cache.clear()

    client = AsyncMock(spec=discord.Client)

    res = await handle_plurality_message(message, client)
    assert res is True


@pytest.mark.asyncio
async def test_reply_delete_command():
    from configuration_module import save_config, get_guild_config
    from plurality_module import proxied_messages, add_proxied_message, webhook_cache

    cfg = get_guild_config(10)
    cfg["plurality_enabled"] = True
    save_config()

    proxied_messages.clear()
    webhook_cache.clear()
    add_proxied_message("8888", 1010, "Original Content", "", 20)

    message = AsyncMock(spec=discord.Message)
    message.author.bot = False
    message.author.id = 1010
    message.guild.id = 10
    message.channel = AsyncMock(spec=discord.TextChannel)
    message.channel.id = 20
    message.content = "delete"
    
    mock_ref = MagicMock(spec=discord.MessageReference)
    mock_ref.message_id = 8888
    message.reference = mock_ref

    client = AsyncMock(spec=discord.Client)

    # Let's mock channel.send to return a confirmation message
    conf_msg = AsyncMock(spec=discord.Message)
    message.channel.send = AsyncMock(return_value=conf_msg)

    from plurality_module import handle_plurality_message
    res = await handle_plurality_message(message, client)
    assert res is True

    # User's triggering message should be deleted
    message.delete.assert_called_once()
    
    # Confirmation prompt should be sent with a view
    message.channel.send.assert_called_once()
    args, kwargs = message.channel.send.call_args
    assert "delete" in kwargs.get("content", "")
    view = kwargs.get("view")
    assert view is not None

    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user.id = 1010
    interaction.message = conf_msg
    interaction.response.send_message = AsyncMock()

    client.get_channel.return_value = message.channel

    wh_mock = AsyncMock(spec=discord.Webhook)
    message.channel.webhooks.return_value = [wh_mock]
    
    await view.delete_btn.callback(interaction)
    
    wh_mock.delete_message.assert_called_once_with(8888)
    # Confirmation message deleted
    conf_msg.delete.assert_called_once()
    # Message removed from cache
    assert "8888" not in proxied_messages


@pytest.mark.asyncio
async def test_reply_edit_command():
    from configuration_module import save_config, get_guild_config
    from plurality_module import proxied_messages, add_proxied_message, webhook_cache

    cfg = get_guild_config(10)
    cfg["plurality_enabled"] = True
    save_config()

    proxied_messages.clear()
    webhook_cache.clear()
    add_proxied_message("9999", 1010, "Original Content", "", 20)

    message = AsyncMock(spec=discord.Message)
    message.author.bot = False
    message.author.id = 1010
    message.guild.id = 10
    message.channel = AsyncMock(spec=discord.TextChannel)
    message.channel.id = 20
    message.content = "edit"
    
    mock_ref = MagicMock(spec=discord.MessageReference)
    mock_ref.message_id = 9999
    message.reference = mock_ref

    client = AsyncMock(spec=discord.Client)

    # Let's mock channel.send to return a confirmation message
    conf_msg = AsyncMock(spec=discord.Message)
    message.channel.send = AsyncMock(return_value=conf_msg)

    from plurality_module import handle_plurality_message
    res = await handle_plurality_message(message, client)
    assert res is True

    # User's triggering message should be deleted
    message.delete.assert_called_once()
    
    # Confirmation prompt should be sent with a view
    message.channel.send.assert_called_once()
    args, kwargs = message.channel.send.call_args
    assert "edit" in kwargs.get("content", "")
    view = kwargs.get("view")
    assert view is not None

    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user.id = 1010
    interaction.message = conf_msg
    interaction.response.send_modal = AsyncMock()

    client.get_channel.return_value = message.channel

    await view.edit_btn.callback(interaction)
    
    # Modal should be sent to interaction
    interaction.response.send_modal.assert_called_once()
    modal = interaction.response.send_modal.call_args[0][0]
    assert modal.content_input.default == "Original Content"

    modal.content_input._value = "Updated Content!"
    
    wh_mock = AsyncMock(spec=discord.Webhook)
    message.channel.webhooks.return_value = [wh_mock]
    
    modal_interaction = AsyncMock(spec=discord.Interaction)
    modal_interaction.response.send_message = AsyncMock()
    await modal.on_submit(modal_interaction)

    wh_mock.edit_message.assert_called_once_with(9999, content="Updated Content!")
    assert proxied_messages["9999"]["content"] == "Updated Content!"
    # Confirmation message deleted
    conf_msg.delete.assert_called_once()


@pytest.mark.asyncio
async def test_thread_none_parent_resolution():
    from plurality_module import get_webhook_for_channel, webhook_cache

    webhook_cache.clear()

    # Create a mock thread channel with parent = None
    thread_channel = AsyncMock(spec=discord.Thread)
    thread_channel.parent = None
    thread_channel.parent_id = 123
    
    parent_channel = AsyncMock(spec=discord.TextChannel)
    parent_channel.id = 123
    thread_channel.guild.get_channel.return_value = None
    thread_channel.guild.fetch_channel = AsyncMock(return_value=parent_channel)
    
    wh_mock = AsyncMock(spec=discord.Webhook)
    wh_mock.token = "token456"
    parent_channel.webhooks.return_value = [wh_mock]
    
    res = await get_webhook_for_channel(thread_channel)
    assert res == wh_mock
    thread_channel.guild.fetch_channel.assert_called_once_with(123)
