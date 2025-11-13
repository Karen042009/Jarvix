import os
import asyncio
import re
from typing import AsyncGenerator, Type, List
import google.generativeai as genai
from config import settings, BASE_DIR
from agents.data_scientist import run_dynamic_analysis, SAFETY_SETTINGS

# --- CONFIGURATION & CONSTANTS ---
genai.configure(api_key=settings.GOOGLE_API_KEY)
USER_HOME = os.path.expanduser("~")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")

# --- Agent Base Class ---
class BaseAgent:
    """An abstract class for a Jarvix agent."""
    keywords: List[str] = []
    
    @classmethod
    def can_handle(cls, prompt: str) -> bool:
        """Checks if the agent's keywords are in the user's prompt."""
        return any(keyword in prompt.lower() for keyword in cls.keywords)
    
    async def execute(self, prompt: str, websocket, command_id: str = None) -> AsyncGenerator[str, None]:
        """The main execution logic for the agent."""
        raise NotImplementedError

# --- Specific Agents ---
class DataScienceAgent(BaseAgent):
    """Handles requests for data analysis on CSV or Excel files."""
    keywords = ["analyze", "analysis", "process", "visualize", "report", ".csv", ".xlsx"]

    async def execute(self, prompt: str, websocket, command_id: str = None) -> AsyncGenerator[str, None]:
        yield "🔬 **Autonomous AI Analyst**: Activated."
        await asyncio.sleep(0.5)

        # First, try to match full file paths (e.g., /path/to/file.csv)
        full_path_match = re.search(r'(/[^\s\'"]+\.(?:csv|xlsx|xls))', prompt)
        if full_path_match:
            file_path = full_path_match.group(1).strip()
            if os.path.exists(file_path):
                yield f"🔍 File found at `{file_path}`. Engaging AI..."
                await asyncio.sleep(1)
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, run_dynamic_analysis, BASE_DIR, file_path)
                yield result
                return
            else:
                yield f"❌ **Error:** File path `{file_path}` does not exist."
                return

        # Fallback: match just filename and search in common locations
        file_match = re.search(r'[\'"]?([\w\s\-\.]+\.(?:csv|xlsx|xls))[\'"]?', prompt)
        if not file_match:
            yield "❌ **Error:** Please specify a `.csv` or `.xlsx` file name or full path."
            return
            
        filename = file_match.group(1).strip()
        paths_to_check = [os.path.join(DOWNLOADS_DIR, filename), filename]
        file_path = next((path for path in paths_to_check if os.path.exists(path)), None)

        if not file_path:
            yield f"❌ **Error:** File `{filename}` not found in Downloads or project directory."
            return
            
        yield f"🔍 File found at `{file_path}`. Engaging AI..."
        await asyncio.sleep(1)

        # Run the heavy data processing in a separate thread to not block the server
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_dynamic_analysis, BASE_DIR, file_path)
        yield result

class CalendarAgent(BaseAgent):
    """A placeholder agent to demonstrate multi-agent capability."""
    keywords = ["calendar", "event", "meeting", "schedule"]
    async def execute(self, prompt: str, websocket, command_id: str = None) -> AsyncGenerator[str, None]:
        yield "📅 **Calendar Agent**: Simulating..."
        await asyncio.sleep(1)
        yield "👍 **Success:** Event scheduled (simulation)."

class ConversationalAgent(BaseAgent):
    """The default agent for general conversation, powered by Gemini."""
    keywords = []
    
    # System instructions to ensure English language responses
    SYSTEM_INSTRUCTIONS = """You are Jarvix ✅ Completed, an intelligent AI assistant powered by Google Gemini.
Your role is to help users provide accurate, helpful, and professional assistance.
ALWAYS RESPOND IN ENGLISH, regardless of what language the user writes in.
Be friendly, professional, knowledgeable, and helpful.
If the question is in another language, respond in English while preserving the meaning of the question.
Sign your responses as "Jarvix ✅ Completed" to maintain brand consistency."""
    
    async def execute(self, prompt: str, websocket, command_id: str = None) -> AsyncGenerator[str, None]:
        model = genai.GenerativeModel(
            'gemini-flash-latest',
            system_instruction=self.SYSTEM_INSTRUCTIONS
        )
        try:
            yield "🤖 **Jarvix ✅ Completed** - Powered by Gemini" # Signal agent activation
            response = await model.generate_content_async(prompt, stream=True, safety_settings=SAFETY_SETTINGS)
            has_sent_content = False
            async for chunk in response:
                if chunk and chunk.text:
                    has_sent_content = True
                    await websocket.send_json({"type": "stream", "id": command_id, "message": chunk.text})
            if not has_sent_content:
                await websocket.send_json({"type": "stream", "id": command_id, "message": "[Response was empty or blocked]"})
        except Exception as e:
            yield f"❌ **Gemini API Error:** {e}"

# --- AGENT REGISTRY & ROUTER ---
SPECIFIC_AGENTS: List[Type[BaseAgent]] = [ DataScienceAgent, CalendarAgent ]

async def jarvix_main_router(prompt: str, websocket, command_id: str = None) -> AsyncGenerator[str, None]:
    """Finds the appropriate agent and executes the prompt."""
    for agent_class in SPECIFIC_AGENTS:
        if agent_class.can_handle(prompt):
            agent_instance = agent_class()
            async for log in agent_instance.execute(prompt, websocket, command_id):
                yield log
            return
            
    # Fallback to conversational agent if no specific agent is triggered
    conversational_agent = ConversationalAgent()
    async for log in conversational_agent.execute(prompt, websocket, command_id):
        yield log