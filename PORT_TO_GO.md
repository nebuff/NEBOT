# Porting NEBOT to Go

**Status:** proposal + M0 scaffold + M1 core + M2 auto-roller/admin dashboard + analytics + self roles
**Reference implementation:** `SRC/` — Python 3.11, discord.py 2.x, wavelink, psycopg2/SQLite
**Target:** one statically linked Go binary, PostgreSQL, Lavalink v4

---

## Executive summary

NEBOT is ~26,000 lines of Python across 27 source modules and 23 test files. Most of
that volume is Discord UI code (`admin_ui_module.py` alone is 3,391 lines and the
repo defines 173 `discord.ui` classes), not business logic. The port is therefore
not a line-by-line translation: the right approach is to port the behaviour and
replace the object-oriented view classes with a small, stateless component router.

The recommended sequence is:

1. Build the Go platform (gateway, command/component router, config, DB) — **M0/M1**.
2. Port the low-risk event modules to prove the pattern — **M2**.
3. Port the fake shell, which is pure Go logic with no Discord UI — **M3**.
4. Port moderation (automod, warnings, verification, join filtering) — **M4**.
5. Port games and the large dashboards — **M5**.
6. Port music (Lavalink) and plurality — **M6/M7**.
7. Shadow-test, cut over, keep Python as rollback — **M8**.

Realistic effort for one developer who knows the codebase: **60–91 engineer-days**.
The admin dashboards and the 173 UI classes are the bulk of it; automod and
plurality are the highest-risk behaviour to match.

### What this change already contains (M0)

- `go.mod` with `discordgo v0.29.0` and `pgx/v5 v5.13.0`.
- `cmd/nebot/main.go`: env config → PostgreSQL pool → migrations → gateway → graceful shutdown.
- `internal/config`: env loading/validation, including the existing `DATABASE_*` variable names.
- `internal/store`: `pgxpool`, embedded SQL migrations, and a **non-destructive schema
  that is compatible with databases created by the Python bot**.
- `internal/bot`: gateway session, slash-command registry, message dispatch, and a
  stateless `custom_id` router for buttons/selects/modals.
- `internal/modules/core`: `/ping`.
- `internal/module` + `internal/interact`: the module contract and interaction helpers.
- `Dockerfile`, `.dockerignore`, tests for config and migration parsing.
- This plan.

### M1 core (this change)

- Typed `guild.Config` covering all 65 `guild_configs` columns, with defaults matching Python's `get_guild_config`.
- `guild.Cache`: lazy per-guild loading, deep-copied reads, and single-row write-through persistence.
- `auth.IsAdmin` / `auth.IsMod`: owner, computed Administrator permission (with guild-state fallback), and configured admin/mod roles.
- First feature modules: `@nebuff` and `@grok` (message → config → reply path).
- Tests for config default/round-trip behaviour, cache semantics, auth, and both modules.

Config writes are currently full-row upserts; targeted per-field updates can follow once more dashboards exist.

### M2 auto-roller + first dashboard (this change)

- `/admin` opens an ephemeral module manager; the Auto-Roller entry is wired, the other modules are status-only until their ports land.
- Auto-Roller dashboard: toggle, clear roles, and a native role multi-select, all stateless and routed by `custom_id`.
- Member-join provider: grants configured roles after filtering them through the bot's role hierarchy, skipping missing/already-held roles, and logging per-role API failures.
- Setting changes save one guild row and emit the Python-compatible audit-log embed when `global_log_channel_id` is configured.
- Tests cover role planning, dashboard construction, and member-join dispatch/interception.

### Analytics (this change)

- Message velocity, member churn, and non-bot voice concurrency are collected through message, member-join, member-leave, and voice-state hooks.
- Writes are aggregated per guild in memory and flushed every five seconds, so a message no longer reloads and rewrites the entire `server_analytics` table the way Python does. Only dirty guild rows are written; failed rows stay dirty for retry.
- The persisted `messages` / `churn` / `voice` JSON remains compatible with the Python-created schema, and 30-day pruning matches `clean_old_records`.
- `/analytics` produces the 24-hour or 7-day report for moderators; `/admin` now has a Server Analytics entry with enable/disable, excluded-channel configuration, and historical-data clearing.
- Tests cover aggregation, batching, retention, clearing, JSON compatibility, dashboard construction, report formatting, and voice counting.

### Self-assignable roles (this change)

- `/admin` now has a Self Roles entry. The dashboard supports module enable/disable, group creation via modal, group mode cycling, single/multi limits, embed title/description/color, role add/remove, button-color styling, deletion, and channel deployment.
- `self_roles_groups` remains the Python JSON shape. Missing Python defaults (`auto_take_away`, `allow_take_off`, role style) are applied on read, so existing rows load without a migration.
- Deployed role menus are stateless: buttons route through compact group-keyed `custom_id`s and keep working after restart. A `self_role:<guild>:<group>:<role>` compatibility route accepts menus deployed by the Python bot.
- Role requirements, single-mode `require_one`/`auto_take_away`, multi-mode min/max, `allow_take_off`, and per-role requirements are enforced by a pure planner with table-driven tests. The bot checks role existence and hierarchy/permission failures before replying with the Python-compatible action message.
- Tests cover JSON defaults/round-trip, mode and requirement decisions, custom-ID parsing, all dashboards, the deployed menu, and the admin entry.

### What this does **not** do yet

- No `/config` read-only overview yet; `/admin` currently exposes Auto-Roller, Server Analytics, and Self Roles (more modules in M2+).
- No `/dash` member analytics view yet; reports are available through `/analytics` and `/admin`.
- No automod, shell, music, plurality, games, or bulk-role management yet (M2+).
- No Lavalink client yet (M6).
- No CI workflow yet.

---

## 1. What exists today

### 1.1 Module inventory

LOC from `wc -l SRC/*.py`; total is 25,993 lines including tests.

| Python module | LOC | Responsibility | Port difficulty |
|---|---:|---|---|
| `admin_ui_module.py` | 3,391 | `/admin`, `/dash`, `/mod`, `/nebuff` dashboards; ~60 views/modals | **XL** |
| `automod_module.py` | 2,257 | Regex/keyword filters, leetspeak/emoji/homoglyph normalisation, nick/join checks, dashboards | **L** |
| `plurality_module.py` | 1,341 | Plural systems, members, proxy tags, proxied message edit/delete, avatars | **XL** |
| `join_filtering_module.py` | 1,289 | Account-age and username filters, enforcement, logs, dashboards | **L** |
| `warning_tracker_module.py` | 1,217 | Multi-platform warnings, points, static/rolling windows, ladders, DMs/logs | **L** |
| `commands_registry_handlers_module.py` | 744 | ~40 fake-shell commands plus SSRF-safe HTTP checks | **M** |
| `self_assignable_roles_module.py` | 738 | Persistent role menus, groups, button styling, limits | **L** |
| `verification_module.py` | 727 | Timed challenge gate, role swap, timeout kicks, logs | **M** |
| `music_module.py` | 678 | Wavelink/Lavalink v4, Spotify resolver, queue, player UI | **L** |
| `vc_wr_module.py` | 600 | Voice-channel world records, session tracking, leaderboard | **M** |
| `db_service.py` | 530 | SQLite/PostgreSQL adapter and SQL translation shim | **replace** |
| `battle_module.py` | 490 | Turn-based battle game, stats | **M** |
| `configuration_module.py` | 464 | Defaults, per-guild config cache, permission helpers, audit embeds | **M** |
| `main_entrypoint.py` | 461 | Client bootstrap, event fan-out, session watcher, intent fallback | **M** |
| `analytics_module.py` | 434 | Message velocity, churn, voice concurrency, 30-day retention | **M** |
| `session_module.py` | 415 | Fake shell session, virtual filesystem, persistence | **M** |
| `auto_channel_namer_module.py` | 409 | Renames voice channels from member activity/fonts | **M** |
| `minesweeper_module.py` | 350 | Interactive Minesweeper with buttons | **S/M** |
| `bulk_role_module.py` | 324 | Bulk add/remove roles with filters and job progress | **M** |
| `grok_module.py` | 148 | `@grok` joke replies | **S** |
| `editor_module.py` | 133 | Nano-like editor inside the shell | **M** |
| `packages_module.py` | 129 | Fake apt packages and animated output | **S** |
| `utility_module.py` | 127 | ANSI blocks, chunked sends, prompts, animated edits | **S** |
| `music_permissions_handler.py` | 114 | Music role/user whitelists and VC access | **S** |
| `auto_roller_module.py` | 83 | Roles granted on join | **S** |
| `nebuff_module.py` | 81 | `@nebuff` unit conversion joke module | **S** |
| `filesystem_module.py` | 74 | In-memory FS node model and default tree | **S** |
| Tests (`test_*.py`) | ~5,900 | Pytest suite with mocks | port selectively |

### 1.2 Discord surface

The codebase uses essentially every modern Discord interaction feature:

- Slash commands (~30; the authoritative list is the union of every
  `setup_*_commands(tree)` function). Examples: `/battle`, `/stats`,
  `/minesweeper`, `/vcwr`, `/analytics`, `/play`, `/next`, `/pause`, `/stop`,
  `/queue`, `/warning`, `/warning-view`, `/warning-edit`, `/warning-delete`,
  `/admin`, `/dash`, `/mod`, `/nebuff`, `/config`, `/set-prefix`, `/set-channel`,
  `/set-admin-role`, `/set-mod-role`, `/set-cmd`, `/set-shared-channel`,
  `/toggle-private-sessions`, `/toggle-shared-sessions`.
- Prefix/message commands: `!nebot <cmd>` (configurable prefix/trigger), DMs,
  shared prefixless channels, and `!debug_plurality`.
- Chat triggers: `@grok`, `@nebuff`, and `ap <member>` for plurality fronting.
- Buttons, select menus (string, user, role, channel), modals, and autocomplete.
- Persistent views registered at startup: `SelfRolesMenuView` and
  `VerificationGateView`. Dashboards use `timeout=None` but are otherwise
  in-memory views.
- Voice state events (auto-namer, VC world records, music).
- Member join/update/remove events (verification, auto-roller, join filtering,
  automod nickname checks, analytics churn).

### 1.3 State and storage

- PostgreSQL when `DATABASE_HOST` is set, otherwise SQLite. A `translate_sql`
  shim rewrites `?` placeholders, `INTEGER PRIMARY KEY AUTOINCREMENT`, and
  `INSERT OR IGNORE/REPLACE` into PostgreSQL forms.
- Guild config is a single 60+ column row per guild, plus 15 JSON-encoded TEXT
  columns (`warning_ladder`, `automod_filters`, `self_roles_groups`, ...). The
  whole cache is rewritten by `save_config()` on every change.
- Shell sessions are in memory and serialised as JSON (`root`, `cwd`, history,
  env) into the `sessions` table for persistent sessions.
- Analytics is one JSON blob per guild in `server_analytics`.
- Plurality caches all systems/members in `plurality_data` and rewrites them on
  save.
- Music state is in Wavelink players, not the DB.

### 1.4 External services

| Service | Used by | Go plan |
|---|---|---|
| Discord API | everything | `discordgo` gateway + REST |
| PostgreSQL | everything | `pgx/v5` + `pgxpool` |
| Lavalink v4 | music | `disgolink/v4` (Lavalink 4.x client) |
| Spotify Web API / embed scraping | music playlist/album fallback | Prefer LavaSrc; port the resolver only if needed |
| Discord webhooks / avatar channel | plurality | Discord REST via `discordgo` |

---

## 2. Target architecture

```
cmd/nebot/main.go               process wiring, signals, graceful shutdown
internal/
  config/                       env parsing and validation
  store/                        pgx pool, queries, embedded migrations
    migrations/                 canonical PostgreSQL schema
  bot/                          gateway session, dispatcher, command sync
  interact/                     interaction responder helpers (reply/defer/update)
  module/                       Module/Command/Route contracts
  modules/
    core/                       /ping, /help, /about (platform)
    fun/                        grok, nebuff
    shell/                      Ne-OS filesystem, editor, packages, commands
    automod/                    normalisation, filter engine, dashboards
    warnings/                   warning tracker, ladders, escalation
    verification/               gate, role swap, timeout worker
    joinfilter/                 age/username screening, enforcement
    roles/                      auto-roller, self roles, bulk roles
    analytics/                  velocity/churn/voice aggregation
    vcwr/                       voice world records
    namer/                      auto channel naming
    games/                      battle, minesweeper
    music/                      Lavalink player, queue, Spotify, player UI
    plurality/                  systems, proxy tags, proxied messages
    admin/                      /admin, /dash, /mod, /nebuff dashboards
  ui/                           component/modal builders and custom_id codec
  auth/                         is_admin/is_mod/music permission checks
  pyjson/                       Python-compatible JSON/time/ID helpers
  testutil/                     fixture loaders, fake Discord API, test DB
```

### 2.1 Interaction flow

```
Discord gateway
  └─ discordgo session
       ├─ InteractionCreate
       │    ├─ slash command  → command map (by name)       → module handler
       │    ├─ component      → longest-prefix custom_id    → module handler
       │    ├─ modal submit   → longest-prefix custom_id    → module handler
       │    └─ autocomplete   → registered autocomplete map → choices
       ├─ MessageCreate
       │    └─ ordered module chain; first handler returning handled=true wins
       └─ guild/member/voice events → event-specific modules
```

`discordgo` invokes handlers concurrently, so all shared state (config cache,
session map, analytics buffers) must be guarded by mutexes. The scaffold keeps
module registration before `Run`, so the command/route maps are read-only at
runtime.

### 2.2 Stateless components instead of view objects

Python keeps `discord.ui.View` objects in memory. After a restart, old dashboard
buttons only work if the view was explicitly re-registered at startup. The Go
port should make every component stateless:

- `custom_id` format: `nebot:v1:<module>:<action>[:<short args>]`.
- Keep it under Discord's 100-character limit. Put IDs and page numbers in the
  `custom_id`; put authoritative state in the database or the message embed.
- Route by **longest prefix**, not exact match, so one handler can serve many
  related controls.
- Never trust guild/user IDs embedded in `custom_id`; always use
  `interaction.GuildID`, `interaction.Member.User.ID`, and re-check permissions.
  A user can replay a component from another guild otherwise.
- Persistent controls that must survive a restart (self-role menus, verification
  gate) get fixed prefixes and are handled by the same router.

This also removes the `add_view(...)` startup loop. It does mean old messages
created by the Python bot need compatibility routes after cutover (see §6).

### 2.3 Concurrency model

- One goroutine per gateway event is fine; `pgxpool` bounds DB concurrency.
- Replace Python's global `guild_configs` dict with a typed cache:
  `map[int64]*GuildConfig` behind `sync.RWMutex`, loaded lazily per guild and
  written through to PostgreSQL. Do **not** copy `save_config()`'s
  rewrite-everything behaviour.
- Replace `asyncio.Lock` + whole-blob analytics rewrites with in-memory
  aggregation flushed every 15–30 seconds and on shutdown. Only one process may
  own the write path (see §6).
- Long-running loops (session watcher, VC session ticker, verification timeout
  worker) take a `context.Context` and stop on shutdown.
- Use `recover()` in every gateway handler; a panic in one handler must not take
  down the bot. The scaffold does this.

### 2.4 Library choices

| Concern | Choice | Why | Alternative |
|---|---|---|---|
| Discord gateway/REST | `github.com/bwmarrin/discordgo` v0.29.0 | Largest ecosystem, complete REST/gateway/voice primitives, stable, no framework lock-in | `disgo` (typed, first-class disgolink, but smaller community and pre-v1) |
| Lavalink | `github.com/disgoorg/disgolink/v4` | Lavalink 4.x, same protocol as wavelink; supports any Discord library; v4 is currently a pinned pseudo-version, so pin a commit | Minimal internal Lavalink REST+WS client |
| PostgreSQL | `github.com/jackc/pgx/v5` + `pgxpool` | Fast, correct types, transactions, pool; no ORM | `database/sql` + `pgx` stdlib |
| Logging | `log/slog` | Structured JSON, stdlib, no dependency | zerolog/zap |
| Admin regexes | `regexp` (RE2) for fixed patterns; `github.com/dlclark/regexp2` with a match timeout for user-supplied patterns | Go RE2 has no lookarounds/backreferences; Python `re` does. regexp2 is pure Go and supports them, but needs a timeout to avoid ReDoS | Reject non-RE2 patterns at input |
| Tests | stdlib `testing`, table-driven; PostgreSQL via Docker/testcontainers | No assertion framework needed | testify |
| Deploy | multi-stage Docker → distroless/static | Static binary, no Python at runtime | systemd unit |

**Why not disgo?** It is a good library and would reduce router code, but it is
pre-v1 with a smaller community. The bot needs long-term stability more than a
typed command DSL. If the custom router becomes a maintenance burden in M5,
revisit before the dashboards are ported; the module contract isolates the
choice.

---

## 3. Port sequence

Estimates are engineer-days for one developer familiar with the Python code.
Each milestone ends with a runnable bot; no big-bang rewrite.

| Milestone | Scope | Est. | Done when |
|---|---|---:|---|
| **M0 Foundation** | module layout, config, slog, pgx, migrations, gateway, router, `/ping`, Dockerfile, tests | 2–3 | `go build ./...`, `go test ./...` pass; bot connects; `/ping` works; SIGTERM exits cleanly; empty DB gets the full schema |
| **M1 Platform** | typed guild config + cache, auth (`is_admin`/`is_mod`), ANSI/chunked send helpers, audit-log embed, command/component UI kit, `/config` read-only | 4–6 | `/config` matches Python defaults; role permissions match; JSON blobs round-trip Python-written rows; restart-safe component demo |
| **M2 Low-risk modules** | grok, nebuff, auto-roller, self roles, auto channel namer, vc_wr, analytics | 6–9 | every command/trigger behaves as Python; persistent self-role menus survive restart; analytics write frequency reduced but data shape identical |
| **M3 Ne-OS shell** | filesystem, sessions, editor, packages, ~40 commands, prompt/ANSI rendering, session expiry watcher | 6–9 | help/command parity; Python-created `sessions.root` JSON loads in Go; FS/editor tests ported |
| **M4 Moderation** | automod engine + dashboards, warning tracker, verification, join filtering | 12–18 | fixture parity for normalisation/matching; warning points/ladder match; verification gate/timeout works; join filter actions/logs match |
| **M5 Games & dashboards** | battle, minesweeper, `/admin`, `/dash`, `/mod`, `/nebuff`, bulk roles | 12–18 | every view/modal reachable and restart-safe; permission checks enforced server-side; job progress works |
| **M6 Music** | disgolink node, join/leave, search, queue, pause/resume/skip/stop, autoplay, Spotify, player buttons, permissions | 5–8 | plays from Lavalink; queue/loop/volume buttons work; whitelist enforced; node reconnect tested |
| **M7 Plurality** | systems/members, proxy tags, message proxying, edit/delete, avatars, fronting, per-guild toggle | 8–12 | proxy/edit/delete parity; avatar upload works; DB round-trip; no message loops |
| **M8 Cutover** | shadow mode, command diff, custom_id compatibility, load test, rollback rehearsal | 5–8 | one week of shadow logs with no unexplained divergence; rollback documented and tested |

Total: **60–91 engineer-days** end-to-end.

### 3.1 Suggested first week

1. **Day 1:** Stand up the scaffold against a copy of the production DB.
   Register `/ping` in a development guild (`DISCORD_DEV_GUILD_ID`) and confirm
   the schema migration is a no-op on the existing DB.
2. **Day 2:** Port the guild config model and auth helpers. Add fixture tests
   that load a Python-written `guild_configs` row and compare every field.
3. **Day 3:** Port `utility_module` send/chunk helpers and the UI kit
   (buttons/selects/modals). Add a throwaway `/config` panel that edits one
   boolean.
4. **Day 4–5:** Port `grok` (message trigger, no DB) and `auto-roller`
   (join event + simple dashboard). This exercises the message chain, member
   intent, config writes, and component routing.

Do not start with the admin UI. It is the largest file and depends on almost
every other module.

---

## 4. Data compatibility

The Python bot and the Go bot must be able to read the same database during the
transition. **Do not change column names or types until Python is retired.**

### 4.1 Type mapping

| Python storage | PostgreSQL (existing) | Go |
|---|---|---|
| Discord snowflake as `int` | `BIGINT` | `int64`; convert to/from string at the Discord boundary |
| Discord snowflake as `str` | `TEXT` | `string` |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL` (int4) in Python-created DBs; `BIGSERIAL` in fresh Go DBs | `int64` for both |
| JSON arrays/objects | `TEXT` | `json.RawMessage` in M0/M1, then typed structs with `json.Marshal` |
| `datetime.utcnow().isoformat()` | `TEXT` | `time.Time` + Python-compatible formatter |
| `REAL` | `REAL` (float4) in existing DBs | `float64` |
| nullable `BOOLEAN` | `BOOLEAN` nullable | `*bool` or `COALESCE` |
| UUID hex warning IDs | `TEXT` (32 hex chars) | `crypto/rand` 16 bytes → hex |

### 4.2 Non-obvious compatibility rules

- **Timestamps:** `warnings.timestamp` and `sessions.start_time` are naive UTC
  ISO strings with optional microseconds, e.g. `2026-11-19T12:34:56.123456` or
  `2026-11-19T12:34:56` (no `Z`). Analytics hour buckets use
  `2026-11-19T12:00:00Z`. Port a `pyjson` helper with tests; do not use Go's
  default RFC3339 formatting everywhere.
- **JSON:** Python `json.dumps` preserves insertion order and does not HTML-escape.
  Go sorts map keys and escapes `<`, `>`, `&` by default. Use
  `json.Encoder.SetEscapeHTML(false)` when writing JSON text; readers parse it,
  so key order differences are harmless.
- **Upserts:** Python's `INSERT OR IGNORE/REPLACE` is translated by
  `db_service.translate_sql` into specific `ON CONFLICT` clauses. Replicate each
  one explicitly. Notable cases: `members` conflicts on `(user_id, short_name)`,
  `proxy_tags` on `(member_id)`, `guild_configs` on `(guild_id)`,
  `warning_linked_accounts`/`join_filtering_logs` rely on `RETURNING id`.
- **Foreign keys:** creating a warning or join-filter log requires the guild's
  `guild_configs` row to exist first (`INSERT ... ON CONFLICT DO NOTHING`), as
  Python does.
- **`save_config()` semantics:** Python rewrites every guild row and every JSON
  blob on any change. The Go port must update one guild/one field at a time.
  Until cutover, avoid running both bots with write access; a Python save can
  clobber a concurrent Go change.
- **Sessions:** Python deletes all rows and re-inserts persistent sessions on
  save. Go should upsert dirty sessions and delete only removed ones. The
  serialised `root` tree must remain byte-compatible JSON (same field names).
- **Analytics:** one row per guild with `messages`, `churn`, `voice` JSON blobs.
  Keep the shape; change only the flush cadence. Do not switch to JSONB during
  the port.
- **Snowflake precision:** Discord IDs fit in int64 today. Use int64 rather than
  float64 anywhere IDs are stored (Python ints are arbitrary precision).

### 4.3 Schema ownership

The scaffold's `internal/store/migrations/0001_platform.sql` creates the same
tables with `IF NOT EXISTS`, so it is a no-op on a Python-created database. The
`BIGSERIAL` vs `SERIAL` difference for surrogate IDs is harmless (both scan into
`int64`; FKs compare fine). From M1 onward, new schema changes go through
numbered migrations only, never through `setup_schema`-style code.

---

## 5. Shared behaviour to port carefully

### 5.1 Automod

`normalize_text` does lowercasing, leetspeak translation, spacing, single-letter
merging, and whitespace condensation. Filters support plain text, `r:` regex,
wrapped wildcards, and `a:`/`a:r:` allow-list exceptions. Nicknames and joins
use the same matcher. Port this as a pure package with table-driven fixtures
before touching any Discord code.

**Regex portability is the biggest trap.** Python's `re` supports lookbehind,
lookahead, backreferences, and atomic groups; Go's `regexp` (RE2) does not. The
bot lets server admins store arbitrary `r:` patterns. Options:

1. Validate at input with `regexp.Compile`, reject unsupported syntax, and
   document the subset (recommended default).
2. Use `regexp2` for stored patterns with a `MatchTimeout` (e.g. 100ms) to
   retain Python-like syntax without ReDoS.
3. Keep a small PCRE2 cgo binding (rejected: loses the static binary).

Whichever is chosen, write a migration/report that scans existing
`automod_filters` and `join_filters` JSON for unsupported patterns before
cutover.

Other automod details to preserve:

- `LEET_MAP` and `HOMOGLYPH_MAP` are rune translations; use `strings.Map`.
- Regional-indicator emoji map 127462–127487 → `a`–`z`.
- `re.IGNORECASE` Unicode folding differs slightly from Go's `(?i)`; fixtures
  should include non-ASCII cases.
- Word-boundary and wildcard matching behaviour is hand-rolled; port the tests,
  not just the regex.

### 5.2 Warnings

- Points are summed statically or within a rolling window
  (`warning_escalation_mode`, `warning_rolling_window_days`).
- `warning_ladder` maps point totals to actions like `"10-minute timeout"`.
- `parse_moderation_action` accepts `ban`, `kick`, `timeout`, and durations in
  seconds/minutes/hours/days/weeks/months (month = 30 days).
- Warnings are linked to one or more platform accounts (`Discord`, `Twitch`,
  ...); the Discord target is resolved by ID or mention.
- Escalation must be idempotent. Python computes points, then executes an
  action; a retry must not double-timeout. Use a transaction and record
  `action_taken`.

### 5.3 Verification

- Codes are held in memory with a 5-minute expiry and support multiple platforms.
- The timeout kick is a `asyncio.sleep` task and is lost on restart. That is
  existing behaviour; preserve parity first. A later improvement can persist
  deadlines.
- Role hierarchy checks must happen before mutating roles; notify admins on
  failure.

### 5.4 Join filtering

- Age is evaluated in days or hours from `member.created_at`.
- Username checks use `member.name` and `member.display_name`, with optional
  emoji/homoglyph normalisation.
- List filters can be `r:` regex, wildcard-wrapped, or plain.
- Enforcement actions include quarantine (role), kick, and ban; logs go to
  `join_filtering_logs` and the configured log channel.

### 5.5 Plurality

- Proxy tags split on the literal word `text`: `[text]`, `m:text`, etc.
- A message matching a tag is re-sent as the member (identity, avatar) and
  recorded in `proxied_messages`; replying `edit`/`delete` to that message
  triggers the edit/delete flow.
- Avatar uploads are stored in a hidden avatars channel and referenced by
  message/channel IDs.
- Guard against loops: never proxy bot messages or proxied webhook messages.

### 5.6 Shell

- Virtual filesystem is an in-memory tree serialised into `sessions.root`.
- Editor is a state machine over messages (`:w`, `:q`, `:set`, `:d`, `:r`).
- Animated output edits one message with delays; rate-limit and stop on failure.
- `is_safe_url` blocks private/loopback/link-local addresses. In Go, validate at
  dial time inside a custom `http.Transport.DialContext` (DNS rebinding makes a
  pre-resolution check insufficient).

---

## 6. Cutover topology (important)

Two gateway clients **cannot reliably share one bot token**; running Python and
Go against the same application will cause duplicate sessions and command
registration fights. Choose one of these:

### Option A — staging application (recommended)

1. Create a second Discord application (`NEBOT-Go staging`) and token.
2. Invite it to a staging guild; copy the production database (or a subset).
3. Run Python as the production bot and Go in **shadow mode**: Go reads config,
   receives events, and logs what it *would* send/write, but sends no messages
   and writes no rows.
4. Compare command registries, event routing, and computed actions.
5. Cut over production by stopping Python and starting Go with the production
   token. Keep the Python image ready for rollback.

### Option B — single-token maintenance window

If a staging application is not possible, do a short cutover window:

1. Backup the database (`pg_dump`), stop Python.
2. Register Go commands (global registration can take time; use a dev guild
   during testing).
3. Start Go, verify core flows, keep logs open.
4. Roll back by stopping Go and starting Python. The schema is unchanged, so
   rollback is safe.

### Component compatibility

Old messages created by Python contain `custom_id`s owned by the Python views.
With the same application, clicks after cutover arrive at Go. Before cutover:

- Catalog explicit custom IDs (`verification_select`, `verification_gate:get_code`,
  `music_*`, `dash_*`, `bulk_*`, self-role IDs, etc.).
- Add compatibility routes for persistent/public controls that users will still
  click (verification gate, self-role menus, music player).
- Accept that old ephemeral dashboard messages can be abandoned; add a
  "this control expired, run /admin again" response and document it.

Run Python and Go against **separate databases** in staging; do not let shadow
Go write. Only the writer process may own config/analytics/session tables.

---

## 7. Testing strategy

Porting 5,900 lines of pytest literally is wasted effort. Extract behaviour
fixtures from the Python implementation and test the Go packages against them.

### 7.1 Fixture extraction (one-time, from Python)

For pure functions, write a throwaway Python script that imports the module and
dumps JSON vectors:

- `normalize_text`, `parse_keyword`, `check_text_against_keywords`,
  `parse_join_keyword`, emoji/homoglyph conversions.
- warning point totals, rolling-window cutoffs, `parse_moderation_action`.
- plurality proxy-tag matching and prefix/suffix splitting.
- `parse_nebuff` conversions, grok query classification, battle damage.
- shell path resolution, FS operations, editor commands.
- Python timestamp formatting and JSON serialisation of `sessions.root`.

Commit the fixtures under `internal/testdata/` and load them with `go test`.
This catches behavioural drift that a rewritten test would miss.

### 7.2 Test layers

| Layer | What | How |
|---|---|---|
| Unit | pure functions above | table-driven `testing`, fixtures |
| Store | schema, upserts, JSON round-trip, warning transactions | PostgreSQL container; run migrations; compare against Python-created row |
| Handler | command/component routing, permissions, error paths | fake `discordgo` REST? Prefer extracting pure decision functions; integration-test the rest against a dev guild |
| Contract | registered command names/options/descriptions | snapshot JSON from `ApplicationCommandBulkOverwrite`; diff against Python's tree |
| Shadow | real events, no writes/sends | staging application, structured diff logs |
| Load | join/leave, message bursts, component spam | synthetic events through handler functions; verify no data races (`go test -race`) |

### 7.3 CI gates

- `gofmt -l ./cmd ./internal` (fail on output)
- `go vet ./...`
- `go test -race ./...`
- `go build ./...`
- migration test against an empty PostgreSQL database
- optional: `golangci-lint`

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 173 UI classes take longer than expected | High | High | Build the UI kit in M1; port simple modules first; keep dashboards last; snapshot-test component JSON |
| Python regex patterns incompatible with RE2 | High | Medium | Validate at input; use `regexp2` with timeout for stored patterns; report incompatible patterns before cutover |
| Behaviour drift in automod normalisation | High | High | Fixture extraction; shadow diffs; port tests before UI |
| Plurality proxy loops / edit-delete bugs | Medium | High | Guard bot/webhook messages; table tests for tag parsing; staging guild |
| Lavalink adapter friction (string vs uint64 snowflakes) | Medium | Medium | Small adapter package; spike in M0/M6; fall back to a minimal Lavalink client |
| Two clients / one token during cutover | High if attempted | High | Use a staging application or a maintenance window (§6) |
| Config cache staleness / lost writes | Medium | High | Single writer, per-guild updates, `sync.RWMutex`, DB as source of truth |
| Timestamp/JSON format drift breaks Python reads | Medium | Medium | `pyjson` helpers with golden tests; keep TEXT columns |
| Privileged intents unavailable | Medium | Medium | Config flags for members/message-content intents; degrade gracefully like Python |
| Rate limits from animated shell edits | Low | Medium | Reuse one message, cap edit frequency, stop on 429 |
| Library maintenance (discordgo/disgolink) | Medium | Medium | Thin handler layer; module contract isolates library |

### Security notes

- `db_service.py` currently falls back to a hardcoded password (`Frog0101!`).
  The Go port requires explicit credentials; remove this from Python when
  decommissioning.
- Keep owner/admin/mod checks server-side in every dashboard handler. Do not
  rely on Discord's default command permissions.
- Validate `custom_id` payloads; never trust guild/user IDs from them.
- Keep the SSRF-safe HTTP client for shell network commands; check at dial time.
- Cap modal input lengths and regex match time.
- Do not log tokens, passwords, or full message content by default.

---

## 9. Deployment

Build:

```bash
go build -trimpath -o nebot ./cmd/nebot
```

Run (PostgreSQL example):

```bash
export DISCORD_TOKEN="..."
export DATABASE_URL="postgres://nebot:secret@127.0.0.1:5432/nebot?sslmode=disable"
export DISCORD_DEV_GUILD_ID="123456789012345678"   # optional, instant command sync
./nebot
```

The existing `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`,
`DATABASE_PASSWORD`, and `DATABASE_NAME` variables are still supported when
`DATABASE_URL` is absent. Lavalink variables are read and validated but unused
until M6.

Docker (multi-stage, distroless) is in the repo `Dockerfile`. A Go service can
run alongside Lavalink exactly like the Python container; the Go binary has no
Python, pip, or wheel dependencies.

---

## 10. Open questions for the owner

1. **PostgreSQL-only?** The plan drops the SQLite fallback to avoid dialect
   drift. Local development would use Docker Postgres. Confirm this is fine.
2. **Dashboard scope:** all ~60 admin/mod/owner views are the largest chunk.
   Should the first Go release ship slash commands + a reduced set of panels,
   with the rest following? Or is full parity required before cutover?
3. **Cutover style:** staging application (recommended) or single-token
   maintenance window?
4. **Hosting:** Docker Compose on one host, or systemd? Is sharding needed
   (likely not for personal/friend servers)?
5. **Music:** is LavaSrc already configured in production Lavalink, or does the
   Go port need the Spotify scraping fallback?
6. **Drop anything?** Any modules that are unused and should not be ported?
7. **Module path:** `github.com/nebuff/n-bot` is a placeholder; confirm the final
   import path.

---

## 11. Definition of done

The port is complete when:

- Every command and chat trigger in the Python bot has a Go equivalent.
- The Go bot can read and write the existing PostgreSQL schema without Python.
- Persistent components (self roles, verification) work after a restart.
- Automod/warning/join-filter decisions match fixtures for the stored configs.
- Music plays through Lavalink and player controls work after a restart.
- Plurality proxying, editing, deleting, and avatars work.
- A one-week shadow run shows no unexplained divergence.
- Rollback to the Python container is documented and has been rehearsed.
