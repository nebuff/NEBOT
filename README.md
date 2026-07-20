# NEBOT

## Prerequisite Baselines

1. **Operating System:** Linux (Debian/Ubuntu recommended) or macOS
2. **Execution Environment:** Docker Engine and Docker Compose (recommended) or Python 3.11+ natively
3. **Lavalink Server:** A valid, accessible Lavalink node (v4) is required for music modules
4. **Database:** PostgreSQL server for persistent platform data storage

## Core Built-in Features

- **AutoMod System:** Advanced regular expression, keyword filtering, and nickname sanitization
- **Role Management:** Auto-roller execution and self-assignable role views
- **Verification Gate:** Timed challenge verification system to prevent unauthorized access
- **Moderation Tracker:** Warning ladders, execution logging, and automated strict moderation actions
- **Music Engine:** Full Lavalink v4 integration (Wavelink) for high-fidelity audio playback
- **Plurality Support:** Native message proxying and system management for plural systems
- **Interactive Modules:** Battle system, Minesweeper, and automated voice channel renaming
- **Analytics:** In-depth server velocity tracking, join filtering, and persistent session logging

## Installation Sequence

The most stable deployment method is via Docker Compose, utilizing the official Python 3.11 slim image.

Clone the repository and spin up the container network:

```bash
git clone https://github.com/nebuff/N-BOT.git
cd N-BOT
docker compose up -d
```

## System Configuration

The engine relies on structural environment variables to resolve its target architectures, database connections, and upstream APIs. You can inject these directly into a `docker-compose.yml` file.

Example configuration architecture:

```yaml
version: '3.8'
services:
  nebot:
    container_name: nebot
    image: python:3.11-slim
    command:
      - sh
      - '-c'
      - pip install --no-cache-dir discord.py wavelink psycopg2-binary && python /app/main_entrypoint.py
    environment:
      - DISCORD_TOKEN=your_discord_bot_token_here
      - OWNER_ID=your_discord_user_id
      - LAVALINK_HOST=127.0.0.1
      - LAVALINK_PORT=2333
      - LAVALINK_PASSWORD=youshallnotpass
      - DATABASE_HOST=127.0.0.1
      - DATABASE_PORT=5432
      - DATABASE_USER=nebot_user
      - DATABASE_PASSWORD=secure_password
      - DATABASE_NAME=nebot_db
      - SPOTIFY_CLIENT_ID=optional_spotify_client_id
      - SPOTIFY_CLIENT_SECRET=optional_spotify_client_secret
      - PYTHONUNBUFFERED=1
    volumes:
      - ./SRC:/app
      - ./DATA:/DATA
    working_dir: /app
    restart: unless-stopped
```

## Dashboard and Usage Examples

Once deployed, NEBOT provides interactive administration directly within the Discord environment.

Execute the primary administration dashboard resolution:
```
/admin
```
*Note: This command generates a secure UI to configure modules, modify thresholds, and manage system states.*

Execute a moderation tracking penalty:
```
/mod warn @user "Rule violation"
```

*Note: Execution will yield formatted application output traces within your designated logging channels for strict operational tracking.*
