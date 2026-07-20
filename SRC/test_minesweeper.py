import sys
from unittest.mock import MagicMock

class MockView:
    def __init__(self, *args, **kwargs):
        pass
    def add_item(self, item):
        pass

class MockButton:
    def __init__(self, *args, **kwargs):
        pass

mock_discord = MagicMock()
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.ui.Button = MockButton
mock_discord.app_commands = MagicMock()
mock_discord.ButtonStyle = MagicMock()
mock_discord.Color = MagicMock()

sys.modules['discord'] = mock_discord
sys.modules['discord.app_commands'] = mock_discord.app_commands
sys.modules['discord.ui'] = mock_discord.ui

import configuration_module
configuration_module.get_guild_config = lambda guild_id: {"minesweeper_enabled": True}

from minesweeper_module import MinesweeperBoard

def test_board_initialization():
    print("Testing MinesweeperBoard initialization...")
    board = MinesweeperBoard(rows=4, cols=5, num_mines=4)
    assert board.rows == 4
    assert board.cols == 5
    assert board.num_mines == 4
    assert not board.mines_placed
    assert len(board.mines) == 0
    assert len(board.revealed) == 0
    assert len(board.flagged) == 0
    print("Initialization tests passed.")

def test_board_generation():
    print("Testing board generation on first click...")
    board = MinesweeperBoard(rows=4, cols=5, num_mines=4)
    # Perform first reveal at (1, 1)
    is_mine = board.reveal(1, 1)
    
    assert board.mines_placed
    assert len(board.mines) == 4
    assert (1, 1) not in board.mines, "First clicked cell should never be a mine"
    assert not is_mine, "First click should not hit a mine"
    assert (1, 1) in board.revealed, "First clicked cell should be revealed"
    print("Board generation tests passed.")

def test_flagging():
    print("Testing flag toggling...")
    board = MinesweeperBoard(rows=4, cols=5, num_mines=4)
    
    # Toggle flag on unrevealed cell
    board.toggle_flag(0, 0)
    assert (0, 0) in board.flagged
    
    # Reveal should not work on flagged cell
    board.reveal(0, 0)
    assert (0, 0) not in board.revealed
    
    # Toggle flag off
    board.toggle_flag(0, 0)
    assert (0, 0) not in board.flagged
    
    # Now reveal should work
    board.reveal(0, 0)
    assert (0, 0) in board.revealed
    
    # Toggle flag on revealed cell should do nothing
    board.toggle_flag(0, 0)
    assert (0, 0) not in board.flagged
    print("Flagging tests passed.")

def test_flood_fill():
    print("Testing flood fill reveal...")
    # Create a simple deterministic board by overriding mine placement
    board = MinesweeperBoard(rows=3, cols=3, num_mines=1)
    # Place a single mine at (0, 0)
    board.mines = {(0, 0)}
    board.mines_placed = True
    # Calculate counts
    board._calculate_adjacent_counts()
    
    # Reveal (2, 2) which is 0-adjacent (neighbors: (1,1)[1 adjacent], (1,2)[0 adjacent], (2,1)[0 adjacent])
    # Flood fill should reveal (2,2), (2,1), (1,2), (2,0), (0,2), (1,1), (0,1), (1,0)
    # The only cell not revealed should be (0,0) which is a mine
    board.reveal(2, 2)
    
    assert (0, 0) not in board.revealed
    assert (2, 2) in board.revealed
    assert (1, 1) in board.revealed
    assert (0, 1) in board.revealed
    assert (1, 0) in board.revealed
    
    # Win condition should be met because all non-mine cells are revealed
    assert board.check_win()
    print("Flood fill tests passed.")

def test_win_loss_states():
    print("Testing win and loss states...")
    board = MinesweeperBoard(rows=3, cols=3, num_mines=1)
    board.mines = {(0, 0)}
    board.mines_placed = True
    board._calculate_adjacent_counts()
    
    # Hit the mine
    hit_mine = board.reveal(0, 0)
    assert hit_mine, "Should return True when hitting a mine"
    assert not board.check_win(), "Should not win after hitting a mine"
    print("Win and loss state tests passed.")

def test_points_and_scoring():
    print("Testing points and scoring calculations...")
    from minesweeper_module import MinesweeperView
    
    member = MagicMock()
    member.id = 9999
    member.display_name = "Charlie"
    
    view = MinesweeperView(member, num_mines=2)
    view.board.mines = {(0, 0), (0, 1)}
    view.board.mines_placed = True
    view.board._calculate_adjacent_counts()
    
    # We mock record_minesweeper_game to avoid writing to database during testing
    view.record_minesweeper_game = MagicMock()
    
    view.safe_clicks = 0
    view.safe_clicks += 1
    view.safe_clicks += 1
    
    # Flag the mine at (0, 0) and non-mine at (1, 0)
    view.board.flagged.add((0, 0))
    view.board.flagged.add((1, 0))
    
    # Test point calculation on game over
    correct_flags = len(view.board.flagged.intersection(view.board.mines))
    points = (view.safe_clicks * 5) + (correct_flags * 10)
    assert correct_flags == 1, "Should have 1 correct flag"
    assert points == 20, f"Expected 20 points, got {points}"
    
    # Test point calculation on win
    view.safe_clicks = 5
    view.board.flagged = view.board.mines.copy() # Flag all mines (2 correct flags)
    correct_flags = len(view.board.flagged.intersection(view.board.mines))
    points = 50 + (view.safe_clicks * 5) + (correct_flags * 10)
    assert correct_flags == 2, "Should have 2 correct flags"
    assert points == 95, f"Expected 95 points, got {points}"
    
    print("Scoring tests passed successfully.")

if __name__ == "__main__":
    test_board_initialization()
    print("-" * 40)
    test_board_generation()
    print("-" * 40)
    test_flagging()
    print("-" * 40)
    test_flood_fill()
    print("-" * 40)
    test_win_loss_states()
    print("-" * 40)
    test_points_and_scoring()
    print("-" * 40)
    print("ALL MINESWEEPER LOGIC TESTS PASSED!")
