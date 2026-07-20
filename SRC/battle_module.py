import os
import json
import datetime
import random
import asyncio
import discord
from discord import app_commands, ui
from configuration_module import get_guild_config
from vc_wr_module import get_user_vc_wr_stats, format_duration

# State tracking dictionaries
active_battles = {}      # Channel_id -> Battle
players_in_battle = set() # Set of user_ids in active battles
pending_challenges = set() # Set of channel_ids with pending challenges

def load_battle_stats() -> dict:
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM battle_stats;")
        rows = cursor.fetchall()
        
        stats = {}
        for r in rows:
            u_id = r["user_id"]
            stats[u_id] = {
                "points": r["points"],
                "wins": r["wins"],
                "losses": r["losses"],
                "total_rounds_won": r["total_rounds_won"],
                "minesweeper_wins": r["minesweeper_wins"],
                "minesweeper_losses": r["minesweeper_losses"],
                "minesweeper_quits": r["minesweeper_quits"],
                "minesweeper_total_safe_clicks": r["minesweeper_total_safe_clicks"],
                "minesweeper_total_correct_flags": r["minesweeper_total_correct_flags"]
            }
        return stats
    except Exception as e:
        print(f"Error loading battle stats: {e}")
        return {}

def save_battle_stats(stats: dict):
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for u_id, s in stats.items():
            # Ensure user exists in users table (FK constraint)
            cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?);", (u_id,))
            
            cursor.execute("""
            INSERT OR REPLACE INTO battle_stats (
                user_id, points, wins, losses, total_rounds_won,
                minesweeper_wins, minesweeper_losses, minesweeper_quits,
                minesweeper_total_safe_clicks, minesweeper_total_correct_flags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                u_id,
                s.get("points", 0),
                s.get("wins", 0),
                s.get("losses", 0),
                s.get("total_rounds_won", 0),
                s.get("minesweeper_wins", 0),
                s.get("minesweeper_losses", 0),
                s.get("minesweeper_quits", 0),
                s.get("minesweeper_total_safe_clicks", 0),
                s.get("minesweeper_total_correct_flags", 0)
            ))
        conn.commit()
    except Exception as e:
        print(f"Error saving battle stats: {e}")

def add_battle_victory(winner_id: int, loser_id: int, rounds: int) -> int:
    w_str = str(winner_id)
    l_str = str(loser_id)
    
    # We can load, update, and save
    stats = load_battle_stats()
    
    if w_str not in stats:
        stats[w_str] = {"points": 0, "wins": 0, "losses": 0, "total_rounds_won": 0}
    if l_str not in stats:
        stats[l_str] = {"points": 0, "wins": 0, "losses": 0, "total_rounds_won": 0}
        
    points_earned = max(10, 150 - (rounds * 5))
    
    stats[w_str]["points"] += points_earned
    stats[w_str]["wins"] += 1
    stats[w_str]["total_rounds_won"] += rounds
    
    stats[l_str]["losses"] += 1
    
    save_battle_stats(stats)
    return points_earned

def get_random_hit_message(user_mention: str, damage: int) -> str:
    templates = [
        f"{user_mention} GOT HIT! -{damage}HP",
        f"Oh no! {user_mention} was not powerful enough, taking -{damage}HP!",
        f"Critical facepalm! {user_mention} takes -{damage}HP from sheer embarrassment!",
        f"{user_mention} tripped on a virtual cable and lost -{damage}HP!",
        f"A wild compiler error appeared! {user_mention} suffered -{damage}HP!",
        f"{user_mention} got hit by a stray semicolon! -{damage}HP!",
        f"{user_mention} forgot to save their files and lost -{damage}HP to rage!",
        f"A flying keyboard struck {user_mention} for -{damage}HP!",
        f"{user_mention} was run over by a steam locomotive! -{damage}HP!",
        f"{user_mention} stepped on a lego! -{damage}HP! Absolute agony!",
        f"{user_mention} tried to delete root! -{damage}HP from the explosion!",
        f"{user_mention} was hit by a segmentation fault! -{damage}HP!",
    ]
    return random.choice(templates)

def get_random_victory_message(winner_mention: str, loser_mention: str) -> str:
    templates = [
        f"{winner_mention}'s PC was too powerful and exploded {loser_mention}'s PC, Oh no!",
        f"{loser_mention} ran out of memory and was terminated by {winner_mention}'s OOM Killer!",
        f"{winner_mention} force pushed to main, overwriting {loser_mention}'s entire existence!",
        f"{winner_mention} deleted {loser_mention}'s system32 directory. RIP!",
        f"{winner_mention} division-by-zeroed {loser_mention} into another dimension!",
        f"{loser_mention} tried to copy {winner_mention}'s homework but got caught and expelled from the server!",
        f"{winner_mention} cast a level 9 sudo command on {loser_mention}!",
        f"{loser_mention} was deprecated. {winner_mention} is now the LTS release!",
        f"{winner_mention} compiled successfully while {loser_mention} had 404 compilation errors!",
        f"{loser_mention} had their swap file filled with garbage by {winner_mention}!",
    ]
    return random.choice(templates)

def calculate_damage(guild_id: int | None) -> int:
    cfg = get_guild_config(guild_id)
    dmg_range = cfg.get("battle_damage_range", "0-100")
    
    if "-" in dmg_range:
        parts = dmg_range.split("-")
        try:
            a = int(parts[0])
            b = int(parts[1])
            if a >= b:
                return a
            # Standard triangular distribution: Mode is at 20% of range
            mode = a + (b - a) * 0.2
            return int(random.triangular(a, b, mode))
        except Exception:
            return int(random.triangular(0, 100, 20))
    else:
        try:
            return int(dmg_range)
        except Exception:
            return 20

class Battle:
    def __init__(self, challenger: discord.Member, opponent: discord.Member, channel_id: int, guild_id: int | None):
        self.challenger = challenger
        self.opponent = opponent
        self.channel_id = channel_id
        self.guild_id = guild_id
        
        cfg = get_guild_config(guild_id)
        default_hp = cfg.get("battle_default_hp", 500)
        self.challenger_hp = default_hp
        self.opponent_hp = default_hp
        
        self.current_turn = challenger
        self.turns_taken = 0
        self.last_activity = datetime.datetime.utcnow()
        self.ended = False

    @property
    def opponent_of_current(self) -> discord.Member:
        if self.current_turn.id == self.challenger.id:
            return self.opponent
        return self.challenger

class BattleChallengeView(ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, channel_id: int):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.channel_id = channel_id
        self.accepted = False
        self.message = None

    @ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("You cannot accept this challenge.", ephemeral=True)
            return
        
        self.accepted = True
        self.stop()
        
        pending_challenges.discard(self.channel_id)
        
        guild_id = interaction.guild_id
        battle = Battle(self.challenger, self.opponent, self.channel_id, guild_id)
        active_battles[self.channel_id] = battle
        players_in_battle.add(self.challenger.id)
        players_in_battle.add(self.opponent.id)
        
        embed = discord.Embed(
            title="BATTLE STARTED",
            description=(
                f"The combat begins!\n\n"
                f"Players:\n"
                f"{self.challenger.mention}: {battle.challenger_hp} HP\n"
                f"{self.opponent.mention}: {battle.opponent_hp} HP\n\n"
                f"It is {self.challenger.mention}'s turn! Type your attack message in this channel."
            ),
            color=discord.Color.red()
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("You cannot decline this challenge.", ephemeral=True)
            return
        
        self.stop()
        pending_challenges.discard(self.channel_id)
        await interaction.response.edit_message(content="Challenge declined.", embed=None, view=None)

    async def on_timeout(self):
        if not self.accepted:
            pending_challenges.discard(self.channel_id)
            if self.message:
                try:
                    await self.message.edit(content="Challenge timed out.", embed=None, view=None)
                except Exception:
                    pass

async def handle_battle_message(message: discord.Message) -> bool:
    if message.author.bot:
        return False

    channel_id = message.channel.id
    if channel_id not in active_battles:
        return False

    battle = active_battles[channel_id]
    
    if message.content.startswith("/"):
        return False

    if message.author.id != battle.current_turn.id:
        return False

    battle.last_activity = datetime.datetime.utcnow()
    battle.turns_taken += 1
    
    # Calculate damage using configured parameters
    damage = calculate_damage(battle.guild_id)
    
    target = battle.opponent_of_current
    if target.id == battle.opponent.id:
        battle.opponent_hp = max(0, battle.opponent_hp - damage)
        target_hp = battle.opponent_hp
    else:
        battle.challenger_hp = max(0, battle.challenger_hp - damage)
        target_hp = battle.challenger_hp

    # Format hit result message
    hit_msg = get_random_hit_message(target.mention, damage)

    # Calculate current round count
    rounds = (battle.turns_taken // 2) + 1
    if target_hp <= 0:
        battle.ended = True
        
        # Send final round embed first showing target reduced to 0 HP
        embed_round = discord.Embed(
            title=f"ROUND {rounds}",
            description=(
                f"{message.author.mention} says: \"{message.content}\"\n\n"
                f"**{hit_msg}**\n\n"
                f"Status:\n"
                f"{battle.challenger.mention}: {battle.challenger_hp} HP\n"
                f"{battle.opponent.mention}: {battle.opponent_hp} HP\n\n"
                f"Oh no! {target.mention} was not powerful enough"
            ),
            color=discord.Color.red()
        )
        await message.channel.send(embed=embed_round)
        
        await asyncio.sleep(1.5)
        
        winner = battle.current_turn
        loser = target
        
        final_rounds = (battle.turns_taken + 1) // 2
        points_awarded = add_battle_victory(winner.id, loser.id, final_rounds)
        
        # Cleanup state
        active_battles.pop(channel_id, None)
        players_in_battle.discard(battle.challenger.id)
        players_in_battle.discard(battle.opponent.id)
        
        funny_victory_msg = get_random_victory_message(winner.mention, loser.mention)
        
        embed_over = discord.Embed(
            title="BATTLE OVER",
            description=(
                f"{winner.mention} wins!\n\n"
                f"{funny_victory_msg}\n\n"
                f"It took {final_rounds} rounds of fighting to defeat {loser.mention}!\n\n"
                f"+{points_awarded} points have been awarded to {winner.mention}!"
            ),
            color=discord.Color.gold()
        )
        embed_over.set_footer(text=f"Winner HP: {battle.challenger_hp if winner.id == battle.challenger.id else battle.opponent_hp} | Loser HP: 0")
        await message.channel.send(embed=embed_over)
        return True

    battle.current_turn = target

    embed = discord.Embed(
        title=f"ROUND {rounds}",
        description=(
            f"{message.author.mention} says: \"{message.content}\"\n\n"
            f"**{hit_msg}**\n\n"
            f"Status:\n"
            f"{battle.challenger.mention}: {battle.challenger_hp} HP\n"
            f"{battle.opponent.mention}: {battle.opponent_hp} HP\n\n"
            f"It is now {battle.current_turn.mention}'s turn! Type your attack message in this channel."
        ),
        color=discord.Color.red()
    )
    await message.channel.send(embed=embed)
    return True

async def battle_watcher(client: discord.Client):
    await client.wait_until_ready()
    while not client.is_closed():
        now = datetime.datetime.utcnow()
        timed_out = []
        for cid, battle in list(active_battles.items()):
            cfg = get_guild_config(battle.guild_id)
            timeout_limit = cfg.get("battle_timeout", 180)
            if (now - battle.last_activity).total_seconds() > timeout_limit:
                timed_out.append((cid, battle))
                
        for cid, battle in timed_out:
            active_battles.pop(cid, None)
            players_in_battle.discard(battle.challenger.id)
            players_in_battle.discard(battle.opponent.id)
            channel = client.get_channel(cid)
            if channel:
                try:
                    await channel.send(
                        f"The battle between {battle.challenger.mention} and {battle.opponent.mention} "
                        f"has timed out due to inactivity."
                    )
                except Exception:
                    pass
        await asyncio.sleep(15)


async def build_user_stats_embeds(guild_id: int, target_user: discord.Member | discord.User):
    stats = load_battle_stats()
    user_id_str = str(target_user.id)

    if user_id_str not in stats:
        user_stats = {"points": 0, "wins": 0, "losses": 0, "total_rounds_won": 0}
    else:
        user_stats = stats[user_id_str]

    points = user_stats.get("points", 0)
    wins = user_stats.get("wins", 0)
    losses = user_stats.get("losses", 0)
    total_rounds_won = user_stats.get("total_rounds_won", 0)
    games_played = wins + losses

    win_rate = (wins / games_played * 100) if games_played > 0 else 0.0
    avg_rounds = (total_rounds_won / wins) if wins > 0 else 0.0

    ms_wins = user_stats.get("minesweeper_wins", 0)
    ms_losses = user_stats.get("minesweeper_losses", 0)
    ms_quits = user_stats.get("minesweeper_quits", 0)
    ms_clicks = user_stats.get("minesweeper_total_safe_clicks", 0)
    ms_flags = user_stats.get("minesweeper_total_correct_flags", 0)

    ms_total_games = ms_wins + ms_losses + ms_quits
    ms_win_rate = (ms_wins / ms_total_games * 100) if ms_total_games > 0 else 0.0

    # General Stats Embed
    embed_general = discord.Embed(
        title=f"General Statistics for {target_user.display_name}",
        color=discord.Color.blue()
    )
    embed_general.description = f"Total Account Points: {points}"

    # Battle Stats Embed
    embed_battle = discord.Embed(
        title="Battle Statistics",
        color=discord.Color.red()
    )
    embed_battle.add_field(name="Wins", value=str(wins), inline=True)
    embed_battle.add_field(name="Losses", value=str(losses), inline=True)
    embed_battle.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)
    embed_battle.add_field(name="Total Battles", value=str(games_played), inline=True)
    embed_battle.add_field(name="Avg Rounds per Win", value=f"{avg_rounds:.1f}" if wins > 0 else "N/A", inline=True)

    # Minesweeper Stats Embed
    embed_ms = discord.Embed(
        title="Minesweeper Statistics",
        color=discord.Color.green()
    )
    embed_ms.add_field(name="Wins", value=str(ms_wins), inline=True)
    embed_ms.add_field(name="Losses", value=str(ms_losses), inline=True)
    embed_ms.add_field(name="Quits", value=str(ms_quits), inline=True)
    embed_ms.add_field(name="Win Rate", value=f"{ms_win_rate:.1f}%", inline=True)
    embed_ms.add_field(name="Safe Clicks (Total)", value=str(ms_clicks), inline=True)
    embed_ms.add_field(name="Correct Flags (Total)", value=str(ms_flags), inline=True)

    # VC WR Stats Embed
    vc_stats = await get_user_vc_wr_stats(guild_id, target_user.id)
    embed_vc = discord.Embed(
        title="Voice Channel World Records",
        color=discord.Color.gold()
    )

    rank_str = str(vc_stats["rank"]) if vc_stats["rank"] is not None else "Unranked"
    record_str = format_duration(vc_stats["record"])

    embed_vc.add_field(name="Leaderboard Rank", value=rank_str, inline=True)
    embed_vc.add_field(name="All-Time Longest Session", value=record_str, inline=True)
    if vc_stats["current_session"] > 0:
        embed_vc.add_field(name="Current Session", value=format_duration(vc_stats["current_session"]), inline=False)

    return [embed_general, embed_battle, embed_ms, embed_vc]

def setup_battle_commands(tree: app_commands.CommandTree):
    @tree.command(name="battle", description="Challenge another user to a BATTLE!")
    async def slash_battle(interaction: discord.Interaction, opponent: discord.Member):
        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("battle_enabled", False):
            await interaction.response.send_message("The battle system is disabled on this server.", ephemeral=True)
            return

        if opponent.id == interaction.user.id:
            await interaction.response.send_message("You cannot battle yourself.", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("hey silly you cant battle a bot", ephemeral=True)
            return
        
        if interaction.channel_id in active_battles:
            await interaction.response.send_message("There is already an active battle in this channel.", ephemeral=True)
            return
            
        if interaction.channel_id in pending_challenges:
            await interaction.response.send_message("There is already a pending challenge in this channel.", ephemeral=True)
            return

        if interaction.user.id in players_in_battle:
            await interaction.response.send_message("You are already in an active battle.", ephemeral=True)
            return
        if opponent.id in players_in_battle:
            await interaction.response.send_message(f"{opponent.display_name} is already in an active battle.", ephemeral=True)
            return

        # Register pending challenge
        pending_challenges.add(interaction.channel_id)
        
        battle_hp = cfg.get("battle_default_hp", 500)
        
        view = BattleChallengeView(interaction.user, opponent, interaction.channel_id)
        embed = discord.Embed(
            title="BATTLE CHALLENGE",
            description=(
                f"{interaction.user.mention} has challenged {opponent.mention} to a BATTLE!! "
                f"Both players start with {battle_hp} HP.\n\n"
                f"{opponent.mention}, click Accept to start the battle."
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(content=opponent.mention, embed=embed, view=view)
        view.message = await interaction.original_response()

    @tree.command(name="stats", description="Check your general bot statistics and points")
    async def slash_stats(interaction: discord.Interaction, user: discord.Member = None):
        target_user = user or interaction.user
        if target_user.bot:
            await interaction.response.send_message("Bots do not have stats.", ephemeral=True)
            return
            
        embeds = await build_user_stats_embeds(interaction.guild_id, target_user)
        await interaction.response.send_message(embeds=embeds, ephemeral=True)
