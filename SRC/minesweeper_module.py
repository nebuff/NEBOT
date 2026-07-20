import random
import discord
from discord import app_commands, ui
from configuration_module import get_guild_config

class MinesweeperBoard:
    def __init__(self, rows=4, cols=5, num_mines=4):
        self.rows = rows
        self.cols = cols
        self.num_mines = num_mines
        self.mines = set()
        self.revealed = set()
        self.flagged = set()
        self.adjacent_counts = {}
        self.mines_placed = False

    def generate_board(self, start_r, start_c):
        all_cells = [(r, c) for r in range(self.rows) for c in range(self.cols)]
        if (start_r, start_c) in all_cells:
            all_cells.remove((start_r, start_c))
        
        self.mines = set(random.sample(all_cells, min(self.num_mines, len(all_cells))))
        self.mines_placed = True
        self._calculate_adjacent_counts()

    def _calculate_adjacent_counts(self):
        self.adjacent_counts = {}
        for r in range(self.rows):
            for c in range(self.cols):
                if (r, c) in self.mines:
                    continue
                count = 0
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.rows and 0 <= nc < self.cols:
                            if (nr, nc) in self.mines:
                                count += 1
                self.adjacent_counts[(r, c)] = count

    def reveal(self, r, c) -> bool:
        if (r, c) in self.flagged or (r, c) in self.revealed:
            return False
            
        if not self.mines_placed:
            self.generate_board(r, c)
            
        if (r, c) in self.mines:
            return True
            
        self.revealed.add((r, c))
        
        if self.adjacent_counts.get((r, c), 0) == 0:
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.rows and 0 <= nc < self.cols:
                        if (nr, nc) not in self.revealed and (nr, nc) not in self.flagged:
                            self.reveal(nr, nc)
        return False

    def toggle_flag(self, r, c):
        if (r, c) in self.revealed:
            return
        if (r, c) in self.flagged:
            self.flagged.remove((r, c))
        else:
            self.flagged.add((r, c))

    def check_win(self) -> bool:
        total_cells = self.rows * self.cols
        non_mines = total_cells - len(self.mines)
        return len(self.revealed) == non_mines

class MinesweeperButton(ui.Button):
    def __init__(self, r: int, c: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=r)
        self.r = r
        self.c = c

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_click(interaction, self.r, self.c)

class MinesweeperView(ui.View):
    def __init__(self, user: discord.Member, num_mines: int = 4):
        super().__init__(timeout=180)
        self.user_id = user.id
        self.username = user.display_name
        self.num_mines = num_mines
        self.board = MinesweeperBoard(rows=4, cols=5, num_mines=num_mines)
        self.mode = "dig"
        self.game_over = False
        self.won = False
        self.exploded_cell = None
        self.message = None
        self.safe_clicks = 0
        
        self.buttons = {}
        for r in range(4):
            for c in range(5):
                btn = MinesweeperButton(r, c)
                self.add_item(btn)
                self.buttons[(r, c)] = btn
                
        self.update_view()

    def record_minesweeper_game(self, points: int, result: str, safe_clicks: int, correct_flags: int):
        from battle_module import load_battle_stats, save_battle_stats
        try:
            stats = load_battle_stats()
            u_str = str(self.user_id)
            if u_str not in stats:
                stats[u_str] = {
                    "points": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_rounds_won": 0,
                    "minesweeper_wins": 0,
                    "minesweeper_losses": 0,
                    "minesweeper_quits": 0,
                    "minesweeper_total_safe_clicks": 0,
                    "minesweeper_total_correct_flags": 0
                }
            
            user_stats = stats[u_str]
            for key in ["minesweeper_wins", "minesweeper_losses", "minesweeper_quits", "minesweeper_total_safe_clicks", "minesweeper_total_correct_flags"]:
                if key not in user_stats:
                    user_stats[key] = 0
                    
            user_stats["points"] += points
            if result == "win":
                user_stats["minesweeper_wins"] += 1
            elif result == "loss":
                user_stats["minesweeper_losses"] += 1
            elif result == "quit":
                user_stats["minesweeper_quits"] += 1
                
            user_stats["minesweeper_total_safe_clicks"] += safe_clicks
            user_stats["minesweeper_total_correct_flags"] += correct_flags
            
            save_battle_stats(stats)
        except Exception as e:
            print(f"Error recording minesweeper game: {e}")

    def update_view(self):
        for (r, c), btn in self.buttons.items():
            if (r, c) in self.board.revealed:
                btn.disabled = True
                if (r, c) in self.board.mines:
                    btn.style = discord.ButtonStyle.danger
                    btn.emoji = None
                    if (r, c) == self.exploded_cell:
                        btn.label = "X"
                    else:
                        btn.label = "M"
                else:
                    count = self.board.adjacent_counts.get((r, c), 0)
                    if count == 0:
                        btn.style = discord.ButtonStyle.success
                        btn.label = "\u200b"
                        btn.emoji = None
                    else:
                        btn.style = discord.ButtonStyle.primary
                        btn.label = str(count)
                        btn.emoji = None
            elif (r, c) in self.board.flagged:
                btn.style = discord.ButtonStyle.secondary
                btn.label = "F"
                btn.emoji = None
                btn.disabled = self.game_over or self.won
            else:
                btn.style = discord.ButtonStyle.secondary
                btn.label = "\u200b"
                btn.emoji = None
                btn.disabled = self.game_over or self.won

        if self.game_over or self.won:
            self.toggle_mode_btn.disabled = True
        else:
            self.toggle_mode_btn.disabled = False

        if self.mode == "dig":
            self.toggle_mode_btn.label = "Dig Mode"
            self.toggle_mode_btn.style = discord.ButtonStyle.success
        else:
            self.toggle_mode_btn.label = "Flag Mode"
            self.toggle_mode_btn.style = discord.ButtonStyle.danger

    def build_embed(self, status_msg: str = None) -> discord.Embed:
        if self.won:
            color = discord.Color.gold()
            title = "MINESWEEPER - VICTORY"
            desc = "Congratulations! You successfully flagged all mines and cleared all safe cells."
            if hasattr(self, "points_earned") and self.points_earned > 0:
                correct_flags = len(self.board.flagged.intersection(self.board.mines))
                desc += (
                    f"\n\n**Points Earned**: `+{self.points_earned}` points!\n"
                    f"• Victory Bonus: `+50`\n"
                    f"• Safe Moves ({self.safe_clicks}): `+{self.safe_clicks * 5}`\n"
                    f"• Correct Flags ({correct_flags}): `+{correct_flags * 10}`"
                )
        elif self.game_over:
            color = discord.Color.red()
            title = "MINESWEEPER - GAME OVER"
            desc = "Boom! You detonated a mine. Better luck next time!"
            if hasattr(self, "points_earned") and self.points_earned > 0:
                correct_flags = len(self.board.flagged.intersection(self.board.mines))
                desc += (
                    f"\n\n**Points Earned**: `+{self.points_earned}` points!\n"
                    f"• Safe Moves ({self.safe_clicks}): `+{self.safe_clicks * 5}`\n"
                    f"• Correct Flags ({correct_flags}): `+{correct_flags * 10}`"
                )
        else:
            color = discord.Color.blue()
            title = "MINESWEEPER"
            desc = (
                f"Mines: **{self.num_mines}** | Flagged: **{len(self.board.flagged)}**\n"
                f"Safe Moves: **{self.safe_clicks}**\n"
                f"Current mode: **{self.mode.upper()}** (toggle below)"
            )
        
        if status_msg:
            desc = f"{desc}\n\n*{status_msg}*"
            
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_footer(text=f"Game by {self.username}")
        return embed

    async def handle_click(self, interaction: discord.Interaction, r: int, c: int):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your game. Start your own with /minesweeper!", ephemeral=True)
            return
            
        if self.game_over or self.won:
            await interaction.response.send_message("The game is already over.", ephemeral=True)
            return
            
        if self.mode == "dig":
            if (r, c) in self.board.flagged:
                await interaction.response.send_message("Unflag this cell first to dig here.", ephemeral=True)
                return
            hit_mine = self.board.reveal(r, c)
            if hit_mine:
                self.game_over = True
                self.exploded_cell = (r, c)
                # Reveal all mines
                for mr, mc in self.board.mines:
                    self.board.revealed.add((mr, mc))
                # Award points for progress before dying
                correct_flags = len(self.board.flagged.intersection(self.board.mines))
                points_earned = (self.safe_clicks * 5) + (correct_flags * 10)
                self.points_earned = points_earned
                self.record_minesweeper_game(points_earned, "loss", self.safe_clicks, correct_flags)
            else:
                self.safe_clicks += 1
                if self.board.check_win():
                    self.won = True
                    self.board.flagged = self.board.mines.copy()
                    # Award points for victory!
                    correct_flags = len(self.board.flagged.intersection(self.board.mines))
                    points_earned = 50 + (self.safe_clicks * 5) + (correct_flags * 10)
                    self.points_earned = points_earned
                    self.record_minesweeper_game(points_earned, "win", self.safe_clicks, correct_flags)
        else:
            self.board.toggle_flag(r, c)
            
        self.update_view()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(label="Dig Mode", style=discord.ButtonStyle.success, row=4)
    async def toggle_mode_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your game.", ephemeral=True)
            return
        if self.mode == "dig":
            self.mode = "flag"
        else:
            self.mode = "dig"
        self.update_view()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(label="Restart", style=discord.ButtonStyle.secondary, row=4)
    async def restart_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your game.", ephemeral=True)
            return
        self.board = MinesweeperBoard(rows=4, cols=5, num_mines=self.num_mines)
        self.mode = "dig"
        self.game_over = False
        self.won = False
        self.exploded_cell = None
        self.safe_clicks = 0
        if hasattr(self, "points_earned"):
            delattr(self, "points_earned")
        self.update_view()
        await interaction.response.edit_message(embed=self.build_embed("Game restarted."), view=self)

    @ui.button(label="Quit", style=discord.ButtonStyle.secondary, row=4)
    async def quit_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your game.", ephemeral=True)
            return
        self.game_over = True
        if not self.board.mines_placed:
            self.board.generate_board(0, 0)
        # Reveal all mines
        for mr, mc in self.board.mines:
            self.board.revealed.add((mr, mc))
        # Award points for progress before quitting
        correct_flags = len(self.board.flagged.intersection(self.board.mines))
        points_earned = (self.safe_clicks * 5) + (correct_flags * 10)
        self.points_earned = points_earned
        self.record_minesweeper_game(points_earned, "quit", self.safe_clicks, correct_flags)
        self.update_view()
        self.stop()
        await interaction.response.edit_message(embed=self.build_embed("Game ended by player."), view=self)

    async def on_timeout(self):
        for btn in self.children:
            btn.disabled = True
        self.stop()
        if self.message:
            try:
                embed = self.build_embed("Game timed out due to inactivity.")
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

def setup_minesweeper_commands(tree: app_commands.CommandTree):
    @tree.command(name="minesweeper", description="Start an interactive game of Minesweeper!")
    @app_commands.describe(mines="Number of mines to place on the 4x5 board (1-8, defaults to configured server settings)")
    async def slash_minesweeper(interaction: discord.Interaction, mines: int = None):
        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("minesweeper_enabled", False):
            await interaction.response.send_message("The Minesweeper game is disabled on this server.", ephemeral=True)
            return
            
        actual_mines = mines if mines is not None else cfg.get("minesweeper_default_mines", 4)
        if not (1 <= actual_mines <= 8):
            await interaction.response.send_message("Please choose between 1 and 8 mines.", ephemeral=True)
            return
            
        view = MinesweeperView(interaction.user, num_mines=actual_mines)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()
