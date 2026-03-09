import os
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ["POSTGRES_HOST"] = "localhost"

from app.core.langgraph.graph import LangGraphAgent
from app.schemas.chat import Message

agent = LangGraphAgent()

async def run():
    messages = [Message(role='user', content='Hello')]
    try:
        async for chunk in agent.get_stream_response(messages, 'test-sess', 'test-user'):
            print('CHUNK TYPE:', type(chunk))
            print('CHUNK:', repr(chunk))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error during streaming: {e}")

asyncio.run(run())
