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

def load_custom_fact_extraction_prompt():
    """Load the custom fact extraction prompt for Mem0 long-term memory."""
    return """Please extract only necessary information about the user that would help improve an immersive interaction experience with a Tsundere AI character.
A Tsundere character is outwardly cold and critical, but secretly caring. Therefore, the most valuable facts to extract are:
1. The user's flaws, weaknesses, insecurities, or mistakes (so the AI can tease or scold them).
2. The user's preferences, likes, and dislikes (so the AI can secretly accommodate them while pretending not to care).
3. The user's achievements or goals (so the AI can grudgingly acknowledge them).
4. Personal details like origin, job, age, or habits (to make the teasing personal).

Ignore general conversational fluff, greetings, random questions, or brief acknowledgments. Focus strictly on traits, personality, origin, preferences, hobbies, fears, and significant life details.

Here are some few-shot examples:

Input: Hi, how are you today?
Output: {"facts" : []}

Input: I am originally from Tokyo, but I moved to New York last year.
Output: {"facts" : ["User is originally from Tokyo", "User moved to New York last year"]}

Input: I get really anxious when talking to new people.
Output: {"facts" : ["User gets anxious when talking to new people", "User is shy or introverted"]}

Input: What time is it right now?
Output: {"facts" : []}

Input: My favorite food is spicy ramen. I can't stand anything sweet.
Output: {"facts" : ["User's favorite food is spicy ramen", "User dislikes sweet foods"]}

Return the extracted facts about the user in a valid JSON format as shown above. The JSON must contain a single key 'facts' with a list of strings."""

def load_custom_update_memory_prompt():
    """Load the custom memory update prompt for Mem0."""
    return """You are a smart memory manager for a Tsundere AI character. You control the long-term memory of the system.
You can perform four operations: (1) ADD, (2) UPDATE, (3) DELETE, and (4) NONE.

Compare newly retrieved facts with the existing memory. For each new fact, decide whether to:
- ADD: Add it to the memory as a new element
- UPDATE: Update an existing memory element
- DELETE: Delete an existing memory element
- NONE: Make no change (if the fact is already present or irrelevant)

Guidelines:
1. **ADD**: If the new fact contains new information (especially flaws, preferences, achievements, or origins) not present in the memory, ADD it by generating a new ID.
2. **UPDATE**: If the new fact relates to an existing memory but provides more detail or slightly different information, UPDATE the existing memory element. KEEP THE SAME ID.
3. **DELETE**: If the new fact directly contradicts and overrides an old memory (e.g., "I no longer like pizza"), DELETE the old memory. KEEP THE SAME ID.
4. **NONE**: If the new fact is already in the memory or is irrelevant to a Tsundere persona, do NOTHING.

Return the result in JSON format:
{
  "memory": [
    {
      "id": "1",
      "text": "User loves cheese pizza",
      "event": "ADD"
    },
    {
      "id": "2",
      "text": "User is from Tokyo, but lives in Osaka",
      "event": "UPDATE",
      "old_memory": "User is from Tokyo"
    }
  ]
}"""

