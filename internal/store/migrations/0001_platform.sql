-- Canonical PostgreSQL schema for NEBOT.
--
-- This mirrors the tables created by SRC/db_service.py after its SQLite-to-
-- PostgreSQL translation, so it is a no-op on an existing Python-created
-- database and produces the same shape on a fresh one.
--
-- Keep this file additive while the Python bot is still a rollback option.

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    system_name TEXT,
    fronting_member TEXT
);

CREATE TABLE IF NOT EXISTS members (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    short_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    avatar_msg_id BIGINT,
    avatar_chan_id BIGINT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (user_id, short_name)
);

CREATE TABLE IF NOT EXISTS proxy_tags (
    id BIGSERIAL PRIMARY KEY,
    member_id BIGINT NOT NULL,
    proxy_tag TEXT NOT NULL,
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
    UNIQUE (member_id)
);

CREATE TABLE IF NOT EXISTS guild_configs (
    guild_id BIGINT PRIMARY KEY,
    prefix TEXT,
    cmd TEXT,
    channel_id BIGINT,
    admin_role_id BIGINT,
    shared_channel_id BIGINT,
    private_sessions_enabled BOOLEAN,
    shared_enabled BOOLEAN,
    ne_os_enabled BOOLEAN,
    nebuff_module_enabled BOOLEAN,
    battle_enabled BOOLEAN,
    battle_default_hp BIGINT,
    battle_damage_range TEXT,
    battle_timeout BIGINT,
    minesweeper_enabled BOOLEAN,
    minesweeper_default_mines BIGINT,
    warning_tracker_enabled BOOLEAN,
    warning_platforms TEXT,
    warning_severity_points TEXT,
    warning_escalation_mode TEXT,
    warning_rolling_window_days BIGINT,
    warning_ladder TEXT,
    warning_log_channel_id BIGINT,
    warning_dm_enabled BOOLEAN,
    verification_enabled BOOLEAN,
    verification_unverified_role_id BIGINT,
    verification_verified_role_id BIGINT,
    verification_verified_role_ids TEXT,
    verification_channel_id BIGINT,
    verification_landing_channel_id BIGINT,
    global_log_channel_id BIGINT,
    verification_log_channel_id BIGINT,
    verification_timeout BIGINT,
    mod_role_id BIGINT,
    auto_roller_enabled BOOLEAN,
    auto_roller_role_id BIGINT,
    auto_roller_role_ids TEXT,
    automod_enabled BOOLEAN,
    automod_filters TEXT,
    automod_ignored_channels TEXT,
    automod_ignored_roles TEXT,
    music_enabled BOOLEAN,
    music_role_restriction_enabled BOOLEAN,
    music_allowed_roles TEXT,
    music_allowed_users TEXT,
    music_component_restriction_enabled BOOLEAN,
    analytics_enabled BOOLEAN,
    analytics_excluded_channels TEXT,
    vc_wr_enabled BOOLEAN,
    join_filter_enabled BOOLEAN,
    join_filter_min_age_value BIGINT,
    join_filter_min_age_unit TEXT,
    join_filter_username_patterns TEXT,
    join_filter_username_emojis BOOLEAN,
    join_filter_username_homoglyphs BOOLEAN,
    join_filter_enforcement TEXT,
    join_filters TEXT,
    auto_channel_namer_enabled BOOLEAN,
    auto_channel_namer_left TEXT,
    auto_channel_namer_right TEXT,
    auto_channel_namer_font TEXT,
    auto_channel_namer_exclude_ids TEXT,
    plurality_enabled BOOLEAN,
    self_roles_enabled BOOLEAN,
    self_roles_groups TEXT
);

CREATE TABLE IF NOT EXISTS global_configs (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS battle_stats (
    user_id TEXT PRIMARY KEY,
    points BIGINT DEFAULT 0,
    wins BIGINT DEFAULT 0,
    losses BIGINT DEFAULT 0,
    total_rounds_won BIGINT DEFAULT 0,
    minesweeper_wins BIGINT DEFAULT 0,
    minesweeper_losses BIGINT DEFAULT 0,
    minesweeper_quits BIGINT DEFAULT 0,
    minesweeper_total_safe_clicks BIGINT DEFAULT 0,
    minesweeper_total_correct_flags BIGINT DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS warnings (
    id TEXT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    details TEXT,
    severity TEXT,
    points BIGINT,
    timestamp TEXT,
    action_taken TEXT,
    FOREIGN KEY (guild_id) REFERENCES guild_configs(guild_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS warning_linked_accounts (
    id BIGSERIAL PRIMARY KEY,
    warning_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    identifier TEXT NOT NULL,
    display_name TEXT NOT NULL,
    FOREIGN KEY (warning_id) REFERENCES warnings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS join_filtering_logs (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT,
    account_created_at TEXT,
    age_evaluated TEXT,
    reason TEXT,
    action TEXT,
    status TEXT,
    timestamp TEXT,
    FOREIGN KEY (guild_id) REFERENCES guild_configs(guild_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proxied_messages (
    message_id TEXT PRIMARY KEY,
    author_id BIGINT NOT NULL,
    content TEXT,
    reply_prefix TEXT,
    channel_id BIGINT NOT NULL,
    timestamp DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    cwd TEXT NOT NULL,
    installed_packages TEXT NOT NULL,
    history TEXT NOT NULL,
    env TEXT NOT NULL,
    start_time TEXT NOT NULL,
    root TEXT NOT NULL,
    is_persistent BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS vc_wr_records (
    guild_id BIGINT,
    user_id TEXT,
    duration DOUBLE PRECISION DEFAULT 0.0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS vc_wr_sessions (
    guild_id BIGINT,
    user_id TEXT,
    join_time DOUBLE PRECISION,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS server_analytics (
    guild_id BIGINT PRIMARY KEY,
    messages TEXT,
    churn TEXT,
    voice TEXT
);

CREATE INDEX IF NOT EXISTS idx_members_user ON members(user_id);

CREATE INDEX IF NOT EXISTS idx_warnings_guild ON warnings(guild_id);

CREATE INDEX IF NOT EXISTS idx_warning_accounts_warning ON warning_linked_accounts(warning_id);

CREATE INDEX IF NOT EXISTS idx_join_logs_guild ON join_filtering_logs(guild_id);
