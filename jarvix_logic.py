import os
import asyncio
import re
from typing import AsyncGenerator, Type, List
import google.generativeai as genai
import pandas as pd
from config import settings, BASE_DIR
from agents.data_scientist import run_dynamic_analysis_async, SAFETY_SETTINGS

# --- CONFIGURATION & CONSTANTS ---
genai.configure(api_key=settings.GOOGLE_API_KEY)
USER_HOME = os.path.expanduser("~")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
MUSIC_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}


# --- Agent Base Class ---
class BaseAgent:
    """An abstract class for a Jarvix agent."""

    keywords: List[str] = []

    @classmethod
    def can_handle(cls, prompt: str) -> bool:
        """Checks if the agent's keywords are in the user's prompt."""
        return any(keyword in prompt.lower() for keyword in cls.keywords)

    async def execute(
        self, prompt: str, websocket, command_id: str = None
    ) -> AsyncGenerator[str, None]:
        """The main execution logic for the agent."""
        raise NotImplementedError


# --- Specific Agents ---
class DataScienceAgent(BaseAgent):
    """Handles requests for data analysis on CSV or Excel files."""

    keywords = [
        "analyze",
        "analysis",
        "process",
        "visualize",
        "report",
        ".csv",
        ".xlsx",
    ]

    async def execute(
        self, prompt: str, websocket, command_id: str = None
    ) -> AsyncGenerator[str, None]:
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
                    if file_path.endswith(".csv"):
                        df = pd.read_csv(file_path)
                    else:
                        df = pd.read_excel(file_path)

                    # Get all columns
                    all_columns = list(df.columns)

                    # Filter out music-related or non-numeric columns
                    relevant_columns = [
                        col
                        for col in all_columns
                        if not any(ext in col.lower() for ext in MUSIC_EXTENSIONS)
                    ]

                    # Send column information
                    columns_info = f"""
📊 **Dataset Overview:**
- Total Columns: {len(all_columns)}
- Total Rows: {len(df)}

📋 **Available Columns for Analysis:**
{chr(10).join([f"  • {col} ({df[col].dtype})" for col in relevant_columns])}
"""
                    await websocket.send_json(
                        {"type": "stream", "id": command_id, "message": columns_info}
                    )
                    await asyncio.sleep(0.3)

                except Exception as e:
                    yield f"⚠️ **Warning:** Could not read column info: {str(e)}"

                yield f"🚀 Engaging AI for analysis..."
                await asyncio.sleep(1)
                result = await run_dynamic_analysis_async(
                    BASE_DIR, file_path, prompt, websocket
                )
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
        file_path = next(
            (path for path in paths_to_check if os.path.exists(path)), None
        )

        if not file_path:
            yield f"❌ **Error:** File `{filename}` not found in Downloads or project directory."
            return

        yield f"🔍 File found at `{file_path}`. Loading data..."
        await asyncio.sleep(0.5)

        # Extract and send column information
        try:
            if file_path.endswith(".csv"):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)

            # Get all columns
            all_columns = list(df.columns)

            # Filter out music-related or non-numeric columns
            relevant_columns = [
                col
                for col in all_columns
                if not any(ext in col.lower() for ext in MUSIC_EXTENSIONS)
            ]

            # Send column information
            columns_info = f"""
📊 **Dataset Overview:**
- Total Columns: {len(all_columns)}
- Total Rows: {len(df)}

📋 **Available Columns for Analysis:**
{chr(10).join([f"  • {col} ({df[col].dtype})" for col in relevant_columns])}
"""
            await websocket.send_json(
                {"type": "stream", "id": command_id, "message": columns_info}
            )
            await asyncio.sleep(0.3)

        except Exception as e:
            yield f"⚠️ **Warning:** Could not read column info: {str(e)}"

        yield f"🚀 Engaging AI for analysis..."
        await asyncio.sleep(1)

        # Run analysis with user's prompt
        result = await run_dynamic_analysis_async(
            BASE_DIR, file_path, prompt, websocket
        )
        yield result


class CalendarAgent(BaseAgent):
    """A placeholder agent to demonstrate multi-agent capability."""

    keywords = ["calendar", "event", "meeting", "schedule"]

    async def execute(
        self, prompt: str, websocket, command_id: str = None
    ) -> AsyncGenerator[str, None]:
        yield "📅 **Calendar Agent**: Simulating..."
        await asyncio.sleep(1)
        yield "👍 **Success:** Event scheduled (simulation)."


class CustomPromptAgent(BaseAgent):
    """Allows user to write custom prompts directly to Gemini without pre-defined agents."""

    keywords = []  # This agent requires explicit detection

    ENHANCED_SYSTEM_INSTRUCTIONS = """You are Jarvix 👋 Completed, an advanced AI analysis assistant.

When the user provides a prompt:
1. Analyze the request thoroughly and provide comprehensive insights
2. Structure your response in clear sections (Problem Statement, Analysis, Findings, Recommendations)
3. Be detailed, professional, and provide actionable insights
4. Format output for easy reading and PDF conversion
5. Include specific data, statistics, or examples where relevant
6. Always respond in English with professional formatting

Your analysis will be converted to a PDF report, so maintain clear formatting and logical structure."""

    async def execute(
        self, prompt: str, websocket, command_id: str = None
    ) -> AsyncGenerator[str, None]:
        """Execute user's custom prompt directly with Gemini and generate PDF report."""
        from jinja2 import Template
        from weasyprint import HTML, CSS
        from datetime import datetime
        
        model = genai.GenerativeModel(
            "gemini-flash-latest",
            system_instruction=self.ENHANCED_SYSTEM_INSTRUCTIONS
        )
        try:
            yield "✨ **Custom Analysis Mode**: Processing your prompt...\n"
            response = await model.generate_content_async(
                prompt, stream=True, safety_settings=SAFETY_SETTINGS
            )
            
            # Collect full response
            full_response = ""
            has_sent_content = False
            async for chunk in response:
                if chunk and chunk.text:
                    has_sent_content = True
                    full_response += chunk.text
                    await websocket.send_json(
                        {"type": "stream", "id": command_id, "message": chunk.text}
                    )
            
            if not has_sent_content:
                full_response = "[Response was empty or blocked]"
                await websocket.send_json(
                    {
                        "type": "stream",
                        "id": command_id,
                        "message": "[Response was empty or blocked]",
                    }
                )
            
            # Generate PDF report
            yield "\n\n📄 **Generating PDF report...**\n"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdf_filename = f"jarvix_analysis_{timestamp}.pdf"
            pdf_path = os.path.join(settings.OUTPUT_DIR, pdf_filename)
            
            # Create HTML template for PDF
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 900px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        text-align: center;
                        border-bottom: 3px solid #2c3e50;
                        padding-bottom: 20px;
                        margin-bottom: 30px;
                    }}
                    .title {{
                        font-size: 28px;
                        font-weight: bold;
                        color: #2c3e50;
                        margin: 0;
                    }}
                    .brand {{
                        font-size: 14px;
                        color: #7f8c8d;
                        margin-top: 5px;
                    }}
                    .timestamp {{
                        font-size: 12px;
                        color: #95a5a6;
                        margin-top: 10px;
                    }}
                    .prompt-section {{
                        background: #ecf0f1;
                        padding: 15px;
                        border-left: 4px solid #3498db;
                        margin: 20px 0;
                        font-size: 14px;
                    }}
                    .prompt-label {{
                        font-weight: bold;
                        color: #2c3e50;
                        margin-bottom: 8px;
                    }}
                    .content {{
                        font-size: 14px;
                        line-height: 1.8;
                        text-align: justify;
                    }}
                    .content h2 {{
                        color: #2c3e50;
                        margin-top: 25px;
                        border-bottom: 2px solid #ecf0f1;
                        padding-bottom: 10px;
                    }}
                    .content h3 {{
                        color: #34495e;
                        margin-top: 15px;
                    }}
                    .footer {{
                        text-align: center;
                        border-top: 2px solid #ecf0f1;
                        padding-top: 15px;
                        margin-top: 30px;
                        font-size: 12px;
                        color: #7f8c8d;
                    }}
                    .footer-brand {{
                        font-weight: bold;
                        color: #2c3e50;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="title">🤖 Jarvix 👋 Completed</div>
                    <div class="brand">Custom Analysis Report</div>
                    <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                </div>
                
                <div class="prompt-section">
                    <div class="prompt-label">📝 Analysis Request:</div>
                    <div>{prompt}</div>
                </div>
                
                <div class="content">
                    {full_response.replace(chr(10), '<br>')}
                </div>
                
                <div class="footer">
                    <div>Report generated by <span class="footer-brand">Jarvix 👋 Completed</span></div>
                    <div style="margin-top: 10px; font-size: 11px;">
                        Note: This analysis is based on the custom prompt provided. Results may vary with different prompts.
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Convert HTML to PDF
            HTML(string=html_template).write_pdf(pdf_path)
            
            yield f"✅ **PDF Report Generated**: {pdf_filename}\n"
            yield f"📍 **Location**: {pdf_path}\n"
            yield f"\n✨ **Analysis complete!** Your custom analysis has been processed and saved to PDF."
            
        except Exception as e:
            yield f"❌ **Custom Analysis Error:** {str(e)}"


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

    async def execute(
        self, prompt: str, websocket, command_id: str = None
    ) -> AsyncGenerator[str, None]:
        model = genai.GenerativeModel(
            "gemini-flash-latest", system_instruction=self.SYSTEM_INSTRUCTIONS
        )
        try:
            yield "🤖 **Jarvix 👋 Completed**"  # Signal agent activation
            response = await model.generate_content_async(
                prompt, stream=True, safety_settings=SAFETY_SETTINGS
            )
            has_sent_content = False
            async for chunk in response:
                if chunk and chunk.text:
                    has_sent_content = True
                    await websocket.send_json(
                        {"type": "stream", "id": command_id, "message": chunk.text}
                    )
            if not has_sent_content:
                await websocket.send_json(
                    {
                        "type": "stream",
                        "id": command_id,
                        "message": "[Response was empty or blocked]",
                    }
                )
        except Exception as e:
            yield f"❌ **Jarvix API Error:** {e}"


# --- AGENT REGISTRY & ROUTER ---
SPECIFIC_AGENTS: List[Type[BaseAgent]] = [DataScienceAgent, CalendarAgent]


def detect_custom_prompt_mode(prompt: str) -> bool:
    """Detect if user is in custom prompt mode by checking for special marker."""
    return prompt.strip().lower().startswith("custom:")


async def jarvix_main_router(
    prompt: str, websocket, command_id: str = None
) -> AsyncGenerator[str, None]:
    """Finds the appropriate agent and executes the prompt.
    
    Priority:
    1. Check for explicit CUSTOM: marker → CustomPromptAgent
    2. Check for specific agent keywords (analyze, calendar, etc.)
    3. Fall back to ConversationalAgent
    """

    # Check for explicit CUSTOM: mode
    if detect_custom_prompt_mode(prompt):
        custom_agent = CustomPromptAgent()
        clean_prompt = prompt[7:].strip()  # Remove "CUSTOM:"
        async for log in custom_agent.execute(clean_prompt, websocket, command_id):
            yield log
        return

    # Check for specific agent keywords
    for agent_class in SPECIFIC_AGENTS:
        if agent_class.can_handle(prompt):
            agent_instance = agent_class()
            async for log in agent_instance.execute(prompt, websocket, command_id):
                yield log
            return

    # Fallback to conversational agent for general questions
    conversational_agent = ConversationalAgent()
    async for log in conversational_agent.execute(prompt, websocket, command_id):
        yield log
