import os
import discord
from discord import app_commands, ui
import wavelink
import asyncio
import aiohttp
import urllib.parse
import re
import json
from configuration_module import get_guild_config
from music_permissions_handler import check_command_permissions, check_button_permissions

LAVALINK_HOST = os.getenv("LAVALINK_HOST", "127.0.0.1")
LAVALINK_PORT = os.getenv("LAVALINK_PORT", "2333")
# LAVALINK_PASSWORD must be explicitly set to avoid using default passwords
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Default playback volume (0-100). Intentionally low so users can raise it
# Themselves via the Volume Up button or bot settings
DEFAULT_VOLUME = 5

class NebotPlayer(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text_channel = None
        self.play_window_message = None
        self.autoplay_enabled = False
        self.loop_mode = False

def prepare_query(query: str) -> str:
    query = query.strip()
    if "open.spotify.com/" in query or "spotify:" in query:
        # Spotify URL pattern, LavaSrc resolves natively
        return query
    if query.startswith(("http://", "https://")):
        # Direct URL string
        return query
    # Plain text search
    return f"scsearch:{query}"

async def fetch_spotify_tracks(url: str) -> dict | None:
    parsed_id = None
    parsed_type = None
    
    if "open.spotify.com/" in url:
        parts = urllib.parse.urlparse(url)
        path_parts = [p for p in parts.path.split('/') if p]
        if len(path_parts) >= 2:
            parsed_type = path_parts[-2] # e.g. "playlist" or "album"
            parsed_id = path_parts[-1]
    elif url.startswith("spotify:"):
        parts = url.split(":")
        if len(parts) >= 3:
            parsed_type = parts[1]
            parsed_id = parts[2]
            
    if not parsed_id or parsed_type not in ("playlist", "album"):
        return None
        
    parsed_id = parsed_id.split('?')[0]
    
    # Try Spotify Web API if credentials are set
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if client_id and client_secret:
        try:
            auth_url = "https://accounts.spotify.com/api/token"
            import base64
            auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    auth_url,
                    data={"grant_type": "client_credentials"},
                    headers={"Authorization": f"Basic {auth_header}"}
                ) as resp:
                    if resp.status == 200:
                        token_data = await resp.json()
                        access_token = token_data.get("access_token")
                        
                        if parsed_type == "playlist":
                            tracks_url = f"https://api.spotify.com/v1/playlists/{parsed_id}"
                        else:
                            tracks_url = f"https://api.spotify.com/v1/albums/{parsed_id}"
                            
                        async with session.get(
                            tracks_url,
                            headers={"Authorization": f"Bearer {access_token}"}
                        ) as get_resp:
                            if get_resp.status == 200:
                                api_data = await get_resp.json()
                                name = api_data.get("name")
                                tracks = []
                                
                                if parsed_type == "playlist":
                                    items = api_data.get("tracks", {}).get("items", [])
                                    for item in items:
                                        track_info = item.get("track")
                                        if track_info:
                                            title = track_info.get("name")
                                            artists = [a.get("name") for a in track_info.get("artists", [])]
                                            artist = ", ".join(artists) if artists else "Unknown Artist"
                                            tracks.append({"title": title, "artist": artist})
                                else:
                                    items = api_data.get("tracks", {}).get("items", [])
                                    for item in items:
                                        title = item.get("name")
                                        artists = [a.get("name") for a in item.get("artists", [])]
                                        artist = ", ".join(artists) if artists else "Unknown Artist"
                                        tracks.append({"title": title, "artist": artist})
                                        
                                return {"name": name, "tracks": tracks}
        except Exception as e:
            print(f"[Music] Spotify API resolution failed, falling back to scraping: {e}")
            
    # Scrape the embed page as fallback
    try:
        embed_url = f"https://open.spotify.com/embed/{parsed_type}/{parsed_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(embed_url, headers=headers) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    for match in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
                        content = match.group(1).strip()
                        if content.startswith('{"props":'):
                            data = json.loads(content)
                            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                            name = entity.get("name") or entity.get("title")
                            track_list = entity.get("trackList", [])
                            
                            tracks = []
                            for track in track_list:
                                title = track.get("title") or track.get("name")
                                artist = track.get("subtitle", "Unknown Artist").replace('\xa0', ' ')
                                tracks.append({"title": title, "artist": artist})
                                
                            if name and tracks:
                                return {"name": name, "tracks": tracks}
    except Exception as e:
        print(f"[Music] Spotify scraping failed: {e}")
        
    return None

async def resolve_spotify_track(title: str, artist: str) -> wavelink.Playable | None:
    query = f"{title} {artist}".strip()
    for prefix in ("scsearch:", "ytsearch:"):
        try:
            tracks = await wavelink.Playable.search(f"{prefix}{query}")
            if tracks:
                return tracks[0]
        except Exception:
            continue
    return None


async def build_play_window_embed(player: NebotPlayer) -> discord.Embed:
    track = player.current
    if not track:
        return discord.Embed(
            title="No Track Playing",
            description="Use `/play` to stream music.",
            color=discord.Color.light_grey()
        )
        
    embed = discord.Embed(color=discord.Color.teal())
    embed.set_author(name="Now playing")
    
    if getattr(track, "uri", None):
        embed.title = track.title
        embed.url = track.uri
    else:
        embed.title = track.title

    added_by_id = getattr(track, "added_by", None)
    added_by_str = f"<@{added_by_id}>" if added_by_id else "Unknown"
    embed.add_field(name="Added by", value=added_by_str, inline=True)
    
    vc_str = f"<#{player.channel.id}>"
    embed.add_field(name="Voice Channel", value=vc_str, inline=True)
    
    artwork = getattr(track, "artwork", None)
    if not artwork and hasattr(track, "thumbnail"):
        artwork = track.thumbnail
    if artwork:
        embed.set_thumbnail(url=artwork)
        
    loop_str = "On" if player.loop_mode else "Off"
    status_bar = f"Queue Size: {len(player.queue)} · Volume: {player.volume}% · Loop: {loop_str}"
    embed.add_field(name="\u200b", value=status_bar, inline=False)
    
    if not player.queue.is_empty:
        queue_list = []
        for i, q_track in enumerate(list(player.queue)[:5], 1):
            q_added_by = getattr(q_track, "added_by", None)
            q_added_str = f" (added by <@{q_added_by}>)" if q_added_by else ""
            if getattr(q_track, "uri", None):
                queue_list.append(f"`{i}.` **[{q_track.title}]({q_track.uri})**{q_added_str}")
            else:
                queue_list.append(f"`{i}.` **{q_track.title}**{q_added_str}")
                
        queue_preview = "\n".join(queue_list)
        if len(player.queue) > 5:
            queue_preview += f"\n*...and {len(player.queue) - 5} more tracks.*"
        embed.add_field(name="Up Next", value=queue_preview, inline=False)
        
    return embed

async def update_play_window(player: NebotPlayer):
    if not player.play_window_message or not player.text_channel:
        return
    try:
        embed = await build_play_window_embed(player)
        view = MusicPlayerView(player)
        await player.play_window_message.edit(embed=embed, view=view)
    except Exception as e:
        print(f"[Music] Error updating play window: {e}")

class MusicPlayerView(discord.ui.View):
    def __init__(self, player: NebotPlayer):
        super().__init__(timeout=None)
        self.player = player
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await check_button_permissions(interaction, self.player):
            return False
        user_voice = getattr(interaction.user, 'voice', None)
        if not user_voice or not user_voice.channel or user_voice.channel.id != self.player.channel.id:
            await interaction.response.send_message("You must be in the voice channel to manage the stream.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.pause_btn.label = "Resume" if self.player.paused else "Pause"
        
        if self.player.autoplay_enabled:
            self.autoplay_btn.style = discord.ButtonStyle.success
            self.autoplay_btn.label = "AutoPlay: On"
        else:
            self.autoplay_btn.style = discord.ButtonStyle.secondary
            self.autoplay_btn.label = "AutoPlay: Off"

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary, custom_id="music_pause")
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.pause(not self.player.paused)
        self.update_buttons()
        embed = await build_play_window_embed(self.player)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="music_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.skip()
        await interaction.response.send_message("Skipped track.", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.secondary, custom_id="music_stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.queue.clear()
        await self.player.disconnect()
        embed = discord.Embed(title="Playback Stopped", description="The stream was terminated and the queue cleared.", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="AutoPlay", style=discord.ButtonStyle.secondary, custom_id="music_autoplay")
    async def autoplay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.autoplay_enabled = not self.player.autoplay_enabled
        if hasattr(wavelink, "AutoPlayMode"):
            self.player.autoplay = wavelink.AutoPlayMode.enabled if self.player.autoplay_enabled else wavelink.AutoPlayMode.disabled
        elif hasattr(self.player, "autoplay"):
            self.player.autoplay = self.player.autoplay_enabled
        self.update_buttons()
        embed = await build_play_window_embed(self.player)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Dashboard", style=discord.ButtonStyle.secondary, custom_id="music_dashboard")
    async def dashboard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MusicDashboardView(self.player)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

class MusicDashboardView(discord.ui.View):
    def __init__(self, player: NebotPlayer):
        super().__init__(timeout=None)
        self.player = player

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await check_button_permissions(interaction, self.player):
            return False
        user_voice = getattr(interaction.user, 'voice', None)
        if not user_voice or not user_voice.channel or user_voice.channel.id != self.player.channel.id:
            await interaction.response.send_message("You must be in the voice channel to manage the stream.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Nebot Music Module Dashboard",
            description="Active streaming node status and metrics for this server.",
            color=discord.Color.blurple()
        )
        current_track = self.player.current
        track_str = f"[{current_track.title}]({current_track.uri})" if current_track and getattr(current_track, "uri", None) else (current_track.title if current_track else "None")
        loop_str = "Enabled" if self.player.loop_mode else "Disabled"
        autoplay_str = "Enabled" if self.player.autoplay_enabled else "Disabled"
        
        embed.add_field(name="Now Playing", value=track_str, inline=False)
        embed.add_field(name="Queue Size", value=f"{len(self.player.queue)} tracks", inline=True)
        embed.add_field(name="Volume", value=f"{self.player.volume}%", inline=True)
        embed.add_field(name="Loop State", value=loop_str, inline=True)
        embed.add_field(name="AutoPlay State", value=autoplay_str, inline=True)
        embed.add_field(name="Node Status", value="Connected & Online", inline=True)
        
        artwork = None
        if current_track:
            artwork = getattr(current_track, "artwork", None)
            if not artwork and hasattr(current_track, "thumbnail"):
                artwork = current_track.thumbnail
        if artwork:
            embed.set_thumbnail(url=artwork)
        
        return embed

    @discord.ui.button(label="Back to Player", style=discord.ButtonStyle.secondary, custom_id="dash_back")
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MusicPlayerView(self.player)
        embed = await build_play_window_embed(self.player)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Toggle Loop", style=discord.ButtonStyle.secondary, custom_id="dash_loop")
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop_mode = not self.player.loop_mode
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Volume Up", style=discord.ButtonStyle.secondary, custom_id="dash_vol_up")
    async def vol_up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vol = min(self.player.volume + 10, 100)
        await self.player.set_volume(vol)
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Volume Down", style=discord.ButtonStyle.secondary, custom_id="dash_vol_down")
    async def vol_down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vol = max(self.player.volume - 10, 0)
        await self.player.set_volume(vol)
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

async def process_play_request(interaction: discord.Interaction, query: str, member: discord.Member, player: NebotPlayer):
    is_spotify_playlist_or_album = False
    if ("open.spotify.com/playlist/" in query or 
        "open.spotify.com/album/" in query or 
        query.startswith("spotify:playlist:") or 
        query.startswith("spotify:album:")):
        is_spotify_playlist_or_album = True
        
    if is_spotify_playlist_or_album:
        # Try our custom Python Spotify resolver
        spotify_data = await fetch_spotify_tracks(query)
        if spotify_data and spotify_data.get("tracks"):
            playlist_name = spotify_data["name"]
            tracks = spotify_data["tracks"]
            
            await interaction.followup.send(
                f"Found Spotify playlist/album **{playlist_name}** ({len(tracks)} tracks). Resolving tracks and queueing...",
                ephemeral=True
            )
            
            sem = asyncio.Semaphore(5)
            
            async def resolve_with_sem(index, t_title, t_artist):
                async with sem:
                    try:
                        track = await resolve_spotify_track(t_title, t_artist)
                        return index, track
                    except Exception:
                        return index, None
                        
            tasks = [resolve_with_sem(i, t["title"], t["artist"]) for i, t in enumerate(tracks)]
            results = await asyncio.gather(*tasks)
            results.sort(key=lambda x: x[0])
            
            resolved_tracks = [r[1] for r in results if r[1] is not None]
            
            if not resolved_tracks:
                await interaction.followup.send(
                    "Failed to resolve any tracks from the Spotify playlist/album.",
                    ephemeral=True
                )
                return
                
            first = True
            enqueued_count = 0
            for t in resolved_tracks:
                t.added_by = member.id
                if first and not player.playing:
                    await player.play(t)
                    first = False
                else:
                    await player.queue.put_wait(t)
                enqueued_count += 1
                
            await interaction.followup.send(
                f"Enqueued **{playlist_name}** ({enqueued_count} tracks resolved).",
                ephemeral=True
            )
            await update_play_window(player)
            return

    # Standard Wavelink search path
    prepared_query = prepare_query(query)
    try:
        tracks = await wavelink.Playable.search(prepared_query)
    except Exception as e:
        if prepared_query.startswith("scsearch:"):
            try:
                tracks = await wavelink.Playable.search(f"ytsearch:{query}")
            except Exception:
                tracks = []
        else:
            await interaction.followup.send(f"Search failed: {e}", ephemeral=True)
            return
            
    if not tracks:
        await interaction.followup.send("No tracks found for your query.", ephemeral=True)
        return
        
    if isinstance(tracks, wavelink.Playlist):
        playlist_tracks = tracks.tracks
        first = True
        for t in playlist_tracks:
            t.added_by = member.id
            if first and not player.playing:
                await player.play(t)
                first = False
            else:
                await player.queue.put_wait(t)
        await interaction.followup.send(f"Enqueued playlist **{tracks.name}** ({len(playlist_tracks)} tracks).", ephemeral=True)
    else:
        t = tracks[0]
        t.added_by = member.id
        if not player.playing:
            await player.play(t)
        else:
            await player.queue.put_wait(t)
        await interaction.followup.send(f"Enqueued **{t.title}**.", ephemeral=True)
        
    await update_play_window(player)

@app_commands.command(name="play", description="Play music from Spotify, SoundCloud, or direct URLs.")
@app_commands.describe(query="Track query or link to play")
async def play_cmd(interaction: discord.Interaction, query: str):
    cfg = get_guild_config(interaction.guild_id)
    if not cfg.get("music_enabled", False):
        await interaction.response.send_message("The Music module is disabled on this server.", ephemeral=True)
        return
        
    if not await check_command_permissions(interaction):
        return
        
    await interaction.response.defer(ephemeral=True)
    
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        await interaction.followup.send("You must be in a voice channel to use this command.", ephemeral=True)
        return
        
    author_channel = member.voice.channel
    
    if not interaction.guild.voice_client:
        try:
            player = await author_channel.connect(cls=NebotPlayer)
            await player.set_volume(DEFAULT_VOLUME)
        except Exception as e:
            await interaction.followup.send(f"Failed to connect to voice channel: {e}", ephemeral=True)
            return
    else:
        player = interaction.guild.voice_client
        if not isinstance(player, NebotPlayer):
            await player.disconnect()
            player = await author_channel.connect(cls=NebotPlayer)
            await player.set_volume(DEFAULT_VOLUME)
        elif player.channel.id != author_channel.id:
            try:
                await player.move_to(author_channel)
            except Exception as e:
                await interaction.followup.send(f"Failed to move to voice channel: {e}", ephemeral=True)
                return
                
    player.text_channel = author_channel
    
    await process_play_request(interaction, query, member, player)

@app_commands.command(name="next", description="Skip to the next playing track.")
async def next_cmd(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    if not cfg.get("music_enabled", False):
        await interaction.response.send_message("The Music module is disabled on this server.", ephemeral=True)
        return
        
    if not await check_command_permissions(interaction):
        return
        
    player = interaction.guild.voice_client
    if not player or not isinstance(player, NebotPlayer) or not player.playing:
        await interaction.response.send_message("There is nothing playing right now.", ephemeral=True)
        return
        
    await player.skip()
    await interaction.response.send_message("Skipped the current track.", ephemeral=True)

@app_commands.command(name="pause", description="Pause or resume playback.")
async def pause_cmd(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    if not cfg.get("music_enabled", False):
        await interaction.response.send_message("The Music module is disabled on this server.", ephemeral=True)
        return
        
    if not await check_command_permissions(interaction):
        return
        
    player = interaction.guild.voice_client
    if not player or not isinstance(player, NebotPlayer) or not player.playing:
        await interaction.response.send_message("There is nothing playing right now.", ephemeral=True)
        return
        
    paused = not player.paused
    await player.pause(paused)
    await update_play_window(player)
    status = "paused" if paused else "resumed"
    await interaction.response.send_message(f"Playback has been {status}.", ephemeral=True)

@app_commands.command(name="stop", description="Stop playback, clear queue, and disconnect.")
async def stop_cmd(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    if not cfg.get("music_enabled", False):
        await interaction.response.send_message("The Music module is disabled on this server.", ephemeral=True)
        return
        
    if not await check_command_permissions(interaction):
        return
        
    player = interaction.guild.voice_client
    if not player or not isinstance(player, NebotPlayer):
        await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
        return
        
    player.queue.clear()
    await player.disconnect()
    
    if player.play_window_message:
        try:
            embed = discord.Embed(title="Playback Stopped", description="The stream was terminated and the queue cleared.", color=discord.Color.red())
            await player.play_window_message.edit(embed=embed, view=None)
        except Exception:
            pass
        player.play_window_message = None
        
    await interaction.response.send_message("Playback stopped and disconnected.", ephemeral=True)

@app_commands.command(name="queue", description="Display the upcoming queue list.")
async def queue_cmd(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    if not cfg.get("music_enabled", False):
        await interaction.response.send_message("The Music module is disabled on this server.", ephemeral=True)
        return
        
    if not await check_command_permissions(interaction):
        return
        
    player = interaction.guild.voice_client
    if not player or not isinstance(player, NebotPlayer) or player.queue.is_empty:
        await interaction.response.send_message("The queue is currently empty.", ephemeral=True)
        return
        
    queue_list = []
    for i, track in enumerate(list(player.queue)[:10], 1):
        added_by = getattr(track, "added_by", None)
        added_str = f" (added by <@{added_by}>)" if added_by else ""
        if getattr(track, "uri", None):
            queue_list.append(f"`{i}.` **[{track.title}]({track.uri})**{added_str}")
        else:
            queue_list.append(f"`{i}.` **{track.title}**{added_str}")
            
    queue_str = "\n".join(queue_list)
    if len(player.queue) > 10:
        queue_str += f"\n*...and {len(player.queue) - 10} more tracks.*"
        
    embed = discord.Embed(title="Upcoming Queue", description=queue_str, color=discord.Color.teal())
    embed.set_footer(text=f"Total tracks in queue: {len(player.queue)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

def setup_music_commands(tree: app_commands.CommandTree):
    tree.add_command(play_cmd)
    tree.add_command(next_cmd)
    tree.add_command(pause_cmd)
    tree.add_command(stop_cmd)
    tree.add_command(queue_cmd)

    client = tree.client

    @client.event
    async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
        player: NebotPlayer = payload.player
        if player is None:
            return
        text_channel = getattr(player, "text_channel", None)
        if not text_channel:
            return
            
        embed = await build_play_window_embed(player)
        view = MusicPlayerView(player)
        
        if player.play_window_message:
            try:
                await player.play_window_message.edit(embed=embed, view=view)
                return
            except Exception:
                player.play_window_message = None
                
        try:
            msg = await text_channel.send(embed=embed, view=view)
            player.play_window_message = msg
        except Exception as e:
            print(f"[Music] Error sending play window: {e}")

    @client.event
    async def on_wavelink_track_end(payload: wavelink.TrackEndEventPayload):
        player: NebotPlayer = payload.player
        if player is None:
            return
        track = payload.track
        
        if player.loop_mode:
            await player.play(track)
            return
            
        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.play(next_track)
            return

        await asyncio.sleep(0.5)
        if not player.playing and player.queue.is_empty:
            if player.play_window_message:
                try:
                    embed = discord.Embed(
                        title="Playback Ended",
                        description="Queue is empty. Use `/play` to stream more tracks.",
                        color=discord.Color.light_grey()
                    )
                    await player.play_window_message.edit(embed=embed, view=None)
                except Exception:
                    pass
                player.play_window_message = None

    async def connect_node():
        await client.wait_until_ready()
        if not LAVALINK_PASSWORD:
            print("[Music] LAVALINK_PASSWORD is not set. For security reasons, a default password is no longer provided. Music module will not be initialized.")
            return

        try:
            port_val = int(LAVALINK_PORT)
        except ValueError:
            port_val = 2333
        
        node = wavelink.Node(uri=f"http://{LAVALINK_HOST}:{port_val}", password=LAVALINK_PASSWORD)
        try:
            await wavelink.Pool.connect(nodes=[node], client=client)
            print(f"[Music] Wavelink node initialized: {LAVALINK_HOST}:{port_val}")
        except Exception as e:
            print(f"[Music] Failed to connect to Wavelink: {e}")

    asyncio.create_task(connect_node())
