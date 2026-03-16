import json
import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Date, Float,
    Boolean, ForeignKey, create_engine, select, func, desc
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

import config

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    title = Column(String(255), default="New Chat")
    system_prompt_key = Column(String(50), default="default")
    model = Column(String(100), default=config.DEFAULT_MODEL)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    # For multimodal: store metadata about images/docs
    attachments = Column(Text, default=None)  # JSON: [{"type": "image", "media_type": "image/jpeg"}]
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class UsageLog(Base):
    __tablename__ = "ai_usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    date = Column(Date, default=date.today, index=True)
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


# --- Engine & Session ---

def get_async_engine():
    url = config.DATABASE_URL
    if not url:
        raise ValueError("DATABASE_URL not set")
    # Convert postgres:// to postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url, echo=False, pool_size=5, max_overflow=10)


engine = None
SessionLocal = None


async def init_db():
    global engine, SessionLocal
    engine = get_async_engine()
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def get_session() -> AsyncSession:
    return SessionLocal()


# --- Conversation CRUD ---

async def get_or_create_conversation(
    user_id: int,
    system_prompt_key: str = "default",
    model: str = None
) -> Conversation:
    """Get active conversation or create new one."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.is_active == True)
            .order_by(desc(Conversation.updated_at))
            .limit(1)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

        conv = Conversation(
            user_id=user_id,
            system_prompt_key=system_prompt_key,
            model=model or config.DEFAULT_MODEL,
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv


async def new_conversation(
    user_id: int,
    system_prompt_key: str = "default",
    model: str = None
) -> Conversation:
    """Archive current and create new conversation."""
    async with SessionLocal() as session:
        # Deactivate all active conversations
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.is_active == True)
        )
        for conv in result.scalars():
            conv.is_active = False

        new_conv = Conversation(
            user_id=user_id,
            system_prompt_key=system_prompt_key,
            model=model or config.DEFAULT_MODEL,
        )
        session.add(new_conv)
        await session.commit()
        await session.refresh(new_conv)
        return new_conv


async def update_conversation(conv_id: int, **kwargs):
    async with SessionLocal() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            for k, v in kwargs.items():
                setattr(conv, k, v)
            conv.updated_at = datetime.utcnow()
            await session.commit()


async def save_message(
    conversation_id: int,
    role: str,
    content: str,
    attachments: list = None,
    input_tokens: int = 0,
    output_tokens: int = 0
) -> Message:
    async with SessionLocal() as session:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            attachments=json.dumps(attachments) if attachments else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        session.add(msg)

        # Update conversation timestamp
        result = await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.updated_at = datetime.utcnow()

        await session.commit()
        return msg


async def get_conversation_messages(conversation_id: int) -> list[Message]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars())


async def get_conversation_list(user_id: int, limit: int = 20) -> list[Conversation]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
        )
        return list(result.scalars())


# --- Usage tracking ---

async def log_usage(user_id: int, model: str, input_tokens: int, output_tokens: int):
    cost_info = config.COSTS.get(model, {"input": 3.0, "output": 15.0})
    cost = (input_tokens * cost_info["input"] + output_tokens * cost_info["output"]) / 1_000_000

    async with SessionLocal() as session:
        log = UsageLog(
            user_id=user_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        session.add(log)
        await session.commit()


async def get_usage_stats(user_id: int, days: int = 30) -> dict:
    async with SessionLocal() as session:
        from datetime import timedelta
        since = date.today() - timedelta(days=days)

        result = await session.execute(
            select(
                func.sum(UsageLog.input_tokens),
                func.sum(UsageLog.output_tokens),
                func.sum(UsageLog.cost_usd),
                func.count(UsageLog.id),
            )
            .where(UsageLog.user_id == user_id, UsageLog.date >= since)
        )
        row = result.one()

        # Today's stats
        today_result = await session.execute(
            select(
                func.sum(UsageLog.input_tokens),
                func.sum(UsageLog.output_tokens),
                func.sum(UsageLog.cost_usd),
            )
            .where(UsageLog.user_id == user_id, UsageLog.date == date.today())
        )
        today = today_result.one()

        return {
            "period_days": days,
            "total_input_tokens": row[0] or 0,
            "total_output_tokens": row[1] or 0,
            "total_cost": round(row[2] or 0, 4),
            "total_requests": row[3] or 0,
            "today_input_tokens": today[0] or 0,
            "today_output_tokens": today[1] or 0,
            "today_cost": round(today[2] or 0, 4),
        }
