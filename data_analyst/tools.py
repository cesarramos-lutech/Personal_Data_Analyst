"""Tools for the Personal Data Analyst agent."""

import os
import sys
from pathlib import Path
from io import StringIO
from typing import Any

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns

from google.adk.tools import ToolContext


# Get data directory from environment or use default
DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()


def list_available_data(tool_context: ToolContext) -> dict[str, Any]:
    """
    List all available data files in the data directory.

    Returns information about CSV and Excel files that can be loaded for analysis.
    """
    if not DATA_DIR.exists():
        return {
            "status": "error",
            "message": f"Data directory not found: {DATA_DIR}",
            "files": []
        }

    files = []
    for ext in ["*.csv", "*.xlsx", "*.xls"]:
        for f in DATA_DIR.glob(ext):
            stat = f.stat()
            files.append({
                "filename": f.name,
                "type": f.suffix[1:].upper(),
                "size_kb": round(stat.st_size / 1024, 2),
            })

    # Store in context for later use
    if tool_context:
        tool_context.state["available_files"] = [f["filename"] for f in files]

    return {
        "status": "success",
        "data_directory": str(DATA_DIR),
        "file_count": len(files),
        "files": files
    }


def load_data(filename: str, tool_context: ToolContext) -> dict[str, Any]:
    """
    Load a data file (CSV or Excel) into memory for analysis.

    Args:
        filename: Name of the file to load (must be in the data directory)
        ctx: Tool context for storing state

    Returns:
        Information about the loaded dataset including shape, columns, and preview.
    """
    filepath = DATA_DIR / filename

    if not filepath.exists():
        return {
            "status": "error",
            "message": f"File not found: {filename}",
            "hint": "Use list_available_data() to see available files"
        }

    try:
        # Load based on file extension
        if filepath.suffix.lower() == ".csv":
            df = pd.read_csv(filepath)
        elif filepath.suffix.lower() in [".xlsx", ".xls"]:
            df = pd.read_excel(filepath)
        else:
            return {
                "status": "error",
                "message": f"Unsupported file type: {filepath.suffix}"
            }

        # Store in context state (as records for JSON serialization)
        dataset_key = f"dataset_{filename.replace('.', '_')}"
        tool_context.state[dataset_key] = df.to_dict(orient="records")
        tool_context.state["current_dataset"] = df.to_dict(orient="records")
        tool_context.state["current_dataset_columns"] = list(df.columns)
        tool_context.state["current_dataset_name"] = filename

        # Generate summary statistics
        summary = {
            "status": "success",
            "filename": filename,
            "shape": {"rows": len(df), "columns": len(df.columns)},
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "missing_values": df.isnull().sum().to_dict(),
            "preview": df.head(5).to_string(),
        }

        # Add numeric summary if applicable
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            summary["numeric_summary"] = df[numeric_cols].describe().to_string()

        return summary

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to load file: {str(e)}"
        }


def run_analysis(code: str, tool_context: ToolContext) -> dict[str, Any]:
    """
    Execute Python code for data analysis.

    The code has access to:
    - pandas (pd), numpy (np), matplotlib.pyplot (plt), seaborn (sns)
    - Any datasets loaded via load_data() (accessible as 'df' for current dataset)
    - The DATA_DIR path for saving outputs

    Args:
        code: Python code to execute
        ctx: Tool context with loaded datasets

    Returns:
        Execution results including any printed output and generated files.
    """
    # Prepare execution environment
    local_vars = {
        "pd": pd,
        "np": np,
        "plt": plt,
        "sns": sns,
        "DATA_DIR": DATA_DIR,
    }

    # Add loaded datasets (from local files, convert from records to DataFrame)
    if "current_dataset" in tool_context.state:
        local_vars["df"] = pd.DataFrame(tool_context.state["current_dataset"])

    # Add BigQuery query results if available (convert from records to DataFrame)
    if "bigquery_query_result" in tool_context.state:
        bq_df = pd.DataFrame(tool_context.state["bigquery_query_result"])
        local_vars["bq_result"] = bq_df
        # Also make it available as df if no local dataset is loaded
        if "df" not in local_vars:
            local_vars["df"] = bq_df

    if "last_query_result" in tool_context.state:
        local_vars["query_result"] = pd.DataFrame(tool_context.state["last_query_result"])

    # Add any other loaded datasets (convert from records to DataFrame)
    for key, value in tool_context.state.items():
        if key.startswith("dataset_") and isinstance(value, list):
            # Make available as clean variable name
            var_name = key.replace("dataset_", "").replace("_csv", "").replace("_xlsx", "")
            local_vars[var_name] = pd.DataFrame(value)

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()

    generated_files = []
    result = None
    error = None

    try:
        # Execute the code
        exec(code, local_vars)

        # Check for any figures and save them
        fig_nums = plt.get_fignums()
        for i, num in enumerate(fig_nums):
            fig = plt.figure(num)
            output_path = DATA_DIR / f"analysis_output_{i+1}.png"
            fig.savefig(output_path, dpi=150, bbox_inches='tight')
            generated_files.append(str(output_path))
        plt.close('all')

        result = {
            "status": "success",
            "output": captured_output.getvalue(),
            "generated_files": generated_files
        }

    except Exception as e:
        error = str(e)
        result = {
            "status": "error",
            "error": error,
            "output": captured_output.getvalue()
        }

    finally:
        sys.stdout = old_stdout

    return result


def get_data_info(tool_context: ToolContext) -> dict[str, Any]:
    """
    Get detailed information about the currently loaded dataset.

    Returns comprehensive statistics and data quality information.
    """
    if "current_dataset" not in tool_context.state:
        return {
            "status": "error",
            "message": "No dataset loaded. Use load_data(filename) first."
        }

    # Convert from records back to DataFrame
    df = pd.DataFrame(tool_context.state["current_dataset"])
    name = tool_context.state.get("current_dataset_name", "unknown")

    info = {
        "status": "success",
        "dataset_name": name,
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "memory_usage_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        "columns": {},
    }

    for col in df.columns:
        col_info = {
            "dtype": str(df[col].dtype),
            "non_null_count": int(df[col].notna().sum()),
            "null_count": int(df[col].isna().sum()),
            "unique_values": int(df[col].nunique()),
        }

        # Add stats for numeric columns
        if pd.api.types.is_numeric_dtype(df[col]):
            col_info.update({
                "min": float(df[col].min()) if not df[col].isna().all() else None,
                "max": float(df[col].max()) if not df[col].isna().all() else None,
                "mean": float(df[col].mean()) if not df[col].isna().all() else None,
                "median": float(df[col].median()) if not df[col].isna().all() else None,
            })

        # Sample values for non-numeric
        else:
            sample_vals = df[col].dropna().head(5).tolist()
            col_info["sample_values"] = sample_vals

        info["columns"][col] = col_info

    return info
