import json
import logging
from typing import Optional

import anthropic

import config
import database as db

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed ru/en."""
    return len(text) // 3


def build_messages_for_api(
    messages: list[db.Message],
    max_tokens: int = None
) -> list[dict]:
    """
    Build API messages list from DB messages.
    Truncate old messages if context window is exceeded.
    Always keep the first message (for context) and recent messages.
    """
    max_tokens = max_tokens or config.MAX_CONTEXT_TOKENS
    api_messages = []

    for msg in messages:
        content = msg.content
        attachments = json.loads(msg.attachments) if msg.attachments else None

        if attachments and msg.role == "user":
            # Multimodal message — rebuild content blocks
            blocks = []
            for att in attachments:
                if att["type"] == "image":
                    blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": att["media_type"],
                            "data": att.get("data", ""),
                        }
                    })
                elif att["type"] == "document":
                    blocks.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": att["media_type"],
                            "data": att.get("data", ""),
                        }
                    })
            if content:
                blocks.append({"type": "text", "text": content})
            api_messages.append({"role": "user", "content": blocks})
        else:
            api_messages.append({"role": msg.role, "content": content})

    # Truncate from the beginning if too long (keep last N messages)
    total_est = sum(
        estimate_tokens(m["content"] if isinstance(m["content"], str) else json.dumps(m["content"]))
        for m in api_messages
    )

    while total_est > max_tokens and len(api_messages) > 2:
        removed = api_messages.pop(0)
        # If we removed a user message and now starts with assistant, remove that too
        if api_messages and api_messages[0]["role"] == "assistant":
            api_messages.pop(0)
        total_est = sum(
            estimate_tokens(m["content"] if isinstance(m["content"], str) else json.dumps(m["content"]))
            for m in api_messages
        )

    return api_messages


def get_tools(enable_web_search: bool = True, enable_n8n: bool = True) -> list[dict]:
    """Build tools list based on what's enabled."""
    tools = []
    if enable_web_search:
        tools.append({
            "type": "web_search_20250305",
            "name": "web_search",
        })
    if enable_n8n and config.N8N_API_URL and config.N8N_API_KEY:
        from n8n_tools import N8N_TOOLS
        tools.extend(N8N_TOOLS)
    return tools


async def _execute_tool_call(tool_name: str, tool_input: dict) -> str:
    """Route tool call to the right executor."""
    if tool_name.startswith("n8n_"):
        from n8n_tools import execute_tool
        return await execute_tool(tool_name, tool_input)
    return json.dumps({"error": f"Unknown tool: {tool_name}"})


async def chat(
    conversation: db.Conversation,
    user_message: str,
    attachments: list = None,
    enable_web_search: bool = True,
    status_callback=None,
) -> tuple[str, int, int]:
    """
    Send message to Claude API and get response.
    Supports tool use loop — Claude can call n8n/web tools multiple times.
    status_callback: async function(str) to send status updates to user.
    Returns: (response_text, input_tokens, output_tokens)
    """
    # Save user message to DB
    attachment_meta = None
    if attachments:
        attachment_meta = [
            {"type": a["type"], "media_type": a["media_type"], "data": a.get("data", "")}
            for a in attachments
        ]

    await db.save_message(
        conversation_id=conversation.id,
        role="user",
        content=user_message,
        attachments=attachment_meta,
    )

    # Build context from history
    history = await db.get_conversation_messages(conversation.id)
    api_messages = build_messages_for_api(history)

    # System prompt
    system_prompt = config.SYSTEM_PROMPTS.get(
        conversation.system_prompt_key,
        config.SYSTEM_PROMPTS["default"]
    )

    # Tools
    tools = get_tools(enable_web_search=enable_web_search)

    total_input_tokens = 0
    total_output_tokens = 0
    max_tool_loops = 10  # Safety limit

    try:
        for loop_i in range(max_tool_loops):
            kwargs = {
                "model": conversation.model,
                "max_tokens": config.MAX_OUTPUT_TOKENS,
                "system": system_prompt,
                "messages": api_messages,
            }
            if tools:
                kwargs["tools"] = tools

            response = client.messages.create(**kwargs)
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Check if Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Build assistant message with all content blocks
                assistant_content = []
                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({
                            "type": "text",
                            "text": block.text,
                        })
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

                # Add assistant message to conversation
                api_messages.append({
                    "role": "assistant",
                    "content": assistant_content,
                })

                # Execute each tool call and collect results
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info(f"Tool call: {block.name}({json.dumps(block.input, ensure_ascii=False)[:200]})")

                        # Send status update if callback provided
                        if status_callback and block.name.startswith("n8n_"):
                            tool_label = block.name.replace("n8n_", "").replace("_", " ")
                            await status_callback(f"⚙️ n8n: {tool_label}...")

                        result = await _execute_tool_call(block.name, block.input)

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                # Add tool results as user message
                api_messages.append({
                    "role": "user",
                    "content": tool_results,
                })

                # Continue loop — Claude will process tool results
                continue

            else:
                # No more tool calls — extract final text response
                text_parts = []
                for block in response.content:
                    if block.type == "text":
                        text_parts.append(block.text)

                response_text = "\n".join(text_parts) or "(empty response)"

                # Save assistant message
                await db.save_message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=response_text,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )

                # Log usage
                await db.log_usage(
                    user_id=conversation.user_id,
                    model=conversation.model,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )

                return response_text, total_input_tokens, total_output_tokens

        # If we hit max loops, return what we have
        return "(Tool loop limit reached)", total_input_tokens, total_output_tokens

    except anthropic.APIError as e:
        logger.error(f"Claude API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Transcribe voice using OpenAI Whisper API."""
    import httpx

    if not config.OPENAI_API_KEY:
        return "[Voice transcription unavailable — OPENAI_API_KEY not set]"

    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            files={"file": (filename, audio_bytes, "audio/ogg")},
            data={"model": "whisper-1"},
        )

    if response.status_code == 200:
        return response.json().get("text", "")
    else:
        logger.error(f"Whisper API error: {response.status_code} {response.text}")
        return f"[Transcription error: {response.status_code}]"
