"""This file contains the graph schema for the application."""

from typing import (
    Annotated, 
    Optional)
from langchain.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import (
    BaseModel,
    Field,
)


class GraphState(BaseModel):
    """State definition for the LangGraph Agent/Workflow."""

    messages: Annotated[list[AnyMessage], add_messages] = Field(
        default_factory=list, description="The messages in the conversation"
    )
    long_term_memory: str = Field(default="", description="The long term memory of the conversation")
    affection_score: int = Field(default=0, description="Affection score from -10 to 10, controls persona tone")
    user_name: Optional[str] = Field(default=None, description="The name of the user")
    is_safe: bool = Field(default=True, description="Whether the latest user message is safe (not a jailbreak attempt)")
