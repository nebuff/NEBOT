import sys
from unittest.mock import MagicMock, AsyncMock
import pytest

# Mock discord module dependencies for the test environment
mock_discord = MagicMock()
sys.modules['discord'] = mock_discord

import grok_module

# A helper to construct mock message object
def create_mock_message(content: str, is_bot: bool = False):
    message = MagicMock()
    message.author = MagicMock()
    message.author.bot = is_bot
    message.content = content
    message.channel = MagicMock()
    message.channel.send = AsyncMock()
    return message

def test_contains_emoji():
    assert grok_module.contains_emoji("") is True
    assert grok_module.contains_emoji("Hello  World") is True
    assert grok_module.contains_emoji("") is True
    # Discord custom emojis
    assert grok_module.contains_emoji("<:custom_emoji:1234567890>") is True
    assert grok_module.contains_emoji("<a:animated_emoji:0987654321>") is True
    # Plain text and punctuation
    assert grok_module.contains_emoji("Hello, World!") is False
    assert grok_module.contains_emoji("Is this true?") is False
    assert grok_module.contains_emoji("@grok 67") is False

@pytest.mark.asyncio
async def test_non_matching_messages():
    # Message without trigger
    msg = create_mock_message("Hello, how are you?")
    handled = await grok_module.handle_grok_message(msg)
    assert handled is False
    msg.channel.send.assert_not_called()

    # Message with bot author
    msg = create_mock_message("@grok is this true?", is_bot=True)
    handled = await grok_module.handle_grok_message(msg)
    assert handled is False
    msg.channel.send.assert_not_called()

    # Trigger but no word boundary (e.g. @grokking)
    msg = create_mock_message("@grokking is this true?")
    handled = await grok_module.handle_grok_message(msg)
    assert handled is False
    msg.channel.send.assert_not_called()

@pytest.mark.asyncio
async def test_general_query():
    msg = create_mock_message("@grok")
    handled = await grok_module.handle_grok_message(msg)
    assert handled is True
    msg.channel.send.assert_called_once()
    response = msg.channel.send.call_args[0][0]
    assert response in grok_module.REPLIES_GENERAL
    assert not grok_module.contains_emoji(response)

@pytest.mark.asyncio
async def test_is_this_true_query():
    # Various regex matching patterns
    patterns = [
        "@grok is this true?",
        "@grok IS THIS TRUE?",
        "@grok IS THIS TRUE IS THIS TRUE??????",
        "  @grok   is this true is this true  ",
        "@grok is this true. is this true! is this true?"
    ]
    for p in patterns:
        msg = create_mock_message(p)
        handled = await grok_module.handle_grok_message(msg)
        assert handled is True
        msg.channel.send.assert_called_once()
        response = msg.channel.send.call_args[0][0]
        assert response in grok_module.REPLIES_IS_THIS_TRUE
        assert not grok_module.contains_emoji(response)

@pytest.mark.asyncio
async def test_67_query():
    msg = create_mock_message("@grok 67")
    handled = await grok_module.handle_grok_message(msg)
    assert handled is True
    msg.channel.send.assert_called_once()
    response = msg.channel.send.call_args[0][0]
    assert response in grok_module.REPLIES_67
    assert not grok_module.contains_emoji(response)

@pytest.mark.asyncio
async def test_other_number_query():
    msg = create_mock_message("@grok 42")
    handled = await grok_module.handle_grok_message(msg)
    assert handled is True
    msg.channel.send.assert_called_once()
    response = msg.channel.send.call_args[0][0]
    assert response in grok_module.REPLIES_NUMBERS
    assert not grok_module.contains_emoji(response)

@pytest.mark.asyncio
async def test_other_questions():
    msg = create_mock_message("@grok why is the sky blue?")
    handled = await grok_module.handle_grok_message(msg)
    assert handled is True
    msg.channel.send.assert_called_once()
    response = msg.channel.send.call_args[0][0]
    assert response in grok_module.REPLIES_QUESTIONS
    assert not grok_module.contains_emoji(response)

@pytest.mark.asyncio
async def test_trigger_in_middle():
    # If @grok is in the middle/end, it should still process and extract query
    msg = create_mock_message("is this true? @grok")
    handled = await grok_module.handle_grok_message(msg)
    assert handled is True
    msg.channel.send.assert_called_once()
    response = msg.channel.send.call_args[0][0]
    assert response in grok_module.REPLIES_IS_THIS_TRUE
    assert not grok_module.contains_emoji(response)
