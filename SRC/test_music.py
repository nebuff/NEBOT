import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Define class types for type checking
class MockMember:
    pass

class MockUser:
    pass

# Setup in-memory mock for discord modules
class MockView:
    def __init__(self, *args, **kwargs):
        self.children = []
    def add_item(self, item):
        self.children.append(item)
        item.view = self

class MockButton:
    def __init__(self, *args, **kwargs):
        self.label = kwargs.get("label", "")
        self.style = kwargs.get("style", None)
        self.custom_id = kwargs.get("custom_id", None)
        self.disabled = False
        self.emoji = None
        self.view = None
        self.callback = None

class MockButtonDescriptor:
    def __init__(self, func, button):
        self.func = func
        self.button = button
    def __get__(self, instance, owner):
        if instance is None:
            return self
        async def bound_callback(interaction, *args, **kwargs):
            return await self.func(instance, interaction, self.button, *args, **kwargs)
        self.button.callback = bound_callback
        return self.button

def mock_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

def mock_button_decorator(*args, **kwargs):
    def decorator(func):
        btn = MockButton(*args, **kwargs)
        return MockButtonDescriptor(func, btn)
    return decorator

mock_discord = MagicMock()
mock_discord.Member = MockMember
mock_discord.User = MockUser
mock_discord.ui = MagicMock()
mock_discord.ui.View = MockView
mock_discord.ui.Button = MockButton
mock_discord.ui.button = mock_button_decorator
mock_discord.app_commands = MagicMock()
mock_discord.app_commands.command = mock_decorator
mock_discord.app_commands.describe = mock_decorator
mock_discord.ButtonStyle = MagicMock()
mock_discord.ButtonStyle.secondary = 1
mock_discord.ButtonStyle.success = 2
mock_discord.ButtonStyle.danger = 3
mock_discord.ButtonStyle.primary = 4
mock_discord.Color = MagicMock()
mock_discord.Color.teal = MagicMock(return_value=0x111111)
mock_discord.Color.red = MagicMock(return_value=0x222222)
mock_discord.Color.blurple = MagicMock(return_value=0x333333)
mock_discord.Color.light_grey = MagicMock(return_value=0x444444)

class MockEmbed:
    def __init__(self, *args, **kwargs):
        self.title = kwargs.get("title", None)
        self.description = kwargs.get("description", None)
        self.color = kwargs.get("color", None)
        self.fields = []
        self.author = None
        self.thumbnail = None
        self.footer = None
        
    def set_author(self, name, icon_url=None):
        self.author = {"name": name, "icon_url": icon_url}
        
    def add_field(self, name, value, inline=True):
        self.fields.append({"name": name, "value": value, "inline": inline})
        
    def set_thumbnail(self, url):
        self.thumbnail = url
        
    def set_footer(self, text, icon_url=None):
        self.footer = text

mock_discord.Embed = MockEmbed

sys.modules['discord'] = mock_discord
sys.modules['discord.ui'] = mock_discord.ui
sys.modules['discord.app_commands'] = mock_discord.app_commands

# Setup in-memory mock for wavelink module
mock_wavelink = MagicMock()
mock_wavelink.AutoPlayMode = MagicMock()
mock_wavelink.AutoPlayMode.enabled = "enabled"
mock_wavelink.AutoPlayMode.disabled = "disabled"

class MockPlayable:
    def __init__(self, title, uri, artwork=None, added_by=None):
        self.title = title
        self.uri = uri
        self.artwork = artwork
        self.added_by = added_by

class MockPlaylist:
    def __init__(self, name, tracks):
        self.name = name
        self.tracks = tracks

async def mock_search(query):
    if "empty" in query:
        return []
    if "playlist" in query:
        return MockPlaylist("Test Playlist", [
            MockPlayable("Track 1", "https://spotify.com/1"),
            MockPlayable("Track 2", "https://spotify.com/2")
        ])
    return [MockPlayable("Test Track", "https://soundcloud.com/test")]

mock_wavelink.Playable = MagicMock()
mock_wavelink.Playable.search = mock_search
mock_wavelink.Playlist = MockPlaylist

class MockQueue:
    def __init__(self):
        self.items = []
    def __len__(self):
        return len(self.items)
    @property
    def is_empty(self):
        return len(self.items) == 0
    def clear(self):
        self.items.clear()
    async def put_wait(self, item):
        self.items.append(item)
    def get(self):
        return self.items.pop(0) if self.items else None
    def __iter__(self):
        return iter(self.items)

class MockBasePlayer:
    def __init__(self, *args, **kwargs):
        self.queue = MockQueue()
        self.current = None
        self.playing = False
        self.paused = False
        self.volume = 100
        self.channel = MagicMock()
        self.channel.id = 9999
        self.channel.members = []
        self.disconnect = AsyncMock()
        self.skip = AsyncMock()
        self.move_to = AsyncMock()

    async def pause(self, state: bool):
        self.paused = state
    async def skip(self):
        pass
    async def play(self, track):
        self.current = track
        self.playing = True
    async def set_volume(self, value):
        self.volume = value

mock_wavelink.Player = MockBasePlayer
sys.modules['wavelink'] = mock_wavelink

# Import music_module after mocking dependencies
import music_module

def run_async(coro):
    return asyncio.run(coro)

def test_config_bindings():
    print("Testing config bindings...")
    assert music_module.LAVALINK_HOST is not None
    assert music_module.LAVALINK_PORT is not None
    print("Config bindings test passed.")

def test_query_preprocessing():
    print("Testing search query preprocessing...")
    # Plain text search queries should be prefixed with scsearch:
    assert music_module.prepare_query("NASTYWERKKKK") == "scsearch:NASTYWERKKKK"
    # Spotify URL patterns should be left unmodified for LavaSrc hook
    spotify_url = "https://open.spotify.com/track/4PTG3Z6ehGkBFm6OhuvDwM"
    assert music_module.prepare_query(spotify_url) == spotify_url
    # Direct URLs should be left unmodified
    soundcloud_url = "https://soundcloud.com/nastywerkkkk/fentanyl"
    assert music_module.prepare_query(soundcloud_url) == soundcloud_url
    print("Query preprocessing tests passed.")

def test_play_window_embed():
    print("Testing play window embed construction...")
    player = music_module.NebotPlayer()
    track = MockPlayable("fentanyl", "https://soundcloud.com/test", added_by=12345)
    player.current = track
    player.volume = 100
    player.loop_mode = True
    
    embed = run_async(music_module.build_play_window_embed(player))
    
    assert embed.title == "fentanyl"
    assert embed.url == "https://soundcloud.com/test"
    assert embed.author is not None
    assert embed.author["name"] == "Now playing"
    assert embed.author["icon_url"] is None
    # Check Added By field
    assert any(f["value"] == "<@12345>" for f in embed.fields if f["name"] == "Added by")
    # Check Voice Channel field (no emoji prefix)
    assert any("<#9999>" in f["value"] for f in embed.fields if f["name"] == "Voice Channel")
    # Check Status Bar field
    assert any("Queue Size: 0 · Volume: 100% · Loop: On" in f["value"] for f in embed.fields if f["name"] == "\u200b")
    
    print("Play window embed tests passed.")

def test_interactive_buttons():
    print("Testing player control buttons and state manipulation...")
    player = music_module.NebotPlayer()
    
    member = MagicMock(spec=MockMember)
    member.id = 5555
    member.bot = False
    player.channel.members = [member]
    
    view = music_module.MusicPlayerView(player)
    
    # Test Pause Toggle Button
    interaction = MagicMock()
    interaction.user = member
    interaction.response.edit_message = AsyncMock()
    
    assert player.paused is False
    run_async(view.pause_btn.callback(interaction))
    assert player.paused is True
    
    # Test AutoPlay Toggle Button
    assert player.autoplay_enabled is False
    run_async(view.autoplay_btn.callback(interaction))
    assert player.autoplay_enabled is True
    
    # Test Dashboard navigation
    run_async(view.dashboard_btn.callback(interaction))
    # Verify mock callback sent dashboard view
    interaction.response.edit_message.assert_called()
    
    print("Interactive button tests passed.")

def test_dashboard_view_controls():
    print("Testing dashboard view controls...")
    player = music_module.NebotPlayer()
    
    member = MagicMock(spec=MockMember)
    member.id = 5555
    member.bot = False
    player.channel.members = [member]
    
    player.volume = 80
    player.loop_mode = False
    
    dash_view = music_module.MusicDashboardView(player)
    
    interaction = MagicMock()
    interaction.user = member
    interaction.response.edit_message = AsyncMock()
    
    # Test Toggle Loop button
    run_async(dash_view.loop_btn.callback(interaction))
    assert player.loop_mode is True
    
    # Test Volume Up button
    run_async(dash_view.vol_up_btn.callback(interaction))
    assert player.volume == 90
    
    # Test Volume Down button
    run_async(dash_view.vol_down_btn.callback(interaction))
    assert player.volume == 80
    
    # Test Navigation back to player
    run_async(dash_view.back_btn.callback(interaction))
    interaction.response.edit_message.assert_called()
    
    print("Dashboard view controls tests passed.")

def test_commands_execution():
    print("Testing slash commands execution...")
    interaction = MagicMock()
    interaction.guild.voice_client = None
    
    member = MockMember()
    member.id = 5555
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.connect = AsyncMock(return_value=music_module.NebotPlayer())
    
    interaction.user = member
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.response.send_message = AsyncMock()

    # Test when music is disabled
    with patch("music_module.get_guild_config") as mock_get_cfg:
        mock_get_cfg.return_value = {"music_enabled": False}
        
        # Test play_cmd when disabled
        run_async(music_module.play_cmd(interaction, "fentanyl"))
        interaction.response.send_message.assert_called_with("The Music module is disabled on this server.", ephemeral=True)
        
        # Test next_cmd when disabled
        interaction.response.send_message.reset_mock()
        run_async(music_module.next_cmd(interaction))
        interaction.response.send_message.assert_called_with("The Music module is disabled on this server.", ephemeral=True)

        # Test pause_cmd when disabled
        interaction.response.send_message.reset_mock()
        run_async(music_module.pause_cmd(interaction))
        interaction.response.send_message.assert_called_with("The Music module is disabled on this server.", ephemeral=True)

        # Test stop_cmd when disabled
        interaction.response.send_message.reset_mock()
        run_async(music_module.stop_cmd(interaction))
        interaction.response.send_message.assert_called_with("The Music module is disabled on this server.", ephemeral=True)

        # Test queue_cmd when disabled
        interaction.response.send_message.reset_mock()
        run_async(music_module.queue_cmd(interaction))
        interaction.response.send_message.assert_called_with("The Music module is disabled on this server.", ephemeral=True)

    # Play Command (enabled)
    with patch("music_module.get_guild_config", return_value={"music_enabled": True}):
        run_async(music_module.play_cmd(interaction, "fentanyl"))
        assert interaction.user.voice.channel.connect.called
        interaction.followup.send.assert_called_with("Enqueued **Test Track**.", ephemeral=True)
        
        # Next Command (formerly skip_cmd, enabled)
        interaction.guild.voice_client = music_module.NebotPlayer()
        interaction.guild.voice_client.playing = True
        interaction.response.send_message.reset_mock()
        run_async(music_module.next_cmd(interaction))
        interaction.response.send_message.assert_called_with("Skipped the current track.", ephemeral=True)
        
    print("Slash commands tests passed.")

def test_music_admin_dashboard():
    print("Testing MusicConfigDashboard and ModuleSelectView settings interaction...")
    import admin_ui_module
    
    # Test build_embed and initial toggle status
    dashboard = admin_ui_module.MusicConfigDashboard(guild_id=12345)
    
    mock_config = {"music_enabled": True}
    with patch("admin_ui_module.get_guild_config", return_value=mock_config), \
         patch("admin_ui_module.save_config") as mock_save, \
         patch("configuration_module.log_setting_change_task") as mock_log:
         
        embed = dashboard.build_embed()
        assert embed.title == "Nebot Module Configuration: Music"
        assert any(f["value"] == "[ENABLED]" for f in embed.fields if f["name"] == "Status")
        
        # Test toggle button callback
        interaction = MagicMock()
        interaction.user = MockUser()
        dashboard.refresh = AsyncMock()
        
        run_async(dashboard.toggle_music.callback(interaction))
        assert mock_config["music_enabled"] is False
        assert mock_save.called
        assert mock_log.called
        dashboard.refresh.assert_called_once()
        
    # Test ModuleSelectView styling based on enabled/disabled states
    mock_config_enabled = {"music_enabled": True, "vc_wr_enabled": True}
    with patch("admin_ui_module.get_guild_config", return_value=mock_config_enabled):
        view_enabled = admin_ui_module.ModuleSelectView(guild_id=12345)
        # Style is success if enabled
        assert view_enabled.config_music.style == mock_discord.ButtonStyle.success
        assert view_enabled.config_music.label == "Music Module"
        assert view_enabled.config_vcwr.style == mock_discord.ButtonStyle.success
        assert view_enabled.config_vcwr.label == "VC WR Module"
        
        embed = view_enabled.build_embed()
        assert any(f["value"] == "[ENABLED]" for f in embed.fields if f["name"] == "Music Module")
        assert any(f["value"] == "[ENABLED]" for f in embed.fields if f["name"] == "VC WR Module")

        # Test callback of config_vcwr
        interaction = MagicMock()
        interaction.response = AsyncMock()
        with patch("vc_wr_module.VCWRConfigDashboard") as mock_vc_wr_dashboard:
            mock_inst = MagicMock()
            mock_inst.build_embed = MagicMock(return_value="mock_embed")
            mock_vc_wr_dashboard.return_value = mock_inst
            
            run_async(view_enabled.config_vcwr.callback(interaction))
            interaction.response.edit_message.assert_called_once_with(
                content=None, embed="mock_embed", view=mock_inst
            )

    mock_config_disabled = {"music_enabled": False, "vc_wr_enabled": False}
    with patch("admin_ui_module.get_guild_config", return_value=mock_config_disabled):
        view_disabled = admin_ui_module.ModuleSelectView(guild_id=12345)
        # Style is danger if disabled
        assert view_disabled.config_music.style == mock_discord.ButtonStyle.danger
        assert view_disabled.config_vcwr.style == mock_discord.ButtonStyle.danger
        
    print("Music admin dashboard tests passed.")

def test_music_permissions_system():
    print("Testing Music Permissions System...")
    import music_permissions_handler
    import admin_ui_module
    
    import discord
    # Let's create a MockMember with custom attributes
    class CustomMockMember(discord.Member):
        def __init__(self, member_id, roles=None, admin=False, manage_guild=False):
            self.id = member_id
            self.roles = roles or []
            self.guild_permissions = MagicMock()
            self.guild_permissions.administrator = admin
            self.guild_permissions.manage_guild = manage_guild
            self.voice = None
            self.bot = False
            
    class MockRole:
        def __init__(self, role_id):
            self.id = role_id

    guild_id = 998877
    cfg = {
        "music_enabled": True,
        "music_role_restriction_enabled": True,
        "music_allowed_roles": [111, 222],
        "music_allowed_users": [333, 444],
        "music_component_restriction_enabled": True
    }

    # Test is_admin_or_manager helper
    admin_member = CustomMockMember(123, admin=True)
    manager_member = CustomMockMember(456, manage_guild=True)
    normal_member = CustomMockMember(789)
    
    assert music_permissions_handler.is_admin_or_manager(admin_member) is True
    assert music_permissions_handler.is_admin_or_manager(manager_member) is True
    assert music_permissions_handler.is_admin_or_manager(normal_member) is False
    
    # Test owner ID override
    with patch("os.getenv", return_value="789"):
        assert music_permissions_handler.is_admin_or_manager(normal_member) is True

    # Test is_user_or_role_whitelisted helper
    whitelisted_user = CustomMockMember(333)
    whitelisted_role_user = CustomMockMember(888, roles=[MockRole(111)])
    non_whitelisted_user = CustomMockMember(888, roles=[MockRole(999)])
    
    assert music_permissions_handler.is_user_or_role_whitelisted(whitelisted_user, cfg) is True
    assert music_permissions_handler.is_user_or_role_whitelisted(whitelisted_role_user, cfg) is True
    assert music_permissions_handler.is_user_or_role_whitelisted(non_whitelisted_user, cfg) is False

    # Test check_command_permissions
    interaction = MagicMock()
    interaction.guild.id = guild_id
    interaction.user = whitelisted_user
    interaction.response.send_message = AsyncMock()
    
    with patch("music_permissions_handler.get_guild_config", return_value=cfg):
        # Whitelisted user command permissions
        res = run_async(music_permissions_handler.check_command_permissions(interaction))
        assert res is True
        
        # Non-whitelisted user command permissions
        interaction.user = non_whitelisted_user
        res = run_async(music_permissions_handler.check_command_permissions(interaction))
        assert res is False
        interaction.response.send_message.assert_called_once()
        
        # Check fail-safe defaults (empty whitelists)
        cfg_empty_lists = {
            "music_role_restriction_enabled": True,
            "music_allowed_roles": [],
            "music_allowed_users": []
        }
        with patch("music_permissions_handler.get_guild_config", return_value=cfg_empty_lists), \
             patch("music_permissions_handler.has_voice_channel_access", return_value=True):
            interaction.user = non_whitelisted_user
            res = run_async(music_permissions_handler.check_command_permissions(interaction))
            assert res is True  # Allowed because lists are empty and has voice access
            
        with patch("music_permissions_handler.get_guild_config", return_value=cfg_empty_lists), \
             patch("music_permissions_handler.has_voice_channel_access", return_value=False):
            interaction.user = non_whitelisted_user
            interaction.response.send_message.reset_mock()
            res = run_async(music_permissions_handler.check_command_permissions(interaction))
            assert res is False  # Blocked because lists empty but no voice access

    # Test check_button_permissions
    player = MagicMock()
    player.current = MagicMock()
    player.current.added_by = 555  # Track requester ID is 555
    
    interaction = MagicMock()
    interaction.guild.id = guild_id
    interaction.user = whitelisted_user
    interaction.response.send_message = AsyncMock()
    
    with patch("music_permissions_handler.get_guild_config", return_value=cfg):
        # Whitelisted user button permissions
        res = run_async(music_permissions_handler.check_button_permissions(interaction, player))
        assert res is True
        
        # Requester user button permissions
        requester_user = CustomMockMember(555)
        interaction.user = requester_user
        res = run_async(music_permissions_handler.check_button_permissions(interaction, player))
        assert res is True
        
        # Non-whitelisted, non-requester user button permissions
        interaction.user = non_whitelisted_user
        res = run_async(music_permissions_handler.check_button_permissions(interaction, player))
        assert res is False
        interaction.response.send_message.assert_called_once_with(
            "Access Denied: You cannot modify or control the current streaming playback.",
            ephemeral=True
        )

    # Test MusicPermissionsConfigDashboard UI
    permissions_view = admin_ui_module.MusicPermissionsConfigDashboard(guild_id)
    with patch("admin_ui_module.get_guild_config", return_value=cfg):
        embed = permissions_view.build_embed()
        assert embed.title == "Nebot Module: Music Permissions Configuration"
        assert any(f["name"] == "Role Restriction" and f["value"] == "Enabled" for f in embed.fields)
        assert any(f["name"] == "Restrict Components" and f["value"] == "Enabled" for f in embed.fields)
        assert any(f["name"] == "Whitelisted Roles" and "<@&111>" in f["value"] for f in embed.fields)
        assert any(f["name"] == "Whitelisted Users" and "<@333>" in f["value"] for f in embed.fields)
        
    print("Music Permissions System tests passed.")

def test_spotify_playlist_and_album_resolution():
    print("Testing Spotify playlist and album resolution...")
    
    # Test fetch_spotify_tracks scraping logic with mock aiohttp response
    mock_html = """
    <html>
      <script>{"props":{"pageProps":{"state":{"data":{"entity":{"name":"Mock Playlist","trackList":[
        {"title": "Track 1", "subtitle": "Artist 1"},
        {"title": "Track 2", "subtitle": "Artist 2"}
      ]}}}}}}</script>
    </html>
    """
    
    class MockResponse:
        def __init__(self, text_data, status=200):
            self._text = text_data
            self.status = status
        async def text(self):
            return self._text
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
    class MockClientSession:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, url, **kwargs):
            return MockResponse(mock_html)
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("aiohttp.ClientSession", MockClientSession):
        res = run_async(music_module.fetch_spotify_tracks("https://open.spotify.com/playlist/test12345"))
        assert res is not None
        assert res["name"] == "Mock Playlist"
        assert len(res["tracks"]) == 2
        assert res["tracks"][0]["title"] == "Track 1"
        assert res["tracks"][0]["artist"] == "Artist 1"
        
    # Test resolve_spotify_track
    with patch("wavelink.Playable.search", new=AsyncMock(return_value=[MockPlayable("Resolved Song", "http://resolved")])) as mock_wavelink_search:
        track = run_async(music_module.resolve_spotify_track("Track 1", "Artist 1"))
        assert track is not None
        assert track.title == "Resolved Song"
        assert mock_wavelink_search.called
        
    # Test process_play_request with mock Spotify playlist
    interaction = MagicMock()
    interaction.followup.send = AsyncMock()
    
    player = music_module.NebotPlayer()
    player.current = None
    player.playing = False
    
    member = MockMember()
    member.id = 1122
    
    mock_spotify_data = {
        "name": "My Spotify Album",
        "tracks": [
            {"title": "Track 1", "artist": "Artist 1"},
            {"title": "Track 2", "artist": "Artist 2"}
        ]
    }
    
    mock_resolved_track_1 = MockPlayable("Song 1", "https://youtube.com/1")
    mock_resolved_track_2 = MockPlayable("Song 2", "https://youtube.com/2")
    
    async def mock_resolve_spotify_track(title, artist):
        if "Track 1" in title:
            return mock_resolved_track_1
        return mock_resolved_track_2

    with patch("music_module.fetch_spotify_tracks", return_value=mock_spotify_data), \
         patch("music_module.resolve_spotify_track", mock_resolve_spotify_track), \
         patch("music_module.update_play_window", new=AsyncMock()) as mock_update_win:
         
        run_async(music_module.process_play_request(
            interaction, 
            "https://open.spotify.com/album/3Pjxmlf1fPMvKFvxxpVPGP", 
            member, 
            player
        ))
        
        # Verify first track started playing and second was enqueued
        assert player.current == mock_resolved_track_1
        assert len(player.queue) == 1
        assert player.queue.get() == mock_resolved_track_2
        assert mock_resolved_track_1.added_by == member.id
        assert mock_resolved_track_2.added_by == member.id
        assert mock_update_win.called
        
    print("Spotify playlist and album resolution tests passed.")

if __name__ == "__main__":
    test_config_bindings()
    print("-" * 40)
    test_query_preprocessing()
    print("-" * 40)
    test_play_window_embed()
    print("-" * 40)
    test_interactive_buttons()
    print("-" * 40)
    test_dashboard_view_controls()
    print("-" * 40)
    test_commands_execution()
    print("-" * 40)
    test_music_admin_dashboard()
    print("-" * 40)
    test_music_permissions_system()
    print("-" * 40)
    test_spotify_playlist_and_album_resolution()
    print("-" * 40)
    print("ALL MUSIC MODULE TESTS PASSED SUCCESSFULLY!")
