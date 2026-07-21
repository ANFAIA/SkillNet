"""Tool definitions and executors for the SkillNet A2A orchestrator."""

import json
from typing import Any

from src.skillnet_client import SkillNetClient

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "who_knows",
            "description": "Find employees who have a specific skill. Returns a list of employees with their proficiency level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "The skill name to search for (e.g., 'Python', 'atencion_cliente', 'sushi')",
                    },
                    "min_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Minimum proficiency level to filter by. Optional.",
                    },
                },
                "required": ["skill"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gap",
            "description": "Analyze skill gaps across the organization. Shows which skills have low coverage and need attention.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_skill",
            "description": "Record or update an employee's skill level. Use this to confirm that an employee has demonstrated a skill at a certain level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the employee",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "The skill to verify",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "The proficiency level",
                    },
                    "source": {
                        "type": "string",
                        "description": "How the skill was verified (e.g., 'manual', 'checkpoint', 'external_assessment')",
                        "default": "manual",
                    },
                },
                "required": ["user_id", "skill_name", "level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List all skills in the organization's taxonomy, grouped by category.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_skills",
            "description": "Get the complete skill profile of a specific employee.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The UUID of the employee",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
]


async def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool call and return the result as a JSON string."""
    client = SkillNetClient()

    if name == "who_knows":
        result = await client.who_knows(
            skill=arguments["skill"],
            min_level=arguments.get("min_level"),
        )
    elif name == "get_gap":
        result = await client.get_gap()
    elif name == "verify_skill":
        result = await client.verify_skill(
            user_id=arguments["user_id"],
            skill_name=arguments["skill_name"],
            level=arguments["level"],
            source=arguments.get("source", "manual"),
        )
    elif name == "list_skills":
        result = await client.list_skills()
    elif name == "get_user_skills":
        result = await client.get_user_skills(user_id=arguments["user_id"])
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, ensure_ascii=False)
