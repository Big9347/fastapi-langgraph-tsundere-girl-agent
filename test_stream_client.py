import asyncio
import httpx
from app.core.config import settings

async def main():
    try:
        data = {
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", 
                "http://localhost:8000/api/v1/chatbot/chat/stream",
                json=data
            ) as response:
                async for line in response.aiter_lines():
                    print("SERVER SENT:", line)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
