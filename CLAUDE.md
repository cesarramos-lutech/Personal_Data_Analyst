# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules for Claude

- **Always update this file** when making changes to code patterns, architecture, environment variables, or key decisions
- Add new architectural decisions with date prefix `[YYYY-MM-DD]`
- Keep documentation in sync with actual implementation

## Project Overview

Personal Data Analyst is a conversational data analysis agent built with Google ADK (Agent Development Kit). It enables analysis of local CSV/Excel files and BigQuery data through natural language.

## Commands

```bash
# Install dependencies (editable mode)
pip install -e .

# GCP authentication (required for BigQuery)
gcloud auth application-default login

# Run the agent (interactive CLI)
python main.py

# Alternative run modes via ADK CLI
adk run data_analyst          # Interactive
adk web                       # Web UI at localhost:8000
adk api_server               # REST API
```

## Environment Setup

Copy `.env.example` to `.env` and configure:
- `GOOGLE_API_KEY` - Required Gemini API key (get from https://aistudio.google.com/apikey)
- `GOOGLE_CLOUD_PROJECT` - Required GCP project ID (for BigQuery)
- `GOOGLE_CLOUD_LOCATION` - Region (must match your BigQuery dataset location)
- `ANALYST_MODEL` - LLM model (default: gemini-2.0-flash)
- `BIGQUERY_DATASET` - Optional default dataset
- `BIGQUERY_MAX_RESULTS` - Query row limit (default: 10000)
- `DATA_DIR` - Local data directory (default: ./data)

## Architecture

The agent combines 9 tools into a single conversational interface:

**Local File Tools** (`data_analyst/tools.py`):
- `list_available_data()`, `load_data()`, `get_data_info()` - CSV/Excel operations
- `run_analysis()` - Execute Python/pandas code with pre-loaded libraries

**BigQuery Tools** (`data_analyst/bigquery_tools.py`):
- `list_bigquery_datasets()`, `list_bigquery_tables()`, `get_table_schema()`, `preview_table()`, `run_bigquery_sql()`

**Data Flow**: User → Agent → Tools → Data Sources (Local/BigQuery) → Analysis → Output

State is managed via ADK's `ToolContext`, allowing tools to share loaded datasets, schemas, and query results across a session.

## Key Patterns

- **Standardized returns**: All tools return `{"status": "success/error", ...}` dicts
- **Lazy BigQuery client**: Singleton pattern, created on first use
- **SQL safety**: Only SELECT/WITH queries allowed; dangerous keywords blocked; 10GB billing limit
- **Code execution**: `run_analysis()` uses sandboxed `exec()` with pandas, numpy, matplotlib, seaborn pre-loaded
- **Auto-save visualizations**: Matplotlib figures saved to `./data/` with sequential naming
- **ToolContext parameter**: Must be named `tool_context: ToolContext` without default value (no `= None`) for ADK automatic function calling to work
- **State serialization**: DataFrames stored as records (`df.to_dict(orient="records")`) in state, converted back to DataFrame when needed

## Adding New Capabilities

- New analysis tools → `data_analyst/tools.py`
- New BigQuery features → `data_analyst/bigquery_tools.py`
- Agent behavior/prompts → `data_analyst/prompts.py`
- Register new tools → `data_analyst/agent.py` (add to tools list)

## Requirements & Constraints

- Must support both local files (CSV/Excel) and BigQuery as data sources
- All BigQuery queries must be read-only (no INSERT, UPDATE, DELETE, DROP)
- Query results capped at 10,000 rows by default to prevent memory issues
- 10GB billing limit per query for cost control

## Architectural Decisions

- [2025-01-22] Chose Google ADK over LangChain for native GCP integration and simpler Vertex AI deployment
- [2025-01-22] SQL queries restricted to SELECT/WITH with dangerous keyword blocking for security
- [2025-01-22] Using ToolContext for state management to enable tool chaining (load data → analyze → visualize)
- [2025-01-22] Lazy-loaded singleton BigQuery client to avoid unnecessary connections
- [2025-01-26] ToolContext parameters must not have default values (`= None`) - ADK's automatic function calling fails to parse them otherwise
- [2025-01-26] DataFrames stored as records (list of dicts) in ToolContext.state to enable JSON serialization by ADK
