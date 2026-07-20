import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

class MockRole:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

class MockMember:
    def __init__(self, id: int, name: str, roles=None):
        self.id = id
        self.name = name
        self.roles = roles or []
        
    def get_role(self, role_id: int):
        for r in self.roles:
            if r.id == role_id:
                return r
        return None
        
    async def add_roles(self, *roles, reason=None):
        for r in roles:
            if r not in self.roles:
                self.roles.append(r)
                
    async def remove_roles(self, *roles, reason=None):
        for r in roles:
            if r in self.roles:
                self.roles.remove(r)

class MockGuild:
    def __init__(self, id: int):
        self.id = id
        self.roles_dict = {}
        
    def get_role(self, role_id: int):
        return self.roles_dict.get(role_id)

mock_discord = MagicMock()
mock_discord.Member = MockMember
mock_discord.Role = MockRole
mock_discord.Guild = MockGuild

class MockClient:
    def __init__(self, *args, **kwargs):
        pass
    def event(self, func):
        return func

mock_discord.Client = MockClient
sys.modules['discord'] = mock_discord

class MockView:
    def __init__(self, *args, **kwargs):
        pass
    def add_item(self, item):
        pass

class MockButton:
    def __init__(self, *args, **kwargs):
        pass

mock_ui = MagicMock()
mock_ui.View = MockView
mock_ui.Button = MockButton
mock_discord.ui = mock_ui
sys.modules['discord.ui'] = mock_ui

def run_async(coro):
    return asyncio.run(coro)

# Now import the module
import self_assignable_roles_module

def test_module_disabled():
    print("Testing toggle with module disabled...")
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    
    mock_config = {
        "self_roles_enabled": False,
        "self_roles_groups": []
    }
    
    with patch("self_assignable_roles_module.get_guild_config", return_value=mock_config):
        run_async(self_assignable_roles_module.handle_self_role_toggle(interaction, 123, "GroupA", 100))
        interaction.response.send_message.assert_called_once_with(
            "Self-assignable roles are currently disabled on this server.", ephemeral=True
        )
    print("Module disabled test passed.")

def test_group_role_requirements():
    print("Testing group and role require_roles/ignore_roles...")
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    
    guild = MockGuild(123)
    r100 = MockRole(100, "Pronoun He")
    r_req = MockRole(200, "MemberRole")
    guild.roles_dict = {100: r100, 200: r_req}
    
    member = MockMember(999, "UserA", roles=[])
    interaction.guild = guild
    interaction.user = member
    interaction.message = MagicMock()
    interaction.message.flags.ephemeral = False
    
    mock_config = {
        "self_roles_enabled": True,
        "self_roles_groups": [
            {
                "name": "Pronouns",
                "mode": "none",
                "require_roles": [200],
                "ignore_roles": [],
                "roles": [
                    {"role_id": 100, "name": "He/Him", "allow_take_off": True, "require_roles": [], "ignore_roles": []}
                ]
            }
        ]
    }
    
    with patch("self_assignable_roles_module.get_guild_config", return_value=mock_config):
        run_async(self_assignable_roles_module.handle_self_role_toggle(interaction, 123, "Pronouns", 100))
        interaction.response.send_message.assert_called_with(
            "You must have at least one of the following roles to use this group: MemberRole", ephemeral=True
        )
        
    member.roles = [r_req]
    interaction.response.send_message.reset_mock()
    member.add_roles = AsyncMock()
    
    with patch("self_assignable_roles_module.get_guild_config", return_value=mock_config):
        run_async(self_assignable_roles_module.handle_self_role_toggle(interaction, 123, "Pronouns", 100))
        member.add_roles.assert_called_once_with(r100, reason="Self-assigned roles menu assignment")
        interaction.response.send_message.assert_called_with(
            "Granted role: **Pronoun He**", ephemeral=True
        )
    print("Requirements verification tests passed.")

def test_single_mode_logic():
    print("Testing single-mode auto_take_away and require_one flags...")
    guild = MockGuild(123)
    r1 = MockRole(101, "RoleA")
    r2 = MockRole(102, "RoleB")
    guild.roles_dict = {101: r1, 102: r2}
    
    member = MockMember(999, "UserA", roles=[r1])
    
    interaction = MagicMock()
    interaction.guild = guild
    interaction.user = member
    interaction.message = MagicMock()
    interaction.message.flags.ephemeral = False
    interaction.response.send_message = AsyncMock()
    
    mock_config = {
        "self_roles_enabled": True,
        "self_roles_groups": [
            {
                "name": "RolesGroup",
                "mode": "single",
                "auto_take_away": True,
                "require_one": True,
                "roles": [
                    {"role_id": 101, "name": "RoleA", "allow_take_off": True},
                    {"role_id": 102, "name": "RoleB", "allow_take_off": True}
                ]
            }
        ]
    }
    
    with patch("self_assignable_roles_module.get_guild_config", return_value=mock_config):
        run_async(self_assignable_roles_module.handle_self_role_toggle(interaction, 123, "RolesGroup", 101))
        interaction.response.send_message.assert_called_with(
            "You must keep at least one role from this group.", ephemeral=True
        )
        assert r1 in member.roles
        
    interaction.response.send_message.reset_mock()
    member.remove_roles = AsyncMock()
    member.add_roles = AsyncMock()
    
    with patch("self_assignable_roles_module.get_guild_config", return_value=mock_config):
        run_async(self_assignable_roles_module.handle_self_role_toggle(interaction, 123, "RolesGroup", 102))
        member.remove_roles.assert_called_once_with(r1, reason="Self-assigned roles menu replacement")
        member.add_roles.assert_called_once_with(r2, reason="Self-assigned roles menu assignment")
        interaction.response.send_message.assert_called_with(
            "Granted role: **RoleB** (and removed RoleA)", ephemeral=True
        )
    print("Single-mode logic tests passed.")

def test_multi_mode_logic():
    print("Testing multi-mode min_amount and max_amount bounds checks...")
    guild = MockGuild(123)
    r1 = MockRole(101, "RoleA")
    r2 = MockRole(102, "RoleB")
    r3 = MockRole(103, "RoleC")
    guild.roles_dict = {101: r1, 102: r2, 103: r3}
    
    member = MockMember(999, "UserA", roles=[r1, r2])
    
    interaction = MagicMock()
    interaction.guild = guild
    interaction.user = member
    interaction.message = MagicMock()
    interaction.message.flags.ephemeral = False
    interaction.response.send_message = AsyncMock()
    
    mock_config = {
        "self_roles_enabled": True,
        "self_roles_groups": [
            {
                "name": "RolesGroup",
                "mode": "multi",
                "min_amount": 1,
                "max_amount": 2,
                "roles": [
                    {"role_id": 101, "name": "RoleA", "allow_take_off": True},
                    {"role_id": 102, "name": "RoleB", "allow_take_off": True},
                    {"role_id": 103, "name": "RoleC", "allow_take_off": True}
                ]
            }
        ]
    }
    
    member.remove_roles = AsyncMock()
    member.add_roles = AsyncMock()
    with patch("self_assignable_roles_module.get_guild_config", return_value=mock_config):
        run_async(self_assignable_roles_module.handle_self_role_toggle(interaction, 123, "RolesGroup", 103))
        member.remove_roles.assert_called_once_with(r1, reason="Self-assigned roles menu replacement")
        member.add_roles.assert_called_once_with(r3, reason="Self-assigned roles menu assignment")
        interaction.response.send_message.assert_called_with(
            "Granted role: **RoleC** (and removed RoleA)", ephemeral=True
        )
        
    member.remove_roles = AsyncMock()
    interaction.response.send_message.reset_mock()
    with patch("self_assignable_roles_module.get_guild_config", return_value=mock_config):
        run_async(self_assignable_roles_module.handle_self_role_toggle(interaction, 123, "RolesGroup", 101))
        member.remove_roles.assert_called_once_with(r1, reason="Self-assigned roles menu removal")
        interaction.response.send_message.assert_called_with(
            "Removed role: **RoleA**", ephemeral=True
        )
        
    member.roles = [r2]
    interaction.response.send_message.reset_mock()
    with patch("self_assignable_roles_module.get_guild_config", return_value=mock_config):
        run_async(self_assignable_roles_module.handle_self_role_toggle(interaction, 123, "RolesGroup", 102))
        interaction.response.send_message.assert_called_with(
            "You must keep at least 1 roles from this group.", ephemeral=True
        )
    print("Multi-mode logic tests passed.")

if __name__ == "__main__":
    test_module_disabled()
    print("-" * 40)
    test_group_role_requirements()
    print("-" * 40)
    test_single_mode_logic()
    print("-" * 40)
    test_multi_mode_logic()
    print("-" * 40)
    print("ALL SELF ASSIGNABLE ROLES TESTS PASSED!")
