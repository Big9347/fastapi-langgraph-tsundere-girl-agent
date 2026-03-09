"""This file contains the prompts for the agent."""

import os
from datetime import datetime

from app.core.config import settings


def load_system_prompt(affection_score: int = 0, user_name: str = None, **kwargs):
    """Load the system prompt from the file.

    Args:
        affection_score: Current affection score to inject into the prompt.
        user_name: The user's extracted name, if known.
    """
    # Build user name section
    if user_name:
        user_name_section = f"The user's name is **{user_name}**. Use it occasionally to make interactions feel personal."
    else:
        user_name_section = "The user's name is unknown. You may ask for it if the conversation feels natural."

    with open(os.path.join(os.path.dirname(__file__), "system.md"), "r") as f:
        return f.read().format(
            character_name=settings.CHARACTER_NAME,
            current_date_and_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_name_section=user_name_section,
            affection_score=affection_score,
            **kwargs,
        )
def load_analyzer_prompt():
    """Load the analyzer prompt for evaluating user messages."""
    return """You are a sentiment analyzer for a Tsundere chatbot. Your ONLY job is to analyze the user's latest message and return a JSON object.

Evaluate the user's message for:
1. **Politeness/Kindness**: Is the user being polite, kind, complimentary, or affectionate? → modifier = +1
2. **Rudeness/Hostility**: Is the user being rude, mean, insulting, or hostile? → modifier = -1
3. **Neutral**: The message is a normal question or statement with no strong sentiment → modifier = 0

Also extract the user's name if they introduce themselves (e.g., "My name is X", "I'm X", "Call me X").

Return ONLY a valid JSON object with no other text:
{"modifier": 0, "user_name": null}

Rules:
- modifier MUST be exactly -1, 0, or +1 (integer)
- user_name should be a string if detected, or null if not
- Do NOT explain your reasoning
- Do NOT return anything except the JSON object"""