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
            "name": "create_course",
            "description": (
                "Create a full training course end to end in ONE call: propose the "
                "schema, generate the knowledge packs (with automatic retry), review "
                "every node, and validate it so it is immediately servable. Optionally "
                "grounds on an uploaded document, enrols an employee, and generates "
                "media artefacts. Returns the course id, per-node pack status, and "
                "whether it validated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The course title / topic to build (e.g. 'Food safety basics').",
                    },
                    "document_id": {
                        "type": "string",
                        "description": "Optional UUID of a ready document to ground the course on.",
                    },
                    "intent_density": {
                        "type": "integer",
                        "description": "How dense the course should be, 1 (light) to 5 (deep). Default 3.",
                    },
                    "enroll_user_id": {
                        "type": "string",
                        "description": "Optional UUID of an employee to enrol once the course is validated.",
                    },
                    "generate_artifacts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional media kinds to generate for the first nodes, e.g. ['podcast', 'infographic'].",
                    },
                },
                "required": ["title"],
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
    elif name == "create_course":
        result = await client.create_course(
            title=arguments["title"],
            document_id=arguments.get("document_id"),
            intent_density=arguments.get("intent_density", 3),
            enroll_user_id=arguments.get("enroll_user_id"),
            generate_artifacts=arguments.get("generate_artifacts"),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, ensure_ascii=False)
