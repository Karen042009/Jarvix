import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from weasyprint import HTML
from datetime import datetime
import numpy as np
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from config import settings, BASE_DIR
import traceback
import re
from typing import Dict, Any, List
from pathlib import Path
import json
import asyncio

# --- CONFIGURATION ---
genai.configure(api_key=settings.GOOGLE_API_KEY)
USER_HOME = os.path.expanduser("~")
OUTPUT_DIR = os.path.join(USER_HOME, "Desktop")
TEMP_CHART_DIR = os.path.join(OUTPUT_DIR, "jarvix_temp_charts")
os.makedirs(TEMP_CHART_DIR, exist_ok=True)

# Number of charts to generate (can be overridden with environment variable NUM_CHARTS)
NUM_CHARTS = int(os.getenv("NUM_CHARTS", "3"))

# Safety settings for Jarvix API calls to prevent unnecessary blocking.
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}


# --- STEP 1: GET BRIEF ANALYSIS ---
async def get_brief_analysis(user_prompt: str, df: pd.DataFrame, file_name: str, websocket=None) -> str:
    """Get concise analysis from Gemini (limit to 500 words)."""
    model = genai.GenerativeModel("gemini-flash-latest")
    
    df_preview = df.head(10).to_string()
    df_stats = df.describe().to_string()
    columns_list = ", ".join(df.columns.tolist())
    
    enhanced_prompt = f"""You are an expert data analyst. Analyze this CSV file BRIEFLY (max 500 words).

**User's Request:** {user_prompt}

**Data:**
- File: {file_name}
- Rows: {len(df)} | Columns: {len(df.columns)}
- Columns: {columns_list}

**Data Preview:**
{df_preview}

**Statistics:**
{df_stats}

Provide 3-5 KEY INSIGHTS only. Be concise and specific. Focus on actionable findings."""

    try:
        analysis_text = ""
        response = await model.generate_content_async(
            enhanced_prompt, stream=True, safety_settings=SAFETY_SETTINGS
        )
        
        async for chunk in response:
            if chunk and chunk.text:
                analysis_text += chunk.text
                if websocket:
                    await websocket.send_json({
                        "type": "stream",
                        "message": chunk.text
                    })
        
        return analysis_text
    except Exception as e:
        return f"❌ **Analysis Error:** {str(e)}"


# --- STEP 2: GENERATE VISUALIZATION CODE ---
async def get_visualization_code(user_prompt: str, df: pd.DataFrame) -> str:
    """Ask Gemini to generate Python code for {NUM_CHARTS} visualizations."""
    model = genai.GenerativeModel("gemini-flash-latest")
    
    columns_list = ", ".join(df.columns.tolist())
    sample_data = df.head(5).to_string()
    
    viz_prompt = f"""You MUST generate exactly {NUM_CHARTS} matplotlib visualizations.

CRITICAL: Return ONLY valid Python code in a code block (```python ... ```). No explanations, no text before or after.

**Context:**
- User wants: {user_prompt}
- DataFrame columns: {columns_list}
- Rows: {len(df)}
- Sample data preview:
{sample_data}

**Requirements:**
1. Create EXACTLY {NUM_CHARTS} separate matplotlib figures
2. Each chart MUST:
   - Use plt.figure(figsize=(12, 6))
   - Include meaningful title and labels
   - Save to: chart_path = os.path.join(TEMP_CHART_DIR, 'chart_N.png')
   - Call plt.savefig(chart_path, dpi=150, bbox_inches='tight')
   - Append to chart_paths: chart_paths.append(chart_path)
   - Call plt.close() to free memory
3. Use ONLY these: plt, sns, pd, np, df, os, matplotlib, seaborn
4. Never reference columns that don't exist
5. Handle missing values gracefully

Return the code wrapped in ```python ... ``` markers."""

    try:
        response = model.generate_content(viz_prompt, safety_settings=SAFETY_SETTINGS)
        code_text = response.text.strip()
        
        # Extract code from markdown block
        if "```python" in code_text:
            code = code_text.split("```python")[1].split("```")[0].strip()
        elif "```" in code_text:
            code = code_text.split("```")[1].split("```")[0].strip()
        else:
            code = code_text
        
        return code
    except Exception as e:
        return f"# Error generating visualization code: {str(e)}"


# --- STEP 3: EXECUTE VISUALIZATION CODE ---
def generate_charts(viz_code: str, df: pd.DataFrame, websocket_callback=None) -> List[str]:
    """Execute visualization code and return list of chart paths."""
    chart_paths = []
    
    if not viz_code or viz_code.startswith("# Error"):
        print(f"⚠️ Skipping visualization generation: {viz_code[:50]}")
        return []
    
    try:
        local_scope = {
            "df": df,
            "pd": pd,
            "plt": plt,
            "sns": sns,
            "np": np,
            "os": os,
            "TEMP_CHART_DIR": TEMP_CHART_DIR,
            "chart_paths": chart_paths,
        }
        
        # Execute the visualization code
        exec(viz_code, {"__builtins__": __builtins__}, local_scope)
        
        # Get the chart paths that were generated
        generated_paths = local_scope.get("chart_paths", [])
        
        # Verify charts exist
        valid_paths = [p for p in generated_paths if os.path.exists(p)]
        
        if websocket_callback:
            websocket_callback(f"Generated {len(valid_paths)} visualization(s)")
        
        print(f"✅ Successfully generated {len(valid_paths)} chart(s)")
        return valid_paths
        
    except Exception as e:
        error_msg = f"⚠️ Visualization Error: {type(e).__name__}: {str(e)}"
        print(error_msg)
        if websocket_callback:
            websocket_callback(error_msg)
        return []


# --- MAIN PIPELINE: Analysis + Visualizations + PDF ---
async def run_dynamic_analysis_async(base_dir: Path, file_path: str, user_prompt: str, websocket=None) -> str:
    """
    Main analysis function with visualizations:
    1. Get concise analysis from Gemini (500 words max)
    2. Generate visualization code
    3. Create charts
    4. Build PDF with analysis + charts
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at '{file_path}'.")
        
        df = (
            pd.read_csv(file_path)
            if file_path.endswith(".csv")
            else pd.read_excel(file_path)
        )
        
        file_name = os.path.basename(file_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = Path(file_path).stem
        
        # Ensure temp chart directory exists
        os.makedirs(TEMP_CHART_DIR, exist_ok=True)
        
        # Step 1: Get brief analysis
        if websocket:
            await websocket.send_json({
                "type": "stream",
                "message": "📊 Analyzing dataset...\n"
            })
        
        analysis_text = await get_brief_analysis(user_prompt, df, file_name, websocket)
        
        if "❌" in analysis_text:
            return analysis_text
        
        # Step 2: Generate visualization code
        if websocket:
            await websocket.send_json({
                "type": "stream",
                "message": f"\n📈 Generating Python code for {NUM_CHARTS} visualization(s)...\n"
            })
        
        viz_code = await get_visualization_code(user_prompt, df)
        
        # Debug: log code generation
        if viz_code.startswith("# Error"):
            if websocket:
                await websocket.send_json({
                    "type": "stream",
                    "message": f"⚠️ {viz_code}\n"
                })
            print(f"❌ Visualization code generation failed: {viz_code}")
        else:
            print(f"✅ Generated {len(viz_code)} chars of visualization code")
        
        # Step 3: Execute visualization code
        def ws_callback(msg):
            if websocket:
                import asyncio
                try:
                    asyncio.create_task(websocket.send_json({
                        "type": "stream",
                        "message": msg
                    }))
                except:
                    pass
        
        chart_paths = generate_charts(viz_code, df, ws_callback)
        
        chart_count = len(chart_paths) if chart_paths else 0
        if websocket:
            await websocket.send_json({
                "type": "stream",
                "message": f"✅ Successfully created {chart_count} visualization(s)\n"
            })
        
        # Step 4: Build PDF with analysis + charts
        # Convert charts to base64 to embed in PDF
        import base64
        chart_html = ""
        for i, chart_path in enumerate(chart_paths, 1):
            if os.path.exists(chart_path):
                try:
                    with open(chart_path, 'rb') as f:
                        chart_data = base64.b64encode(f.read()).decode('utf-8')
                    chart_html += f"""
                    <div style="margin: 20px 0; text-align: center; page-break-inside: avoid;">
                        <img src="data:image/png;base64,{chart_data}" style="max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 5px;">
                    </div>
                    """
                except Exception as e:
                    print(f"⚠️ Could not embed chart {i}: {e}")
        
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #2c3e50;
                    max-width: 950px;
                    margin: 0 auto;
                    padding: 30px;
                    background: #f8f9fa;
                }}
                .header {{
                    text-align: center;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px;
                    margin-bottom: 30px;
                }}
                .title {{
                    font-size: 32px;
                    font-weight: bold;
                    margin: 0;
                }}
                .subtitle {{
                    font-size: 16px;
                    opacity: 0.9;
                    margin-top: 8px;
                }}
                .timestamp {{
                    font-size: 13px;
                    opacity: 0.8;
                    margin-top: 10px;
                }}
                .file-info {{
                    background: white;
                    padding: 20px;
                    border-left: 5px solid #667eea;
                    margin-bottom: 25px;
                    border-radius: 5px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .file-info strong {{
                    color: #667eea;
                }}
                .section {{
                    background: white;
                    padding: 25px;
                    margin-bottom: 25px;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                }}
                .section-title {{
                    font-size: 20px;
                    font-weight: bold;
                    color: #667eea;
                    margin-top: 0;
                    margin-bottom: 15px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #ecf0f1;
                }}
                .analysis-text {{
                    font-size: 14px;
                    line-height: 1.8;
                    color: #444;
                    text-align: justify;
                }}
                .charts-container {{
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                }}
                .chart-wrapper {{
                    text-align: center;
                    border: 1px solid #ecf0f1;
                    padding: 15px;
                    border-radius: 8px;
                    background: #f8f9fa;
                }}
                .chart-wrapper img {{
                    max-width: 100%;
                    height: auto;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 2px solid #ecf0f1;
                    color: #7f8c8d;
                    font-size: 12px;
                }}
                .footer-brand {{
                    font-weight: bold;
                    color: #667eea;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="title">🤖 Jarvix 👋 Completed</div>
                <div class="subtitle">Data Analysis Report</div>
                <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            
            <div class="file-info">
                <strong>📊 Dataset:</strong> {file_name}<br>
                <strong>📈 Dimensions:</strong> {len(df):,} rows × {len(df.columns)} columns
            </div>
            
            <div class="section">
                <div class="section-title">📋 Analysis & Insights</div>
                <div class="analysis-text">
                    {analysis_text.replace(chr(10), '<br>')}
                </div>
            </div>
            
            {f'<div class="section"><div class="section-title">📊 Visualizations</div><div class="charts-container">{chart_html}</div></div>' if chart_paths else ''}
            
            <div class="footer">
                <div>Report generated by <span class="footer-brand">Jarvix 👋 Completed</span></div>
                <div style="margin-top: 10px;">
                    ✨ Each analysis is unique and tailored to your specific request
                </div>
            </div>
        </body>
        </html>
        """
        
        pdf_filename = f"Jarvix_Analysis_{base_filename}_{timestamp}.pdf"
        pdf_path = os.path.join(settings.OUTPUT_DIR, pdf_filename)
        
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        HTML(string=html_template).write_pdf(pdf_path)
        
        # Clean up temporary charts
        for chart_path in chart_paths:
            try:
                if os.path.exists(chart_path):
                    os.remove(chart_path)
            except:
                pass
        
        if websocket:
            await websocket.send_json({
                "type": "stream",
                "message": f"\n✅ **PDF Report Generated!** Saved to: `{pdf_path}`\n"
            })
        
        return f"✅ **Analysis Complete!** PDF saved to: `{pdf_path}`"
        
    except Exception as e:
        tb_lines = traceback.format_exc().splitlines()
        error_details = "\n".join(tb_lines[-5:])
        return f"❌ **Data Science Agent Error:** {str(e)}\n\n{error_details}"
