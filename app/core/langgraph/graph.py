"""This file contains the LangGraph Agent/workflow and interactions with the LLM."""

import asyncio
from typing import (
    AsyncGenerator,
    Optional,
)
from urllib.parse import quote_plus

from asgiref.sync import sync_to_async
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
#    ToolMessage,
    convert_to_openai_messages,
)
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import (
    END,
    StateGraph,
)
from langgraph.graph.state import (
    Command,
    CompiledStateGraph,
)
from langgraph.types import (
    RunnableConfig,
    StateSnapshot,
)
from mem0 import AsyncMemory
from psycopg_pool import AsyncConnectionPool

from app.core.config import (
    Environment,
    settings,
)
#from app.core.langgraph.tools import tools
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.core.prompts import load_system_prompt, load_analyzer_prompt, load_custom_fact_extraction_prompt, load_custom_update_memory_prompt
from app.schemas import (
    GraphState,
    Message,
)
from app.services.llm import llm_service
from app.utils import (
    dump_messages,
    prepare_messages_sliding_window,
    process_llm_response,
)


class LangGraphAgent:
    """Manages the LangGraph Agent/workflow and interactions with the LLM.

    This class handles the creation and management of the LangGraph workflow,
    including LLM interactions, database connections, and response processing.
    """

    def __init__(self):
        """Initialize the LangGraph Agent with necessary components."""
        # Use the LLM service with tools bound
        self.llm_service = llm_service
#        self.llm_service.bind_tools(tools)
#        self.tools_by_name = {tool.name: tool for tool in tools}
        self._connection_pool: Optional[AsyncConnectionPool] = None
        self._graph: Optional[CompiledStateGraph] = None
        self.memory: Optional[AsyncMemory] = None
        logger.info(
            "langgraph_agent_initialized",
            model=settings.DEFAULT_LLM_MODEL,
            environment=settings.ENVIRONMENT.value,
        )

    async def _long_term_memory(self) -> AsyncMemory:
        """Initialize the long term memory."""
        if self.memory is None:
            self.memory = await AsyncMemory.from_config(
                config_dict={
                    "vector_store": {
                        "provider": "pgvector",
                        "config": {
                            "collection_name": settings.LONG_TERM_MEMORY_COLLECTION_NAME,
                            "dbname": settings.POSTGRES_DB,
                            "user": settings.POSTGRES_USER,
                            "password": settings.POSTGRES_PASSWORD,
                            "host": settings.POSTGRES_HOST,
                            "port": settings.POSTGRES_PORT,
                        },
                    },
                    "llm": {
                        "provider": "openai",
                        "config": {"model": settings.LONG_TERM_MEMORY_MODEL},
                    },
                    "embedder": {"provider": "openai", "config": {"model": settings.LONG_TERM_MEMORY_EMBEDDER_MODEL}},
                    "custom_fact_extraction_prompt": load_custom_fact_extraction_prompt(),
                    "custom_update_memory_prompt": load_custom_update_memory_prompt(),
                }
            )
        return self.memory

    async def _get_connection_pool(self) -> AsyncConnectionPool:
        """Get a PostgreSQL connection pool using environment-specific settings.

        Returns:
            AsyncConnectionPool: A connection pool for PostgreSQL database.
        """
        if self._connection_pool is None:
            try:
                # Configure pool size based on environment
                max_size = settings.POSTGRES_POOL_SIZE

                connection_url = (
                    "postgresql://"
                    f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )

                self._connection_pool = AsyncConnectionPool(
                    connection_url,
                    open=False,
                    max_size=max_size,
                    kwargs={
                        "autocommit": True,
                        "connect_timeout": 5,
                        "prepare_threshold": None,
                    },
                )
                await self._connection_pool.open()
                logger.info("connection_pool_created", max_size=max_size, environment=settings.ENVIRONMENT.value)
            except Exception as e:
                logger.error("connection_pool_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                # In production, we might want to degrade gracefully
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_connection_pool", environment=settings.ENVIRONMENT.value)
                    return None
                raise e
        return self._connection_pool

    async def _get_relevant_memory(self, user_id: str, query: str) -> str:
        """Get the relevant memory for the user and query.

        Args:
            user_id (str): The user ID.
            query (str): The query to search for.

        Returns:
            str: The relevant memory.
        """
        try:
            memory = await self._long_term_memory()
            results = await memory.search(user_id=str(user_id), query=query, limit=1)
            print(results)
            return "\n".join([f"* {result['memory']}" for result in results["results"]])
        except Exception as e:
            logger.error("failed_to_get_relevant_memory", error=str(e), user_id=user_id, query=query)
            return ""

    async def _update_long_term_memory(self, user_id: str, messages: list[dict], metadata: dict = None) -> None:
        """Update the long term memory.

        Args:
            user_id (str): The user ID.
            messages (list[dict]): The messages to update the long term memory with.
            metadata (dict): Optional metadata to include.
        """
        try:
            memory = await self._long_term_memory()
            await memory.add(messages, user_id=str(user_id), metadata=metadata)
            logger.info("long_term_memory_updated_successfully", user_id=user_id)
        except Exception as e:
            logger.exception(
                "failed_to_update_long_term_memory",
                user_id=user_id,
                error=str(e),
            )
    async def _guardrail(self, state: GraphState, config: RunnableConfig) -> dict:
        """
        """
        return {}
    async def _analyze(self, state: GraphState, config: RunnableConfig) -> dict:
        """Analyze the user's latest message for sentiment and name extraction.

        Uses the LLM to evaluate whether the message is polite (+1),
        rude (-1), or neutral (0), and extracts the user's name if mentioned.

        Returns:
            dict with score_modifier and optionally user_name.
        """
        # Find the last user message and its index
        last_user_msg_idx = -1
        prev_user_msg_idx = 0
        
        # Iterate backwards to find the last HumanMessage and the one before that
        for i in range(len(state.messages) - 1, -1, -1):
            msg = state.messages[i]
            if isinstance(msg, HumanMessage) and msg.content:
                if last_user_msg_idx == -1:
                    last_user_msg_idx = i
                else:
                    prev_user_msg_idx = i
                    break

        if last_user_msg_idx == -1:
            return {"affection_score": state.affection_score}

        # Build conversation context ending at the last user message, starting from the previous user message
        recent_messages = state.messages[prev_user_msg_idx : last_user_msg_idx + 1]

        analyzer_prompt = load_analyzer_prompt()

        try:
            from pydantic import BaseModel, Field
            class AnalyzerResult(BaseModel):
                modifier: int = Field(description="Score modifier between -1 and 1")
                user_name: str | None = Field(default=None, description="The extracted user name")

            current_llm = self.llm_service.get_llm()
            structured_llm = current_llm.with_structured_output(AnalyzerResult)

            # Build the message list for the LLM natively
            messages_for_llm = [SystemMessage(content=analyzer_prompt)] + recent_messages

            result: AnalyzerResult = await structured_llm.ainvoke(messages_for_llm)

            modifier = max(-1, min(1, result.modifier))  # Clamp to -1, 0, +1

            new_score = state.affection_score + modifier
            new_score = max(-10, min(10, new_score))

            update = {"affection_score": new_score}

            extracted_name = result.user_name
            if extracted_name and isinstance(extracted_name, str):
                update["user_name"] = extracted_name

            logger.info(
                "analyzer_completed",
                modifier=modifier,
                old_score=state.affection_score,
                new_score=new_score,
                extracted_name=extracted_name,
                session_id=config["configurable"]["thread_id"],
            )

            return update

        except Exception as e:
            logger.error("analyzer_failed", error=str(e))
            return {"affection_score": state.affection_score}
        
    async def _generate(self, state: GraphState, config: RunnableConfig) -> dict:
        """Generate the Tsundere-persona response using the current affection score.

        The system prompt dynamically adapts tone based on the score.
        """
        # Get the current LLM instance for metrics
        current_llm = self.llm_service.get_llm()
        model_name = (
            current_llm.model_name
            if current_llm and hasattr(current_llm, "model_name")
            else settings.DEFAULT_LLM_MODEL
        )

        SYSTEM_PROMPT = load_system_prompt(
            long_term_memory=state.long_term_memory, 
            affection_score=state.affection_score,
            user_name=state.user_name
        )

        # Prepare messages with system prompt
        messages = prepare_messages_sliding_window(
            messages=state.messages,
            system_prompt=SYSTEM_PROMPT,
            llm=current_llm,
            session_id=config["configurable"]["thread_id"],
            model_name=model_name,
        )

        try:
            # Use LLM service with automatic retries and circular fallback
            with llm_inference_duration_seconds.labels(model=model_name).time():
                response_message = await self.llm_service.call(messages)

            # Process response to handle structured content blocks
            response_message = process_llm_response(response_message)

            logger.info(
                "llm_response_generated",
                session_id=config["configurable"]["thread_id"],
                model=model_name,
                environment=settings.ENVIRONMENT.value,
                affection_score=state.affection_score,
            )

            # Determine next node based on whether there are tool calls
            # if response_message.tool_calls:
            #     goto = "tool_call"
            # else:
            #     goto = END

            return {"messages": [response_message]}
        except Exception as e:
            logger.error(
                "generator_failed",
                session_id=config["configurable"]["thread_id"],
                error=str(e),
                environment=settings.ENVIRONMENT.value,
            )
            raise Exception(f"Failed to generate Tsundere response: {str(e)}")

    # Define our tool node
    # async def _tool_call(self, state: GraphState) -> Command:
    #     """Process tool calls from the last message.

    #     Args:
    #         state: The current agent state containing messages and tool calls.

    #     Returns:
    #         Command: Command object with updated messages and routing back to chat.
    #     """
    #     outputs = []
    #     for tool_call in state.messages[-1].tool_calls:
    #         tool_result = await self.tools_by_name[tool_call["name"]].ainvoke(tool_call["args"])
    #         outputs.append(
    #             ToolMessage(
    #                 content=tool_result,
    #                 name=tool_call["name"],
    #                 tool_call_id=tool_call["id"],
    #             )
    #         )
    #     return Command(update={"messages": outputs}, goto="chat")

    
    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """Create and configure the LangGraph workflow.

        Returns:
            Optional[CompiledStateGraph]: The configured LangGraph instance or None if init fails
        """
        if self._graph is None:
            try:
                graph_builder = StateGraph(GraphState)
                # graph_builder.add_node("guardrail", self._guardrail)
                graph_builder.add_node("analyzer", self._analyze)
                graph_builder.add_node("generator", self._generate)
#                graph_builder.add_node("tool_call", self._tool_call, ends=["chat"])

                graph_builder.set_entry_point("analyzer")
                # graph_builder.add_conditional_edges(
                #     "guardrail",
                #     lambda x: x["guardrail_decision"],
                #     ["analyzer", END],
                # )
                graph_builder.add_edge("analyzer", "generator")
                graph_builder.add_edge("generator", END)

                # Get connection pool (may be None in production if DB unavailable)
                connection_pool = await self._get_connection_pool()
                if connection_pool:
                    checkpointer = AsyncPostgresSaver(connection_pool)
                    await checkpointer.setup()
                else:
                    # In production, proceed without checkpointer if needed
                    checkpointer = None
                    if settings.ENVIRONMENT != Environment.PRODUCTION:
                        raise Exception("Connection pool initialization failed")

                self._graph = graph_builder.compile(
                    checkpointer=checkpointer, name=f"{settings.PROJECT_NAME} Agent ({settings.ENVIRONMENT.value})"
                )

                logger.info(
                    "graph_created",
                    graph_name=f"{settings.PROJECT_NAME} Agent",
                    environment=settings.ENVIRONMENT.value,
                    has_checkpointer=checkpointer is not None,
                )
            except Exception as e:
                logger.error("graph_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                # In production, we don't want to crash the app
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_graph")
                    return None
                raise e

        return self._graph

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """Get a response from the LLM.

        Args:
            messages (list[Message]): The messages to send to the LLM.
            session_id (str): The session ID for Langfuse tracking.
            user_id (Optional[str]): The user ID for Langfuse tracking.

        Returns:
            tuple[list[dict], int]: The response from the LLM and the affection score.
        """
        if self._graph is None:
            self._graph = await self.create_graph()
        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": [CallbackHandler()],
            "metadata": {
                "user_id": user_id,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }
        relevant_memory = (
            await self._get_relevant_memory(user_id, messages[-1].content)
        ) or "No relevant memory found."
        try:
            response = await self._graph.ainvoke(
                input={"messages": dump_messages(messages), "long_term_memory": relevant_memory},
                config=config,
            )
            # Run memory update in background without blocking the response
            asyncio.create_task(
                self._update_long_term_memory(
                    user_id, convert_to_openai_messages(response["messages"]), config["metadata"]
                )
            )
            return self.__process_messages(response["messages"]), response["affection_score"]
        except Exception as e:
            logger.error(f"Error getting response: {str(e)}")

    async def get_stream_response(
        self, messages: list[Message], session_id: str, user_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Get a stream response from the LLM.

        Args:
            messages (list[Message]): The messages to send to the LLM.
            session_id (str): The session ID for the conversation.
            user_id (Optional[str]): The user ID for the conversation.

        Yields:
            str: Tokens of the LLM response.
        """
        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": [
                CallbackHandler()
            ],
            "metadata": {
                "user_id": user_id,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }
        if self._graph is None:
            self._graph = await self.create_graph()

        relevant_memory = (
            await self._get_relevant_memory(user_id, messages[-1].content)
        ) or "No relevant memory found."

        try:
            async for token, metadata in self._graph.astream(
                {"messages": dump_messages(messages), "long_term_memory": relevant_memory},
                config,
                stream_mode="messages",
            ):
                if metadata.get("langgraph_node") != "generator":
                    continue
                try:
                    content = token.content
                    if isinstance(content, list):
                        text_content = ""
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                text_content += item["text"]
                            elif isinstance(item, str):
                                text_content += item
                        content = text_content
                    
                    if content or token.content == "":
                        # yield even if it's an empty string to maintain stream structure
                        yield str(content)
                except Exception as token_error:
                    logger.error("Error processing token", error=str(token_error), session_id=session_id)
                    # Continue with next token even if current one fails
                    continue

            # After streaming completes, get final state and update memory in background
            state: StateSnapshot = await sync_to_async(self._graph.get_state)(config=config)
            if state.values and "messages" in state.values:
                asyncio.create_task(
                    self._update_long_term_memory(
                        user_id, convert_to_openai_messages(state.values["messages"]), config["metadata"]
                    )
                )
        except Exception as stream_error:
            logger.error("Error in stream processing", error=str(stream_error), session_id=session_id)
            raise stream_error

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """Get the chat history for a given thread ID.

        Args:
            session_id (str): The session ID for the conversation.

        Returns:
            list[Message]: The chat history.
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        state: StateSnapshot = await sync_to_async(self._graph.get_state)(
            config={"configurable": {"thread_id": session_id}}
        )
        return self.__process_messages(state.values["messages"]) if state.values else []
    
    async def get_affection_score(self, session_id: str) -> int:
        """Get the current affection score for a session.

        Args:
            session_id: The session ID.

        Returns:
            int: The current affection score.
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        state: StateSnapshot = await sync_to_async(self._graph.get_state)(
            config={"configurable": {"thread_id": session_id}}
        )
        if state.values:
            return state.values.get("affection_score", 0)
        return 0
    
    def __process_messages(self, messages: list[BaseMessage]) -> list[Message]:
        openai_style_messages = convert_to_openai_messages(messages)
        # keep just assistant and user messages
        processed = []
        for message in openai_style_messages:
            if message["role"] not in ["assistant", "user"]:
                continue
                
            content = message.get("content", "")
            if not content:
                continue
                
            if isinstance(content, list):
                text_content = ""
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        text_content += item["text"]
                    elif isinstance(item, str):
                        text_content += item
                content_str = text_content
            else:
                content_str = str(content)
                
            processed.append(Message(role=message["role"], content=content_str))
        return processed

    async def clear_chat_history(self, session_id: str) -> None:
        """Clear all chat history for a given thread ID.

        Args:
            session_id: The ID of the session to clear history for.

        Raises:
            Exception: If there's an error clearing the chat history.
        """
        try:
            # Make sure the pool is initialized in the current event loop
            conn_pool = await self._get_connection_pool()

            # Use a new connection for this specific operation
            async with conn_pool.connection() as conn:
                for table in settings.CHECKPOINT_TABLES:
                    try:
                        await conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (session_id,))
                        logger.info(f"Cleared {table} for session {session_id}")
                    except Exception as e:
                        logger.error(f"Error clearing {table}", error=str(e))
                        raise

        except Exception as e:
            logger.error("Failed to clear chat history", error=str(e))
            raise
