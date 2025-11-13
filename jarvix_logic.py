import os
import asyncio
import re
from typing import AsyncGenerator, Type, List
import google.generativeai as genai
import pandas as pd
from config import settings, BASE_DIR
from agents.data_scientist import run_dynamic_analysis, SAFETY_SETTINGS

# --- CONFIGURATION & CONSTANTS ---
genai.configure(api_key=settings.GOOGLE_API_KEY)
USER_HOME = os.path.expanduser("~")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
MUSIC_EXTENSIONS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'}

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
                yield f"🔍 File found at `{file_path}`. Loading data..."
                await asyncio.sleep(0.5)
                
                # Extract and send column information
                try:
                    if file_path.endswith('.csv'):
                        df = pd.read_csv(file_path)
                    else:
                        df = pd.read_excel(file_path)
                    
                    # Get all columns
                    all_columns = list(df.columns)
                    
                    # Filter out music-related or non-numeric columns
                    relevant_columns = [col for col in all_columns 
                                       if not any(ext in col.lower() for ext in MUSIC_EXTENSIONS)]
                    
                    # Send column information
                    columns_info = f"""
📊 **Dataset Overview:**
- Total Columns: {len(all_columns)}
- Total Rows: {len(df)}

📋 **Available Columns for Analysis:**
{chr(10).join([f"  • {col} ({df[col].dtype})" for col in relevant_columns])}
"""
                    await websocket.send_json({"type": "stream", "id": command_id, "message": columns_info})
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    yield f"⚠️ **Warning:** Could not read column info: {str(e)}"
                
                yield f"🚀 Engaging AI for analysis..."
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
            
        yield f"🔍 File found at `{file_path}`. Loading data..."
        await asyncio.sleep(0.5)
        
        # Extract and send column information
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            
            # Get all columns
            all_columns = list(df.columns)
            
            # Filter out music-related or non-numeric columns
            relevant_columns = [col for col in all_columns 
                               if not any(ext in col.lower() for ext in MUSIC_EXTENSIONS)]
            
            # Send column information
            columns_info = f"""
📊 **Dataset Overview:**
- Total Columns: {len(all_columns)}
- Total Rows: {len(df)}

📋 **Available Columns for Analysis:**
{chr(10).join([f"  • {col} ({df[col].dtype})" for col in relevant_columns])}
"""
            await websocket.send_json({"type": "stream", "id": command_id, "message": columns_info})
            await asyncio.sleep(0.3)
            
        except Exception as e:
            yield f"⚠️ **Warning:** Could not read column info: {str(e)}"
        
        yield f"🚀 Engaging AI for analysis..."
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

class CustomPromptAgent(BaseAgent):
    """Allows user to write custom prompts directly to Gemini without pre-defined agents."""
    keywords = []  # This agent requires explicit detection
    
    async def execute(self, prompt: str, websocket, command_id: str = None) -> AsyncGenerator[str, None]:
        """Execute user's custom prompt directly with Gemini."""
        model = genai.GenerativeModel('gemini-flash-latest')
        try:
            yield "✨ **Custom Analysis Mode**: Processing your prompt..."
            response = await model.generate_content_async(prompt, stream=True, safety_settings=SAFETY_SETTINGS)
            has_sent_content = False
            async for chunk in response:
                if chunk and chunk.text:
                    has_sent_content = True
                    await websocket.send_json({"type": "stream", "id": command_id, "message": chunk.text})
            if not has_sent_content:
                await websocket.send_json({"type": "stream", "id": command_id, "message": "[Response was empty or blocked]"})
        except Exception as e:
            yield f"❌ **Custom Analysis Error:** {e}"

class ConversationalAgent(BaseAgent):
    """The default agent for general conversation."""
    keywords = []
    
    # System instructions to ensure English language responses
    SYSTEM_INSTRUCTIONS = """You are Jarvix 👋 Completed, an intelligent AI assistant.
Your role is to help users provide accurate, helpful, and professional assistance.
ALWAYS RESPOND IN ENGLISH, regardless of what language the user writes in.
Be friendly, professional, knowledgeable, and helpful.
If the question is in another language, respond in English while preserving the meaning of the question.
Sign your responses as "Jarvix 👋 Completed" to maintain brand consistency."""
    
    async def execute(self, prompt: str, websocket, command_id: str = None) -> AsyncGenerator[str, None]:
        model = genai.GenerativeModel(
            'gemini-flash-latest',
            system_instruction=self.SYSTEM_INSTRUCTIONS
        )
        try:
            yield "🤖 **Jarvix 👋 Completed**" # Signal agent activation
            response = await model.generate_content_async(prompt, stream=True, safety_settings=SAFETY_SETTINGS)
            has_sent_content = False
            async for chunk in response:
                if chunk and chunk.text:
                    has_sent_content = True
                    await websocket.send_json({"type": "stream", "id": command_id, "message": chunk.text})
            if not has_sent_content:
                await websocket.send_json({"type": "stream", "id": command_id, "message": "[Response was empty or blocked]"})
        except Exception as e:
            yield f"❌ **Jarvix API Error:** {e}"

# --- AGENT REGISTRY & ROUTER ---
SPECIFIC_AGENTS: List[Type[BaseAgent]] = [ DataScienceAgent, CalendarAgent ]

def detect_custom_prompt_mode(prompt: str) -> bool:
    """Detect if user is in custom prompt mode by checking for special marker."""
    return prompt.strip().lower().startswith('custom:')

async def jarvix_main_router(prompt: str, websocket, command_id: str = None) -> AsyncGenerator[str, None]:
    """Finds the appropriate agent and executes the prompt."""
    
    # Check for custom prompt mode first
    if detect_custom_prompt_mode(prompt):
        custom_agent = CustomPromptAgent()
        # Remove marker and execute
        clean_prompt = prompt[7:].strip()  # Remove "CUSTOM:"
        async for log in custom_agent.execute(clean_prompt, websocket, command_id):
            yield log
        return
    
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