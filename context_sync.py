"""
Auto-context sync — pulls data from all Railway PostgreSQL databases
and compresses into a compact context summary.

Runs daily via cron. Stores summary in bot's own DB.
Cost: ~0 tokens extra per sync, ~2000-4000 tokens added to system prompt.
"""

import json
import logging
from datetime import datetime, timedelta

import asyncpg

import config

logger = logging.getLogger(__name__)


async def _safe_query(db_url: str, query: str, label: str) -> list:
    """Run query against a remote database, return rows or empty list."""
    if not db_url:
        return []
    try:
        conn = await asyncpg.connect(db_url, timeout=10)
        rows = await conn.fetch(query)
        await conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Context sync [{label}]: {e}")
        return []


async def sync_digest_context() -> str:
    """Pull latest from telegram-digest DB."""
    url = config.DIGEST_DATABASE_URL
    if not url:
        return ""

    # Last 3 daily summaries
    rows = await _safe_query(url, """
        SELECT plan_date, summary 
        FROM daily_summaries 
        ORDER BY plan_date DESC LIMIT 3
    """, "digest-summaries")

    # Open items
    items = await _safe_query(url, """
        SELECT item, status, source 
        FROM open_items 
        WHERE status != 'done'
        ORDER BY created_at DESC LIMIT 10
    """, "digest-items")

    parts = []
    if rows:
        latest = rows[0]
        summary = str(latest.get("summary", ""))[:500]
        parts.append(f"Последний дайджест ({latest.get('plan_date', '?')}): {summary}")
    if items:
        item_list = "; ".join(f"{i['item'][:60]} [{i.get('status','?')}]" for i in items[:5])
        parts.append(f"Открытые задачи: {item_list}")

    return "\n".join(parts)


async def sync_crm_context() -> str:
    """Pull latest from ZBS CRM bot DB."""
    url = config.CRM_DATABASE_URL
    if not url:
        return ""

    # Upcoming tasks/events
    tasks = await _safe_query(url, """
        SELECT title, deadline, status, assigned_to
        FROM tasks
        WHERE status NOT IN ('DONE', 'CANCELLED')
        ORDER BY deadline ASC NULLS LAST
        LIMIT 10
    """, "crm-tasks")

    # Recent finance entries
    finance = await _safe_query(url, """
        SELECT description, amount, currency, created_at
        FROM finance_entries
        ORDER BY created_at DESC LIMIT 5
    """, "crm-finance")

    parts = []
    if tasks:
        task_list = "; ".join(
            f"{t['title'][:40]} → {t.get('assigned_to', '?')} [{t.get('status', '?')}]"
            for t in tasks[:7]
        )
        parts.append(f"Задачи CRM: {task_list}")
    if finance:
        fin_list = "; ".join(
            f"{f['description'][:30]}: {f.get('amount', '?')} {f.get('currency', '')}"
            for f in finance[:3]
        )
        parts.append(f"Последние финансы: {fin_list}")

    return "\n".join(parts)


async def sync_opportunities_context() -> str:
    """Pull latest from revenue-scanner DB."""
    url = config.OPP_DATABASE_URL
    if not url:
        return ""

    # Top opportunities
    opps = await _safe_query(url, """
        SELECT title, client, revenue_low, revenue_high, confidence, priority, status
        FROM opportunities
        WHERE status NOT IN ('rejected', 'done')
        ORDER BY priority ASC, confidence DESC
        LIMIT 10
    """, "opp-top")

    # Today's plan
    plan = await _safe_query(url, """
        SELECT plan_text, opportunity_ids
        FROM daily_plans
        ORDER BY plan_date DESC LIMIT 1
    """, "opp-plan")

    parts = []
    if opps:
        opp_list = "; ".join(
            f"{o['title'][:40]} ({o.get('client', '?')}) ${o.get('revenue_low', '?')}-{o.get('revenue_high', '?')} [{o.get('status', '?')}]"
            for o in opps[:5]
        )
        parts.append(f"Топ возможности: {opp_list}")
    if plan:
        plan_text = str(plan[0].get("plan_text", ""))[:300]
        parts.append(f"Сегодняшний план: {plan_text}")

    return "\n".join(parts)


async def build_live_context() -> str:
    """
    Build full live context from all databases.
    Called on bot startup and daily via cron.
    Returns compact text to append to system prompt.
    """
    sections = []

    digest = await sync_digest_context()
    if digest:
        sections.append(f"═══ ДАЙДЖЕСТ ═══\n{digest}")

    crm = await sync_crm_context()
    if crm:
        sections.append(f"═══ CRM ═══\n{crm}")

    opps = await sync_opportunities_context()
    if opps:
        sections.append(f"═══ ВОЗМОЖНОСТИ ═══\n{opps}")

    if not sections:
        return ""

    header = f"\n═══ LIVE DATA (обновлено {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC) ═══\n"
    return header + "\n".join(sections)


# ──── Storage in bot's own DB ────

async def save_live_context(context: str):
    """Save live context to bot's own database."""
    if not config.DATABASE_URL:
        return

    url = config.DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    try:
        conn = await asyncpg.connect(url, timeout=10)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS live_context (
                id INTEGER PRIMARY KEY DEFAULT 1,
                context TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            INSERT INTO live_context (id, context, updated_at) 
            VALUES (1, $1, NOW())
            ON CONFLICT (id) DO UPDATE SET context = $1, updated_at = NOW()
        """, context)
        await conn.close()
        logger.info(f"Live context saved ({len(context)} chars)")
    except Exception as e:
        logger.error(f"Failed to save live context: {e}")


async def load_live_context() -> str:
    """Load last saved live context."""
    if not config.DATABASE_URL:
        return ""

    url = config.DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    try:
        conn = await asyncpg.connect(url, timeout=10)
        row = await conn.fetchrow("SELECT context FROM live_context WHERE id = 1")
        await conn.close()
        return row["context"] if row else ""
    except Exception:
        return ""


async def run_sync():
    """Run full sync — call from cron or startup."""
    logger.info("Starting live context sync...")
    context = await build_live_context()
    if context:
        await save_live_context(context)
        logger.info(f"Live context synced: {len(context)} chars")
    else:
        logger.info("No live data found from any database")
    return context
