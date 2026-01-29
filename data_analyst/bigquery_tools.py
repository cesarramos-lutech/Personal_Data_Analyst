"""BigQuery tools for the Personal Data Analyst agent."""

import os
import re
from typing import Any

from google.cloud import bigquery
from google.adk.tools import ToolContext

# Configuration from environment
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
DATASET_ID = os.getenv("BIGQUERY_DATASET")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
MAX_RESULTS = int(os.getenv("BIGQUERY_MAX_RESULTS", "10000"))

# Lazy-loaded BigQuery client
_bq_client = None


def _get_bq_client() -> bigquery.Client:
    """Get or create BigQuery client."""
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=PROJECT_ID, location=LOCATION)
    return _bq_client


def list_bigquery_datasets(tool_context: ToolContext) -> dict[str, Any]:
    """
    List all available BigQuery datasets in the configured GCP project.

    USE THIS FIRST when the user wants to work with BigQuery data.
    This is the starting point for BigQuery exploration - it shows all
    available datasets before you can list tables or query data.

    Returns:
        dict with status, project ID, dataset count, and list of datasets
        (each with dataset_id, description, and location)

    Next steps after calling this:
        - Use list_bigquery_tables(dataset_id) to see tables in a dataset
    """
    if not PROJECT_ID:
        return {
            "status": "error",
            "message": "GOOGLE_CLOUD_PROJECT environment variable not set"
        }

    try:
        client = _get_bq_client()
        datasets = list(client.list_datasets())

        dataset_list = []
        for dataset in datasets:
            dataset_ref = client.get_dataset(dataset.reference)
            dataset_list.append({
                "dataset_id": dataset.dataset_id,
                "description": dataset_ref.description or "",
                "location": dataset_ref.location,
            })

        tool_context.state["available_datasets"] = [d["dataset_id"] for d in dataset_list]

        return {
            "status": "success",
            "project": PROJECT_ID,
            "dataset_count": len(dataset_list),
            "datasets": dataset_list
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_bigquery_tables(dataset_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """
    List all tables in a specific BigQuery dataset.

    USE THIS after list_bigquery_datasets() to explore what tables are
    available within a dataset. Shows table names, types, row counts, and sizes.

    Args:
        dataset_id: The BigQuery dataset ID (e.g., "my_dataset")

    Returns:
        dict with status, dataset name, table count, and list of tables
        (each with table_id, type, num_rows, size_mb, description)

    Next steps after calling this:
        - Use get_table_schema(dataset_id, table_id) to see column details
        - Use preview_table(dataset_id, table_id) to see sample data
    """
    if not PROJECT_ID:
        return {
            "status": "error",
            "message": "GOOGLE_CLOUD_PROJECT environment variable not set"
        }

    try:
        client = _get_bq_client()
        dataset_ref = f"{PROJECT_ID}.{dataset_id}"
        tables = list(client.list_tables(dataset_ref))

        table_list = []
        for table in tables:
            table_info = client.get_table(table.reference)
            table_list.append({
                "table_id": table.table_id,
                "type": table.table_type,
                "num_rows": table_info.num_rows,
                "size_mb": round(table_info.num_bytes / 1024 / 1024, 2) if table_info.num_bytes else 0,
                "description": table_info.description or "",
            })

        tool_context.state["current_dataset"] = dataset_id
        tool_context.state["available_tables"] = [t["table_id"] for t in table_list]

        return {
            "status": "success",
            "dataset": dataset_id,
            "table_count": len(table_list),
            "tables": table_list
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_table_schema(dataset_id: str, table_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """
    Get the detailed schema of a BigQuery table - column names, types, and descriptions.

    ALWAYS call this before writing SQL queries to understand the table structure.
    This prevents errors from incorrect column names or types.

    Args:
        dataset_id: The BigQuery dataset ID (e.g., "my_dataset")
        table_id: The table name (e.g., "customers")

    Returns:
        dict with status, table name, row count, and list of columns
        (each with name, type, mode, description)

    Next steps after calling this:
        - Use run_bigquery_sql() to query the table with correct column names
        - Use preview_table() if you want to see sample data first
    """
    if not PROJECT_ID:
        return {
            "status": "error",
            "message": "GOOGLE_CLOUD_PROJECT environment variable not set"
        }

    try:
        client = _get_bq_client()
        table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"
        table = client.get_table(table_ref)

        columns = []
        for field in table.schema:
            columns.append({
                "name": field.name,
                "type": field.field_type,
                "mode": field.mode,  # NULLABLE, REQUIRED, REPEATED
                "description": field.description or "",
            })

        # Store schema in context for SQL generation
        schema_key = f"schema_{dataset_id}_{table_id}"
        tool_context.state[schema_key] = columns
        tool_context.state["current_table_schema"] = {
            "dataset": dataset_id,
            "table": table_id,
            "columns": columns
        }

        return {
            "status": "success",
            "table": f"{dataset_id}.{table_id}",
            "num_rows": table.num_rows,
            "num_columns": len(columns),
            "columns": columns,
            "description": table.description or "",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def run_bigquery_sql(sql: str, tool_context: ToolContext) -> dict[str, Any]:
    """
    Execute a SELECT SQL query against BigQuery and return results.

    IMPORTANT: Only SELECT and WITH (CTE) queries are allowed for safety.
    Queries with DELETE, DROP, INSERT, UPDATE, etc. will be rejected.

    ALWAYS call get_table_schema() first to know the correct column names!

    Args:
        sql: The SQL query (SELECT only). Use fully qualified table names:
             `project.dataset.table` or just `dataset.table`

    Returns:
        dict with status, row_count, columns, preview of results, and
        bytes_processed_mb. Results are stored in state for run_analysis().

    SQL Tips:
        - Use LIMIT to control result size
        - Use WHERE clauses to filter early
        - CTEs (WITH clauses) are great for complex queries

    Next steps after calling this:
        - Use run_analysis(code) to do Python/pandas analysis on the results
        - The data is available as 'df', 'bq_result', or 'query_result'
    """
    if not PROJECT_ID:
        return {
            "status": "error",
            "message": "GOOGLE_CLOUD_PROJECT environment variable not set"
        }

    # Safety check - only allow SELECT statements
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        return {
            "status": "error",
            "message": "Only SELECT queries are allowed for safety. Use SELECT or WITH statements."
        }

    # Block dangerous operations - use word boundaries to avoid false positives
    # e.g., "created_at" should NOT match "CREATE", "updated_at" should NOT match "UPDATE"
    dangerous_keywords = ["DELETE", "DROP", "INSERT", "UPDATE", "TRUNCATE", "ALTER", "CREATE"]
    for keyword in dangerous_keywords:
        # \b matches word boundaries, so "CREATE" won't match "created_at"
        pattern = rf'\b{keyword}\b'
        if re.search(pattern, sql_upper):
            return {
                "status": "error",
                "message": f"Query contains forbidden keyword: {keyword}. Only read operations allowed."
            }

    try:
        client = _get_bq_client()

        # Configure query job
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=10 * 1024 * 1024 * 1024,  # 10 GB limit
        )

        # Execute query
        query_job = client.query(sql, job_config=job_config)
        results = query_job.result()

        # Convert to pandas DataFrame
        df = results.to_dataframe()

        # Limit results
        if len(df) > MAX_RESULTS:
            df = df.head(MAX_RESULTS)
            truncated = True
        else:
            truncated = False

        # Store in context for further analysis (as records for JSON serialization)
        tool_context.state["last_query"] = sql
        tool_context.state["last_query_result"] = df.to_dict(orient="records")
        tool_context.state["last_query_columns"] = list(df.columns)
        tool_context.state["bigquery_query_result"] = df.to_dict(orient="records")

        # Get bytes processed
        bytes_processed = query_job.total_bytes_processed or 0

        return {
            "status": "success",
            "sql": sql,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "truncated": truncated,
            "bytes_processed_mb": round(bytes_processed / 1024 / 1024, 2),
            "preview": df.head(10).to_string(),
            "data_available": "Use run_analysis() to further analyze this data"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "sql": sql
        }


def preview_table(dataset_id: str, table_id: str, tool_context: ToolContext, limit: int = 10) -> dict[str, Any]:
    """
    Quick preview of sample rows from a BigQuery table.

    Use this to understand what the data looks like before writing complex queries.
    Faster than get_table_schema() + manual SELECT for initial exploration.

    Args:
        dataset_id: The BigQuery dataset ID (e.g., "my_dataset")
        table_id: The table name (e.g., "customers")
        limit: Number of rows to return (default 10, max 100)

    Returns:
        Same as run_bigquery_sql() - sample rows with metadata

    Next steps after calling this:
        - Use run_bigquery_sql() for filtered/aggregated queries
        - Use run_analysis() for Python analysis on the preview data
    """
    # Enforce reasonable limit
    limit = min(limit, 100)

    sql = f"SELECT * FROM `{PROJECT_ID}.{dataset_id}.{table_id}` LIMIT {limit}"
    return run_bigquery_sql(sql, tool_context)
