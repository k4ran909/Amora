# Spark: Telegram + Discord dating bot

Face-checked dating profiles with admin review. Full design: [docs/PLAN.md](docs/PLAN.md).

**Built so far (phases 0–1, plus the core of phase 2):**
- Telegram onboarding with buttons: terms, 18+ gate, gender, preferences, name, location, bio, interests, photos, preview, submit. It resumes where the user left off.
- Face checks on every photo (OpenCV YuNet + SFace):
  - the main photo must show exactly one clear, frontal, sharp face
  - extra photos must contain the same person
  - photos already used on another profile are rejected
  - EXIF/GPS metadata is stripped
- Face fingerprints are encrypted at rest (Fernet).
- Storage: a private Telegram vault channel (photos + profile JSON), or `data/vault/` locally.
- Admin: an owner set via `.env`, `/admin` panel, review cards with Approve / Reject (with reasons) / Block underage, stats, and an audit log.
- My Profile: view, all photos, edit, pause/resume, delete account (GDPR).
- Discord bot online with `/dating` and `/admin` (the full flow comes in phase 3).

## Run locally

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
.venv/Scripts/python.exe scripts/download_models.py
.venv/Scripts/python.exe scripts/init_env.py
# edit .env: TELEGRAM_BOT_TOKEN, OWNER_TG_IDS (and optionally the Discord settings)
.venv/Scripts/python.exe -m spark
```

## Telegram setup
1. Create the bot with **@BotFather** and put the token in `TELEGRAM_BOT_TOKEN`.
2. Get your numeric ID from **@userinfobot** and put it in `OWNER_TG_IDS`. Then send `/start` to your bot once, so it can DM you review cards.
3. *(Recommended)* Create a **private channel**, add the bot as admin, and put its ID (`-100…`) in `TG_VAULT_CHANNEL_ID`. All photos and profile backups live there.
4. *(Optional)* Create a **private admin group**, add the bot, and put its ID in `TG_ADMIN_CHAT_ID`. Review cards then go there instead of your DMs.

## Discord setup
Create an app at https://discord.com/developers/applications, add a bot, and copy the token into `DISCORD_BOT_TOKEN`. Invite the bot with the `bot` + `applications.commands` scopes. Set `DISCORD_GUILD_ID` so slash commands appear instantly, and set `OWNER_DC_IDS` to your user ID.

## Production (VPS)
```bash
docker compose up -d --build
```
This runs the bot with Postgres + Redis. Onboarding progress survives restarts via Redis.

## Tests
```bash
.venv/Scripts/python.exe -m pytest -q
```
The face tests download OpenCV's own sample images into `tests/.cache/` on first run.

## Layout
```
spark/core/        platform-independent logic (profiles, face checks, validation, admin roles, vault)
spark/db/          SQLAlchemy models
spark/adapters/    telegram/ (aiogram 3) and discord/ (discord.py 2)
scripts/           model download + .env bootstrap
```
