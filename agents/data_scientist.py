import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from jinja2 import Environment, FileSystemLoader
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

# --- CONFIGURATION ---
genai.configure(api_key=settings.GOOGLE_API_KEY)
USER_HOME = os.path.expanduser('~')
OUTPUT_DIR = os.path.join(USER_HOME, 'Desktop')
TEMP_CHART_DIR = os.path.join(OUTPUT_DIR, 'jarvix_temp_charts')
os.makedirs(TEMP_CHART_DIR, exist_ok=True)

# Safety settings for Jarvix API calls to prevent unnecessary blocking.
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# --- DYNAMIC MULTI-STEP AI ANALYSIS ---
def get_ai_plan(df_head: str, columns: List[str], df_stats: str = "") -> Dict[str, Any]:
    """Step 1: Ask Jarvix to create a strategic plan as a JSON object."""
    model = genai.GenerativeModel('gemini-flash-latest')
    prompt = f"""
You are an expert strategic data analyst and business intelligence specialist. Based on the data preview, columns, and statistics, create a comprehensive analysis plan.

**Data Preview (df.head()):**
{df_head}

**Data Statistics:**
{df_stats}

**Columns available:**
{columns}

**Your output MUST be a valid JSON object** with three keys:
1.  `"strategic_recommendations"`: A list of 4-6 strings with specific, actionable advice (e.g., "Identify trends in 'column_X'", "Segment data by 'column_Y'", "Detect outliers in 'column_Z'").
2.  `"feature_engineering_code"`: A string containing Python code to preprocess the data and create new features. This code will modify the DataFrame `df`. IMPORTANT: Only use variables that are already defined (df, pd, np, os). Do NOT reference variables that don't exist. Each line should be self-contained and not depend on variables created in previous lines unless you explicitly create them.
3.  `"visualization_code"`: A string containing Python code to generate 4-5 INSIGHTFUL visualizations. CRITICAL: Only use plt (matplotlib) functions like plt.figure(), plt.plot(), plt.hist(), plt.bar(), plt.scatter(), plt.boxplot(), sns.heatmap(), sns.countplot(). NEVER use sns.pie() - use plt.pie() instead. NEVER use functions that don't exist. Save each chart with plt.savefig(path, dpi=150, bbox_inches='tight'), append to chart_paths, then call plt.close().

Example JSON output structure:
```json
{{
    "strategic_recommendations": [
        "Browser and device distribution shows high mobile traffic",
        "Identify top IP addresses and geographic patterns",
        "Analyze referrer sources to understand traffic channels",
        "Examine temporal patterns in user access",
        "Correlation between device type and user engagement"
    ],
    "feature_engineering_code": "df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')\\ndf['hour'] = df['timestamp'].dt.hour\\ndf['day_of_week'] = df['timestamp'].dt.day_name()\\ndf['is_mobile_or_tablet'] = df['is_mobile'] | df['is_tablet']",
    "visualization_code": "plt.figure(figsize=(14, 6))\\nplt.hist([df[df['is_mobile']==True].shape[0], df[df['is_pc']==True].shape[0]], label=['Mobile', 'PC'])\\nplt.title('Device Type Distribution', fontsize=16, fontweight='bold')\\nplt.xlabel('Device Type', fontsize=12)\\nplt.ylabel('Count', fontsize=12)\\nchart_path = os.path.join(TEMP_CHART_DIR, '01_devices.png')\\nplt.savefig(chart_path, dpi=150, bbox_inches='tight')\\nchart_paths.append(chart_path)\\nplt.close()\\n\\nplt.figure(figsize=(14, 6))\\nbrowser_counts = df['browser'].value_counts().head(10)\\nplt.bar(range(len(browser_counts)), browser_counts.values)\\nplt.title('Top 10 Browsers', fontsize=16, fontweight='bold')\\nplt.xticks(range(len(browser_counts)), browser_counts.index, rotation=45)\\nchart_path = os.path.join(TEMP_CHART_DIR, '02_browsers.png')\\nplt.savefig(chart_path, dpi=150, bbox_inches='tight')\\nchart_paths.append(chart_path)\\nplt.close()"
}}

**CRITICAL RULES - MATPLOTLIB VISUALIZATION FUNCTIONS ONLY:**
- Use ONLY these functions: plt.figure(), plt.plot(), plt.bar(), plt.hist(), plt.scatter(), plt.boxplot(), plt.pie(), plt.xlim(), plt.ylim(), plt.title(), plt.xlabel(), plt.ylabel(), plt.xticks(), plt.legend()
- Use sns.heatmap() and sns.countplot() from seaborn when appropriate
- NEVER use sns.pie() - use plt.pie() instead
- NEVER use functions that don't exist in matplotlib/seaborn
- Always save with: plt.savefig(path, dpi=150, bbox_inches='tight') then plt.close()
- Only use variables: df, pd, np, plt, sns, os, TEMP_CHART_DIR, chart_paths
- Create new columns in df during feature engineering
- Each visualization should have a clear title and axis labels
"""
    try:
        response = model.generate_content(prompt, safety_settings=SAFETY_SETTINGS)
        # Clean the response to ensure it's valid JSON
        json_text_match = re.search(r'```json\n([\s\S]*?)```', response.text)
        if not json_text_match:
            # Try plain text search if the markdown block is missing
            json_text_match = re.search(r'\{[\s\S]*\}', response.text)
        
        if not json_text_match:
            raise ValueError("AI response did not contain a valid JSON block.")
        
        json_text = json_text_match.group(0).replace('```json\n', '').replace('```', '')
        plan = json.loads(json_text)
        return plan
    except (ValueError, AttributeError, json.JSONDecodeError) as e:
        raise ValueError(f"Failed to parse AI plan. Jarvix's raw response might be invalid. Error: {e}\nResponse: {response.text}")

# --- REPORTING ---
def generate_pdf_report(base_dir: Path, csv_path: str, summary: Dict[str, Any], charts: List[str]) -> str:
    """Generates a PDF report from the analysis results."""
    templates_dir = base_dir / "templates_pdf"
    env = Environment(loader=FileSystemLoader(templates_dir))

    try:
        template = env.get_template('professional_report_template.html')
    except Exception as e:
        raise FileNotFoundError(f"Could not find 'professional_report_template.html' in '{templates_dir}'. Error: {e}")

    now = datetime.now()
    base_path = Path(csv_path)
    dataset_slug = base_path.stem
    dataset_label = dataset_slug.replace('_', ' ').replace('-', ' ').title()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    template_vars = {
        "report_title": f"Automated Analysis of {base_path.name}",
        "custom_title": f"Jarvix Insights · {dataset_label}",
        "generation_date": now.strftime("%Y-%m-%d %H:%M:%S"),
        "file_name": base_path.name,
        "file_path": csv_path,
        "strategic_recommendations": summary.pop('strategic_recommendations', []),
        "analysis_summary": summary,
        "chart_paths": charts
    }
    html_out = template.render(template_vars)
    report_filename = f"Jarvix_Report_{dataset_slug}_{timestamp}.pdf"
    report_path = os.path.join(OUTPUT_DIR, report_filename)
    HTML(string=html_out, base_url=str(TEMP_CHART_DIR)).write_pdf(report_path)
    return report_path

# --- MAIN PIPELINE ---
def run_dynamic_analysis(base_dir: Path, file_path: str) -> str:
    """The main multi-step function Jarvix will call."""
    try:
        # Ensure TEMP_CHART_DIR exists before starting analysis
        os.makedirs(TEMP_CHART_DIR, exist_ok=True)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at '{file_path}'.")
        df = pd.read_csv(file_path) if file_path.endswith('.csv') else pd.read_excel(file_path)

        # --- STEP 0: GATHER ENHANCED STATISTICS ---
        df_stats = df.describe().to_string()
        
        # --- STEP 1: GET THE AI'S STRATEGIC PLAN ---
        ai_plan = get_ai_plan(df.head().to_string(), list(df.columns), df_stats)
        feature_engineering_code = ai_plan.get("feature_engineering_code", "")
        visualization_code = ai_plan.get("visualization_code", "")
        strategic_recommendations = ai_plan.get("strategic_recommendations", [])

        # --- STEP 2: EXECUTE FEATURE ENGINEERING ---
        # Create a safe savefig wrapper that ensures directories exist
        original_savefig = plt.savefig
        def safe_savefig(*args, **kwargs):
            """Wrapper for plt.savefig that ensures parent directory exists."""
            if args:
                filepath = args[0]
                parent_dir = os.path.dirname(filepath)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
            return original_savefig(*args, **kwargs)
        
        # Monkey-patch plt.savefig to use our safe version
        plt.savefig = safe_savefig
        
        local_scope = {
            'df': df, 'pd': pd, 'plt': plt, 'sns': sns, 'np': np, 'os': os,
            'TEMP_CHART_DIR': TEMP_CHART_DIR, 'chart_paths': [],
            'analysis_summary': {"strategic_recommendations": strategic_recommendations}
        }
        if feature_engineering_code:
            try:
                exec(feature_engineering_code, globals(), local_scope)
            except NameError as e:
                error_msg = f"NameError in feature engineering code: {str(e)}. The code tried to use a variable that doesn't exist."
                return f"❌ **Feature Engineering Error:** {error_msg}\n\nPlease ensure the code only uses variables that are already defined (df, pd, np, os)."
            except Exception as e:
                error_msg = f"Error in feature engineering code: {str(e)}"
                return f"❌ **Feature Engineering Error:** {error_msg}"
        
        # --- STEP 3: EXECUTE VISUALIZATIONS ---
        if visualization_code:
            # Ensure chart_paths list exists in local scope
            if 'chart_paths' not in local_scope:
                local_scope['chart_paths'] = []
            try:
                exec(visualization_code, globals(), local_scope)
            except NameError as e:
                error_msg = f"NameError in visualization code: {str(e)}. The code tried to use a variable that doesn't exist."
                return f"❌ **Visualization Error:** {error_msg}\n\nPlease ensure the code only uses variables that are already defined (df, pd, np, plt, sns, os, TEMP_CHART_DIR, chart_paths)."
            except Exception as e:
                error_msg = f"Error in visualization code: {str(e)}"
                return f"❌ **Visualization Error:** {error_msg}"

        # Restore original plt.savefig
        plt.savefig = original_savefig

        chart_paths = local_scope.get('chart_paths', [])
        analysis_summary = local_scope.get('analysis_summary', {})
        if not chart_paths:
             return "⚠️ **Warning:** The AI-generated plan did not produce any valid chart files."

        # --- STEP 4: GENERATE PDF ---
        report_path = generate_pdf_report(base_dir, file_path, analysis_summary, chart_paths)
        
        # Clean up temporary chart images
        for path in chart_paths:
            if os.path.exists(path): os.remove(path)
        
        return f"👍 **Success:** AI-driven analysis is complete. Strategic report saved to: `{report_path}`"
    except Exception:
        tb_lines = traceback.format_exc().splitlines()
        error_details = "\n".join(tb_lines)
        return f"❌ **Data Science Agent Error:** A critical error occurred.\n<pre><code>{error_details}</code></pre>"