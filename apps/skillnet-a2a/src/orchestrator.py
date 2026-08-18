"""LLM orchestrator: interprets natural language, calls tools, returns answers."""

import json
import logging

import litellm

from src.config import settings
from src.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are SkillNet's agent — an AI training platform for companies.
You help external agents and systems query employee skills, identify skill gaps,
and verify learning achievements.

You have access to the following capabilities:
- Find who knows a specific skill (who_knows)
- Analyze skill gaps across the organization (get_gap)
- Verify/record an employee's skill level (verify_skill)
- List the skill taxonomy (list_skills)
- Get an employee's skill profile (get_user_skills)
- Create a full training course end to end in one call (create_course)

Always respond in the same language as the user's message.
Be concise and structured in your responses.
If you cannot fulfill a request with the available tools, explain what you can do instead.
"""

MAX_TOOL_ROUNDS = 5


async def run(message: str) -> str:
    """Process a natural language message and return a response.

    Uses a tool-calling loop: the LLM decides which tools to call,
    we execute them and feed results back, until the LLM produces
    a final text response.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    for _round in range(MAX_TOOL_ROUNDS):
        response = await litellm.acompletion(
            model=settings.LLM_MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            api_key=settings.LLM_API_KEY,
            api_base=settings.LLM_BASE_URL if settings.LLM_BASE_URL else None,
            temperature=0.1,
        )

        choice = response.choices[0]

        # If no tool calls, we have the final answer
        if not choice.message.tool_calls:
            return choice.message.content or ""

        # Process tool calls
        messages.append(choice.message.model_dump())

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            logger.info("Tool call: %s(%s)", fn_name, fn_args)

            try:
                result = await execute_tool(fn_name, fn_args)
            except Exception as exc:
                logger.error("Tool %s failed: %s", fn_name, exc)
                result = json.dumps({"error": str(exc)})

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    # Safety: if we exhaust rounds, return what we have
    return "I was unable to complete the request within the allowed number of steps."
