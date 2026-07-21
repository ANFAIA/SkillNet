"""AgentCard definition for the SkillNet A2A server."""

from src.config import settings

AGENT_CARD = {
    "name": "SkillNet",
    "description": (
        "AI-native training platform agent. Query employee skills, "
        "find experts, analyze skill gaps, and verify learning achievements."
    ),
    "url": settings.A2A_AGENT_URL,
    "version": "0.1.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
    },
    "skills": [
        {
            "id": "who_knows",
            "name": "Find who knows a skill",
            "description": "Find employees who have a specific skill at a given proficiency level",
            "examples": [
                "Who knows Python?",
                "Find employees skilled in customer service at high level",
            ],
        },
        {
            "id": "get_gap",
            "name": "Analyze skill gaps",
            "description": "Identify skills with low coverage across the organization",
            "examples": [
                "What are our biggest skill gaps?",
                "Which skills need more training?",
            ],
        },
        {
            "id": "verify_skill",
            "name": "Verify employee skill",
            "description": "Record or confirm an employee's proficiency in a skill",
            "examples": [
                "Confirm Maria knows food safety at medium level",
                "Record that Juan has completed Python training",
            ],
        },
        {
            "id": "list_skills",
            "name": "List skill taxonomy",
            "description": "Show all skills organized by category",
            "examples": ["What skills do we track?", "Show me the skill categories"],
        },
        {
            "id": "get_user_skills",
            "name": "Get employee skills",
            "description": "Get the complete skill profile of an employee",
            "examples": [
                "What skills does Maria have?",
                "Show Juan's skill profile",
            ],
        },
    ],
    "authentication": {
        "schemes": ["bearer"],
    },
}
