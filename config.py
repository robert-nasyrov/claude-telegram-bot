import os

# === Telegram ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "271065518"))  # @nasyrov_robert

# === Claude API ===
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "180000"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "8192"))

# === OpenAI (for Whisper STT) ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# === n8n ===
N8N_API_URL = os.getenv("N8N_API_URL", "")  # e.g. https://xxx.app.n8n.cloud
N8N_API_KEY = os.getenv("N8N_API_KEY", "")

# === Database ===
DATABASE_URL = os.getenv("DATABASE_URL")

# === Models available ===
MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}

# === System prompts (projects) ===
SYSTEM_PROMPTS = {
    "default": (
        "You are Claude, a helpful AI assistant. Respond in the same language "
        "the user writes in. Be concise but thorough."
    ),
    "code": (
        "You are a senior software engineer. Write clean, production-ready code. "
        "Use best practices. Respond in the same language the user writes in. "
        "When writing code, always specify the language and provide brief explanations."
    ),
    "media": (
        "Ты — креативный директор медиа-компании ZBS Media в Ташкенте. "
        "Помогаешь с контент-стратегией, сценариями, идеями для подкастов, "
        "новостных выпусков, коммерческих предложений. Будь конкретен и креативен."
    ),
    "business": (
        "Ты — бизнес-консультант и стратег. Помогаешь с финансовым планированием, "
        "коммерческими предложениями, переговорами, анализом рынка. "
        "Давай конкретные цифры и рекомендации, а не общие слова."
    ),
    "writer": (
        "You are a professional writer and editor. Help with copywriting, "
        "scripts, social media posts, articles. Match the tone and style "
        "requested. Be creative and engaging."
    ),
}

# === Telegram message limit ===
TG_MSG_LIMIT = 4096

# === Cost per 1M tokens (USD) ===
COSTS = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
}
