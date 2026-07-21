#!/usr/bin/env python3
"""Demo script: send natural-language tasks to the SkillNet A2A server.

Usage:
    python scripts/test_a2a.py [--url http://localhost:5000] [--auth-key KEY]

Requires: httpx (pip install httpx)
"""

import argparse
import asyncio
import json
import sys

import httpx


async def send_message(url: str, text: str, auth_key: str = "") -> dict:
    """Send a message to the A2A server and return the response."""
    headers = {}
    if auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"

    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": text}],
            },
        },
        "id": 1,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def get_agent_card(url: str) -> dict:
    """Fetch the AgentCard."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{url}/.well-known/agent.json")
        resp.raise_for_status()
        return resp.json()


def extract_text(response: dict) -> str:
    """Extract the text response from an A2A result."""
    result = response.get("result", {})
    artifacts = result.get("artifacts", [])
    if not artifacts:
        error = response.get("error", {})
        return f"ERROR: {error.get('message', 'Unknown error')}"
    parts = artifacts[0].get("parts", [])
    return parts[0].get("text", "") if parts else "(empty response)"


TEST_MESSAGES = [
    "What skills do we track in our organization?",
    "Who knows Python in the team?",
    "What are our biggest skill gaps?",
    "What skills does the first employee have?",
]


async def main(url: str, auth_key: str) -> None:
    print(f"\n{'='*60}")
    print(f"  SkillNet A2A Demo — {url}")
    print(f"{'='*60}\n")

    # 1. Fetch AgentCard
    print("[1] Fetching AgentCard...")
    try:
        card = await get_agent_card(url)
        print(f"    Agent: {card.get('name', '?')}")
        print(f"    Description: {card.get('description', '?')}")
        skills = card.get("skills", [])
        print(f"    Skills: {', '.join(s.get('id', '?') for s in skills)}")
        print()
    except Exception as e:
        print(f"    FAILED: {e}\n")
        return

    # 2. Send test messages
    for i, msg in enumerate(TEST_MESSAGES, start=2):
        print(f"[{i}] User: {msg}")
        try:
            response = await send_message(url, msg, auth_key)
            answer = extract_text(response)
            print(f"    Agent: {answer[:500]}")
        except Exception as e:
            print(f"    FAILED: {e}")
        print()

    print(f"{'='*60}")
    print("  Demo complete.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the SkillNet A2A server")
    parser.add_argument("--url", default="http://localhost:5000", help="A2A server URL")
    parser.add_argument("--auth-key", default="", help="Bearer auth key")
    args = parser.parse_args()

    asyncio.run(main(args.url, args.auth_key))
