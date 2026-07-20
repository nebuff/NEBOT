import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

class MockRole:
    def __init__(self, id: int, name: str, position: int = 0):
        self.id = id
        self.name = name
        self.position = position
        self.mention = f"<@&{id}>"

class MockPermissions:
    def __init__(self, read_messages=True, view_channel=True):
        self.read_messages = read_messages
        self.view_channel = view_channel

class MockChannel:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
        self.mention = f"<#{id}>"
        self.send = AsyncMock()
        
    def permissions_for(self, member):
        if member.id == 900:
            return MockPermissions(read_messages=False, view_channel=False)
        return MockPermissions(read_messages=True, view_channel=True)

class MockMember:
    def __init__(self, id: int, name: str, bot=False, roles=None):
        self.id = id
        self.name = name
        self.bot = bot
        self.roles = roles or []
        self.add_roles = AsyncMock()
        self.remove_roles = AsyncMock()
        self.mention = f"<@{id}>"
        
    def get_role(self, role_id: int):
        for r in self.roles:
            if r.id == role_id:
                return r
        return None

class MockGuild:
    def __init__(self, id: int, members=None):
        self.id = id
        self.members = members or []
        self.chunked = True
        self.member_count = len(self.members)
        
        self.me = MockMember(12345, "BotSelf", bot=True)
        self.me.guild_permissions = MagicMock()
        self.me.guild_permissions.manage_roles = True
        self.me.top_role = MockRole(999, "BotHighestRole", position=10)
        
    async def chunk(self):
        pass

mock_discord = MagicMock()
mock_discord.Member = MockMember
mock_discord.Role = MockRole
mock_discord.Guild = MockGuild
mock_discord.TextChannel = MockChannel
mock_discord.Color = MagicMock()
sys.modules['discord'] = mock_discord
sys.modules['discord.ui'] = MagicMock()

def run_async(coro):
    return asyncio.run(coro)

import bulk_role_module

def test_bulk_role_all_filter():
    print("Testing bulk assign with filter_type='all'...")
    target_role = MockRole(100, "MemberRole")
    
    m1 = MockMember(1, "UserA", roles=[])
    m2 = MockMember(2, "UserB", roles=[target_role])
    guild = MockGuild(123, members=[m1, m2])
    
    notify_channel = MockChannel(10, "logs")
    started_by = MockMember(99, "Admin")
    
    run_async(bulk_role_module.run_bulk_role_task(
        guild=guild,
        target_role=target_role,
        operation="assign",
        filter_type="all",
        notify_channel=notify_channel,
        started_by=started_by
    ))
    
    m1.add_roles.assert_called_once_with(target_role, reason="Bulk Role assignment by <@99>")
    m2.add_roles.assert_not_called()
    assert bulk_role_module.active_bulk_role_operations[123]["applied"] == 1
    print("Filter 'all' test passed.")

def test_bulk_role_bots_humans_filters():
    print("Testing bulk assign with filter_type='bots' / 'humans'...")
    target_role = MockRole(100, "MemberRole")
    
    m_human = MockMember(1, "HumanUser", bot=False)
    m_bot = MockMember(2, "BotUser", bot=True)
    guild = MockGuild(123, members=[m_human, m_bot])
    
    run_async(bulk_role_module.run_bulk_role_task(
        guild=guild,
        target_role=target_role,
        operation="assign",
        filter_type="bots",
        notify_channel=None,
        started_by=None
    ))
    m_bot.add_roles.assert_called_once()
    m_human.add_roles.assert_not_called()
    
    m_bot.add_roles.reset_mock()
    m_human.add_roles.reset_mock()
    run_async(bulk_role_module.run_bulk_role_task(
        guild=guild,
        target_role=target_role,
        operation="assign",
        filter_type="humans",
        notify_channel=None,
        started_by=None
    ))
    m_human.add_roles.assert_called_once()
    m_bot.add_roles.assert_not_called()
    print("Filters 'bots' and 'humans' tests passed.")

def test_bulk_role_has_missing_filters():
    print("Testing bulk assign with filter_type='has_role' / 'missing_role'...")
    target_role = MockRole(100, "TargetRole")
    filter_role = MockRole(200, "VIP")
    
    m1 = MockMember(1, "UserA", roles=[filter_role])
    m2 = MockMember(2, "UserB", roles=[])
    guild = MockGuild(123, members=[m1, m2])
    
    run_async(bulk_role_module.run_bulk_role_task(
        guild=guild,
        target_role=target_role,
        operation="assign",
        filter_type="has_role",
        filter_role=filter_role
    ))
    m1.add_roles.assert_called_once()
    m2.add_roles.assert_not_called()
    
    m1.add_roles.reset_mock()
    m2.add_roles.reset_mock()
    run_async(bulk_role_module.run_bulk_role_task(
        guild=guild,
        target_role=target_role,
        operation="assign",
        filter_type="missing_role",
        filter_role=filter_role
    ))
    m2.add_roles.assert_called_once()
    m1.add_roles.assert_not_called()
    print("Filters 'has_role' and 'missing_role' tests passed.")

def test_bulk_role_channel_allowed_filter():
    print("Testing bulk assign with filter_type='channel_allowed'...")
    target_role = MockRole(100, "TargetRole")
    filter_channel = MockChannel(555, "restricted-chat")
    
    m1 = MockMember(1, "AllowedUser")
    m2 = MockMember(900, "RestrictedUser")
    guild = MockGuild(123, members=[m1, m2])
    
    run_async(bulk_role_module.run_bulk_role_task(
        guild=guild,
        target_role=target_role,
        operation="assign",
        filter_type="channel_allowed",
        filter_channel=filter_channel
    ))
    m1.add_roles.assert_called_once()
    m2.add_roles.assert_not_called()
    print("Filter 'channel_allowed' test passed.")

if __name__ == "__main__":
    test_bulk_role_all_filter()
    print("-" * 40)
    test_bulk_role_bots_humans_filters()
    print("-" * 40)
    test_bulk_role_has_missing_filters()
    print("-" * 40)
    test_bulk_role_channel_allowed_filter()
    print("-" * 40)
    print("ALL BULK ROLE TESTS PASSED!")
