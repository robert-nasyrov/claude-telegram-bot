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

# === GitHub ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "CryptoKong999")

# === Railway ===
RAILWAY_TOKEN = os.getenv("RAILWAY_TOKEN", "")

# === Vercel ===
VERCEL_TOKEN = os.getenv("VERCEL_TOKEN", "")

# === Database ===
DATABASE_URL = os.getenv("DATABASE_URL")

# External databases (for live context sync)
DIGEST_DATABASE_URL = os.getenv("DIGEST_DATABASE_URL", "")   # telegram-digest
CRM_DATABASE_URL = os.getenv("CRM_DATABASE_URL", "")         # zbs-crm-bot
OPP_DATABASE_URL = os.getenv("OPP_DATABASE_URL", "")

# === Models available ===
MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}

# === Telegram formatting instructions (prepended to all prompts) ===
TG_FORMAT_RULES = (
    "CRITICAL FORMATTING RULES — you are responding in Telegram:\n"
    "- NEVER use markdown headers (##, ###). Use plain text or emoji as section markers.\n"
    "- NEVER use **bold** or *italic* markdown. Telegram uses HTML: <b>bold</b>, <i>italic</i>, <code>code</code>.\n"
    "- Keep responses SHORT. Max 3-5 short paragraphs. No walls of text.\n"
    "- Use plain lists with emoji (▸, →) instead of bullet points or numbered lists.\n"
    "- Get to the point immediately. No preamble, no 'Great question!'.\n"
    "- When showing data, use compact format. No verbose explanations.\n"
    "- Respond in the same language the user writes in.\n"
)

# Import Robert's full context
from context import ROBERT_CONTEXT

# === System prompts (projects) ===
SYSTEM_PROMPTS = {
    "default": (
        TG_FORMAT_RULES + ROBERT_CONTEXT +
        "\nBe concise and direct. You have access to n8n, GitHub, Railway, and Vercel tools."
    ),
    "code": (
        TG_FORMAT_RULES + ROBERT_CONTEXT +
        "\nFocus: senior software engineer mode. Write clean, production-ready code. "
        "Keep explanations minimal — code speaks for itself."
    ),
    "media": (
        TG_FORMAT_RULES + ROBERT_CONTEXT +
        "\nFocus: креативный директор ZBS Media. "
        "Помогай с контент-стратегией, сценариями, идеями. Будь конкретен и краток."
    ),
    "business": (
        TG_FORMAT_RULES + ROBERT_CONTEXT +
        "\nFocus: бизнес-стратег. "
        "Давай конкретные цифры и рекомендации, а не общие слова. Коротко."
    ),
    "writer": (
        TG_FORMAT_RULES + ROBERT_CONTEXT +
        "\nFocus: professional writer and editor. "
        "Match the tone and style requested. Be creative and engaging."
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
