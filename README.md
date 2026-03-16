# Claude Telegram Bot

Personal Claude AI assistant in Telegram with full context, Vision, web search, and voice support.

## Features

- 💬 **Full conversation context** — stored in PostgreSQL, smart truncation
- 🖼️ **Vision** — send photos and PDFs, Claude analyzes them
- 🔍 **Web search** — Claude can search the web via tool use
- 🎤 **Voice messages** — transcribed via Whisper, then processed by Claude
- 📂 **Text files** — send .py, .json, .md etc. for analysis
- 🔄 **Model switching** — sonnet/opus/haiku on the fly
- 📊 **Usage tracking** — cost per day/month
- 🗂️ **Projects** — switchable system prompts (code, media, business, etc.)

## Commands

| Command | Description |
|---------|------------|
| `/new` | Start new conversation |
| `/model [name]` | Switch model (sonnet/opus/haiku) |
| `/project [name]` | Switch system prompt |
| `/history` | List recent conversations |
| `/usage` | Cost and token stats |
| `/status` | Current settings |
| `/search on\|off` | Toggle web search |
| `/help` | Show commands |

## Deploy to Railway

1. Create new project on Railway
2. Add PostgreSQL plugin
3. Connect GitHub repo
4. Set environment variables:
   - `BOT_TOKEN` — from @BotFather
   - `OWNER_ID` — your Telegram user ID (271065518)
   - `ANTHROPIC_API_KEY` — Claude API key
   - `OPENAI_API_KEY` — for voice transcription (optional)
   - `DATABASE_URL` — auto-set by Railway PostgreSQL plugin

## Cost Estimate

| Model | Input (per 1M) | Output (per 1M) | ~50 msgs/day |
|-------|----------------|-----------------|--------------|
| Sonnet | $3 | $15 | ~$15-25/mo |
| Opus | $15 | $75 | ~$75-150/mo |
| Haiku | $0.80 | $4 | ~$5-10/mo |
