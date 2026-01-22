# Personal Data Analyst

A personal data analyst agent built with Google ADK that helps you analyze both local files (CSV/Excel) and BigQuery data.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Personal Data Analyst Agent                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    Tools Available                     │  │
│  ├───────────────────┬───────────────────────────────────┤  │
│  │   Local Files     │         BigQuery                  │  │
│  ├───────────────────┼───────────────────────────────────┤  │
│  │ • list_available_ │ • list_bigquery_datasets()        │  │
│  │   data()          │ • list_bigquery_tables()          │  │
│  │ • load_data()     │ • get_table_schema()              │  │
│  │ • get_data_info() │ • preview_table()                 │  │
│  │                   │ • run_bigquery_sql()              │  │
│  ├───────────────────┴───────────────────────────────────┤  │
│  │              Analysis (works with both)               │  │
│  │              • run_analysis() - Python/pandas         │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
              │                           │
              ▼                           ▼
     ┌─────────────────┐        ┌─────────────────┐
     │   ./data/       │        │   BigQuery      │
     │  CSV/Excel      │        │   Tables        │
     └─────────────────┘        └─────────────────┘
```

## Features

- **Local File Analysis**: Load and analyze CSV/Excel files
- **BigQuery Integration**: Query and analyze BigQuery tables
- **Python Analysis**: Run pandas, numpy, matplotlib code on any data
- **Visualizations**: Generate charts and save them automatically
- **Safe Queries**: Only SELECT statements allowed (no data modification)

## Quick Start

### 1. Install dependencies

```bash
cd ~/Desktop/"Claude Code projects"/personal-data-analyst
pip install -e .
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your Google Cloud settings:
```
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
ANALYST_MODEL=gemini-2.0-flash
```

### 3. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

### 4. Run the analyst

```bash
python main.py
```

## Example Usage

### BigQuery Analysis

```
You: What BigQuery datasets do I have?

Analyst: Let me check your BigQuery datasets...
Found 3 datasets:
- analytics_data (US)
- sales_data (US)
- marketing_metrics (US)

You: Show me the tables in sales_data

Analyst: Here are the tables in sales_data:
- orders (1.2M rows, 45 MB)
- customers (50K rows, 2 MB)
- products (5K rows, 0.5 MB)

You: What's the total revenue by product category for last month?

Analyst: Let me query that for you...
[Runs SQL query]

Here's the revenue breakdown by category:
- Electronics: $1,234,567
- Clothing: $987,654
- Home & Garden: $543,210
...

You: Create a bar chart of that data

Analyst: [Creates visualization]
I've created a bar chart showing revenue by category.
The chart is saved to ./data/analysis_output_1.png
```

### Local File Analysis

```
You: What local files do I have?

Analyst: Found 1 file in ./data:
- sample_sales.csv (1.2 KB)

You: Load it and show me revenue trends

Analyst: [Loads data and creates visualization]
```

## Tools Reference

### Local File Tools

| Tool | Description |
|------|-------------|
| `list_available_data()` | List CSV/Excel files in data directory |
| `load_data(filename)` | Load a file into memory |
| `get_data_info()` | Get detailed stats on loaded data |

### BigQuery Tools

| Tool | Description |
|------|-------------|
| `list_bigquery_datasets()` | List all datasets in your project |
| `list_bigquery_tables(dataset_id)` | List tables in a dataset |
| `get_table_schema(dataset_id, table_id)` | Get column info for a table |
| `preview_table(dataset_id, table_id, limit)` | Preview rows from a table |
| `run_bigquery_sql(sql)` | Execute a SELECT query |

### Analysis Tools

| Tool | Description |
|------|-------------|
| `run_analysis(code)` | Execute Python code with pandas/numpy/matplotlib |

## Requirements

- Python 3.11+
- Google Cloud project with BigQuery enabled
- `gcloud` CLI authenticated
- Google ADK SDK

## Security

- Only SELECT/WITH queries are allowed
- Dangerous keywords (DELETE, DROP, INSERT, etc.) are blocked
- Query results are limited to 10,000 rows by default
- 10 GB query billing limit per query
