import os
import sys
import shutil
from unittest.mock import MagicMock

# Setup in-memory mock for discord module
class MockView:
    def __init__(self, *args, **kwargs):
        pass

mock_discord = MagicMock()
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.app_commands = MagicMock()
mock_discord.ButtonStyle = MagicMock()
mock_discord.Color = MagicMock()

sys.modules['discord'] = mock_discord
sys.modules['discord.app_commands'] = mock_discord.app_commands
sys.modules['discord.ui'] = mock_discord.ui

# Mock configuration module inside tests to return custom guild configs
mock_guild_configs = {}

def mock_get_guild_config(guild_id):
    # Returns default config or mocked configurations
    defaults = {
        "battle_enabled": True,
        "battle_default_hp": 500,
        "battle_damage_range": "0-100",
        "battle_timeout": 180
    }
    if guild_id in mock_guild_configs:
        defaults.update(mock_guild_configs[guild_id])
    return defaults

import configuration_module
configuration_module.get_guild_config = mock_get_guild_config

import test_db_helper
import db_service
DB_TEST_FILE = test_db_helper.DB_TEST_FILE
def init_test_db():
    test_db_helper.init_test_db()
init_test_db()

# Import battle_module after mocking
import battle_module

class MockMember:
    def __init__(self, user_id, display_name):
        self.id = user_id
        self.display_name = display_name
        self.mention = f"<@{user_id}>"

def test_stats_and_points():
    print("Testing stats persistence and point calculations...")
    init_test_db()
    
    try:
        # Load empty stats
        stats = battle_module.load_battle_stats()
        assert stats == {}, "Initial stats should be empty"
        
        # Test winner point scaling: rounds = 5 (fast victory)
        pts_fast = battle_module.add_battle_victory(111, 222, 5)
        # Expected points: max(10, 150 - 25) = 125
        assert pts_fast == 125, f"Expected 125 points for 5 rounds, got {pts_fast}"
        
        # Test winner point scaling: rounds = 30 (slow victory)
        pts_slow = battle_module.add_battle_victory(111, 222, 30)
        # Expected points: max(10, 150 - 150) = 10 (since 0 is < 10)
        assert pts_slow == 10, f"Expected 10 points for 30 rounds, got {pts_slow}"
        
        # Check overall stats
        updated_stats = battle_module.load_battle_stats()
        assert "111" in updated_stats, "Winner should be in stats"
        assert "222" in updated_stats, "Loser should be in stats"
        
        winner_data = updated_stats["111"]
        loser_data = updated_stats["222"]
        
        assert winner_data["points"] == 135, f"Winner points should be 125 + 10 = 135, got {winner_data['points']}"
        assert winner_data["wins"] == 2, f"Winner wins should be 2, got {winner_data['wins']}"
        assert winner_data["losses"] == 0, "Winner losses should be 0"
        assert winner_data["total_rounds_won"] == 35, f"Winner total rounds should be 35, got {winner_data['total_rounds_won']}"
        
        assert loser_data["points"] == 0, "Loser points should be 0"
        assert loser_data["wins"] == 0, "Loser wins should be 0"
        assert loser_data["losses"] == 2, f"Loser losses should be 2, got {loser_data['losses']}"
        
        print("Stats and points tests passed successfully!")
    finally:
        db_service.close_db_connection()

def test_customizable_guild_settings():
    print("Testing custom guild settings (default health, custom range, fixed damage)...")
    
    # Custom default HP
    mock_guild_configs[123] = {"battle_default_hp": 350}
    challenger = MockMember(1, "Alice")
    opponent = MockMember(2, "Bob")
    battle = battle_module.Battle(challenger, opponent, 456, 123)
    assert battle.challenger_hp == 350, f"Expected 350 HP, got {battle.challenger_hp}"
    assert battle.opponent_hp == 350, f"Expected 350 HP, got {battle.opponent_hp}"
    
    # Fixed damage value "15"
    mock_guild_configs[123] = {"battle_damage_range": "15"}
    for _ in range(50):
        dmg = battle_module.calculate_damage(123)
        assert dmg == 15, f"Expected exactly 15 damage, got {dmg}"
        
    # Custom damage range "10-50"
    mock_guild_configs[123] = {"battle_damage_range": "10-50"}
    all_dmgs = [battle_module.calculate_damage(123) for _ in range(1000)]
    for dmg in all_dmgs:
        assert 10 <= dmg <= 50, f"Damage {dmg} out of bounds for range 10-50"
        
    print("Customizable guild settings tests passed successfully!")

def test_funny_text_generators():
    print("Testing funny hit and victory text generators...")
    
    winner = MockMember(1, "Alice")
    loser = MockMember(2, "Bob")
    
    hit_msg = battle_module.get_random_hit_message(loser.mention, 42)
    assert loser.mention in hit_msg, "Loser mention should be in hit text"
    assert "42" in hit_msg, "Damage should be in hit text"
    
    victory_msg = battle_module.get_random_victory_message(winner.mention, loser.mention)
    assert winner.mention in victory_msg, "Winner mention should be in victory text"
    assert loser.mention in victory_msg, "Loser mention should be in victory text"
    
    print("Funny text generators tests passed successfully!")

if __name__ == "__main__":
    test_stats_and_points()
    print("-" * 40)
    test_customizable_guild_settings()
    print("-" * 40)
    test_funny_text_generators()
    print("-" * 40)
    print("ALL TESTS PASSED!")
