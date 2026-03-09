"""This file contains the graph utilities for the application."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.messages import trim_messages as _trim_messages

from app.core.config import settings
from app.core.logging import logger
from app.schemas import Message


def dump_messages(messages: list[Message]) -> list[dict]:
    """Dump the messages to a list of dictionaries.

    Args:
        messages (list[Message]): The messages to dump.

    Returns:
        list[dict]: The dumped messages.
    """
    return [message.model_dump() for message in messages]


def process_llm_response(response: BaseMessage) -> BaseMessage:
    """Process LLM response to handle structured content blocks (e.g., from GPT-5 models).

    GPT-5 models return content as a list of blocks like:
    [
        {'id': '...', 'summary': [], 'type': 'reasoning'},
        {'type': 'text', 'text': 'actual response'}
    ]

    This function extracts the actual text content from such structures.

    Args:
        response: The raw response from the LLM

    Returns:
        BaseMessage with processed content
    """
    if isinstance(response.content, list):
        # Extract text from content blocks
        text_parts = []
        for block in response.content:
            if isinstance(block, dict):
                # Handle text blocks
                if block.get("type") == "text" and "text" in block:
                    text_parts.append(block["text"])
                # Log reasoning blocks for debugging
                elif block.get("type") == "reasoning":
                    logger.debug(
                        "reasoning_block_received",
                        reasoning_id=block.get("id"),
                        has_summary=bool(block.get("summary")),
                    )
            elif isinstance(block, str):
                text_parts.append(block)

        # Join all text parts
        response.content = "".join(text_parts)
        logger.debug(
            "processed_structured_content",
            block_count=len(response.content) if isinstance(response.content, list) else 1,
            extracted_length=len(response.content) if isinstance(response.content, str) else 0,
        )

    return response


def prepare_messages(messages: list[Message], llm: BaseChatModel, system_prompt: str) -> list[Message]:
    """Prepare the messages for the LLM.

    Args:
        messages (list[Message]): The messages to prepare.
        llm (BaseChatModel): The LLM to use.
        system_prompt (str): The system prompt to use.

    Returns:
        list[Message]: The prepared messages.
    """
    try:
        trimmed_messages = _trim_messages(
            dump_messages(messages),
            strategy="last",
            token_counter=llm,
            max_tokens=settings.MAX_TOKENS,
            start_on="human",
            include_system=False,
            allow_partial=False,
        )
    except ValueError as e:
        # Handle unrecognized content blocks (e.g., reasoning blocks from GPT-5)
        if "Unrecognized content block type" in str(e):
            logger.warning(
                "token_counting_failed_skipping_trim",
                error=str(e),
                message_count=len(messages),
            )
            # Skip trimming and return all messages
            trimmed_messages = messages
        else:
            raise

    return [Message(role="system", content=system_prompt)] + trimmed_messages
def prepare_messages_sliding_window(
    messages: list[BaseMessage],
    system_prompt: str,
    llm: BaseChatModel | None = None,
    session_id: str = "",
    model_name: str = "",
) -> list[BaseMessage]:
    """Prepare messages using a sliding window and check token limits.

    Args:
        messages: Full list of messages from state.
        system_prompt: The system prompt to prepend.
        llm: The current LLM instance for token counting.
        session_id: Session ID for logging.
        model_name: Model name for logging.

    Returns:
        list[dict]: Prepared list of messages to send.
    """
    # 1. Apply sliding window on unified format
    windowed_messages = apply_sliding_window(messages, window_size=settings.SLIDING_WINDOW_SIZE)

    # 2. Build final message list: system + windowed conversation
    messages_to_send = [SystemMessage(content=system_prompt)] + windowed_messages

    # Check if the sliding window exceeds the max token limit and log a warning
    try:
        if llm:
            total_tokens = llm.get_num_tokens_from_messages(messages_to_send)
            if total_tokens > settings.MAX_TOKENS:
                logger.warning(
                    "sliding_window_token_limit_exceeded",
                    total_tokens=total_tokens,
                    max_tokens=settings.MAX_TOKENS,
                    session_id=session_id,
                    model=model_name,
                )
    except Exception as e:
        logger.debug("token_counting_failed", error=str(e))

    return messages_to_send


def apply_sliding_window(messages: list[BaseMessage], window_size: int = 10) -> list[BaseMessage]:
    """Keep only the last N interaction turns (user message + AI response + tools).

    An "interaction turn" is identified by a sequence of messages starting from a human message,
    inclusive of the AI's response and any tool calls/results, up to the next human message.
    Iterating backwards avoids grouping operations on the entire list.

    Args:
        messages: Full list of LangChain BaseMessage objects.
        window_size: Number of interaction turns to keep.

    Returns:
        Trimmed list containing at most window_size interaction turns.
    """
    if not messages:
        return []

    turns: list[list[BaseMessage]] = []
    current_turn: list[BaseMessage] = []

    # Iterate backwards so we can stop as soon as we have enough turns
    for msg in reversed(messages):
        current_turn.append(msg)
        if isinstance(msg, HumanMessage):
            # A human message signifies the "start" of a turn (since we are going backwards)
            turns.append(list(reversed(current_turn)))
            current_turn = []
            
            if len(turns) == window_size:
                break

    # If the first message in the slice isn't human (e.g. system message or malformed state), include the remainder
    if current_turn and len(turns) < window_size:
        turns.append(list(reversed(current_turn)))

    # We accumulated turns backwards, so reverse them to chronological order
    turns.reverse()
    
    # Flatten back to a single list
    return [m for turn in turns for m in turn]
    
# def prepare_messages_sliding_window(
#     messages: list,
#     system_prompt: str,
#     llm: BaseChatModel | None = None,
#     session_id: str = "",
#     model_name: str = "",
# ) -> list[dict]:
#     """Prepare messages using a sliding window and check token limits.

#     Args:
#         messages: Full list of messages from state.
#         system_prompt: The system prompt to prepend.
#         llm: The current LLM instance for token counting.
#         session_id: Session ID for logging.
#         model_name: Model name for logging.

#     Returns:
#         list[dict]: Prepared list of messages to send.
#     """
#     windowed_messages = _apply_sliding_window(messages, window_size=settings.SLIDING_WINDOW_SIZE)

#     # Build final message list: system + windowed conversation
#     messages_to_send = [{"role": "system", "content": system_prompt}]
#     for msg in windowed_messages:
#         # Handle both BaseMessage objects and dicts
#         if isinstance(msg, dict):
#             role = msg.get("role", "user")
#             content = msg.get("content", "")
#         else:
#             role = "assistant" if getattr(msg, "type", "") == "ai" else "user"
#             content = getattr(msg, "content", "")

#         if role in ("user", "human"):
#             messages_to_send.append({"role": "user", "content": str(content)})
#         elif role in ("assistant", "ai"):
#             messages_to_send.append({"role": "assistant", "content": str(content)})

#     # Check if the sliding window exceeds the max token limit and log a warning
#     try:
#         if llm:
#             total_tokens = llm.get_num_tokens_from_messages(messages_to_send)
#             if total_tokens > settings.MAX_TOKENS:
#                 logger.warning(
#                     "sliding_window_token_limit_exceeded",
#                     total_tokens=total_tokens,
#                     max_tokens=settings.MAX_TOKENS,
#                     session_id=session_id,
#                     model=model_name,
#                 )
#     except Exception as e:
#         logger.debug("token_counting_failed", error=str(e))

#     return messages_to_send


# def _apply_sliding_window(messages: list, window_size: int = 10) -> list:
#     """Keep only the last N user+assistant message pairs.

#     Args:
#         messages: Full list of messages.
#         window_size: Number of message pairs to keep (default: 10).

#     Returns:
#         Trimmed list containing at most window_size pairs.
#     """
#     max_messages = window_size * 2  # Each pair = user + assistant
#     if len(messages) > max_messages:
#         return messages[-max_messages:]
#     return messages
