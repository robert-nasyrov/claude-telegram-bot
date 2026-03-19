"""
Smart model routing — saves money by using Haiku for simple queries
and Sonnet for complex ones.
"""

import re

# Keywords that require Sonnet (complex tasks)
SONNET_TRIGGERS = {
    # Code & technical
    "код", "code", "python", "javascript", "react", "sql", "api", "баг", "bug",
    "ошибк", "error", "деплой", "deploy", "railway", "github", "vercel",
    "воркфлоу", "workflow", "n8n", "бот", "bot", "скрипт", "script",
    "функци", "function", "класс", "class", "база данн", "database",
    "postgresql", "docker", "webhook", "cron", "aiogram", "npm", "pip",
    # Business & strategy
    "стратег", "strateg", "бюджет", "budget", "финанс", "financ",
    "коммерческ", "commercial", "предложени", "proposal", "контракт",
    "договор", "клиент", "client", "спонсор", "sponsor",
    "план", "plan", "анализ", "analysis", "отчёт", "report",
    "оплат", "заплатил", "получил", "выручк", "доход", "money",
    "revenue", "payment", "$", "долл", "сум",
    "кп", "предложение", "proposal", "pdf", "коммерческ", "прайс",
    # Creative / long form
    "сценарий", "script", "напиши текст", "write", "статья", "article",
    "пост", "контент", "content",
    # n8n / infra management
    "нода", "node", "execution", "выполнен", "запусти", "activate",
    "деактив", "логи", "logs", "редеплой", "redeploy",
    # Explicit model requests
    "sonnet", "opus", "подробн", "детальн",
}

# Patterns that definitely need Sonnet
SONNET_PATTERNS = [
    r"```",              # code blocks
    r"https?://",        # URLs
    r"\d{3,}",           # long numbers (IDs, etc)
    r"[A-Za-z]{15,}",    # long technical words
]


def should_use_sonnet(text: str) -> bool:
    """
    Returns True if the message needs Sonnet, False if Haiku is enough.
    
    Haiku handles: greetings, simple questions, yes/no, short factual queries.
    Sonnet handles: code, strategy, n8n, devops, long-form, anything complex.
    """
    text_lower = text.lower().strip()
    
    # Very short messages (< 20 chars) — likely greetings or simple questions
    if len(text_lower) < 20 and not any(t in text_lower for t in SONNET_TRIGGERS):
        return False
    
    # Check trigger words
    for trigger in SONNET_TRIGGERS:
        if trigger in text_lower:
            return True
    
    # Check patterns
    for pattern in SONNET_PATTERNS:
        if re.search(pattern, text):
            return True
    
    # Long messages (> 200 chars) probably need Sonnet
    if len(text) > 200:
        return True
    
    # Has attachments? → Sonnet (Vision tasks)
    # (checked separately in claude_api.py)
    
    # Default: Haiku for everything else
    return False
