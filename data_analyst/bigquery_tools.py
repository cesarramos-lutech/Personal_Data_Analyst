"""BigQuery tools for the Personal Data Analyst agent."""

import os
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
    List all available BigQuery datasets in the configured project.

    Returns a list of datasets with their IDs and descriptions.
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
    List all tables in a BigQuery dataset.

    Args:
        dataset_id: The BigQuery dataset ID to list tables from
        ctx: Tool context

    Returns:
        List of tables with their names, types, and row counts.
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
    Get the schema of a BigQuery table.

    Args:
        dataset_id: The BigQuery dataset ID
        table_id: The table ID to get schema for
        ctx: Tool context

    Returns:
        Table schema with column names, types, and descriptions.
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
    Execute a SQL query against BigQuery and return results.

    Args:
        sql: The SQL query to execute (SELECT statements only for safety)
        ctx: Tool context

    Returns:
        Query results as a list of dictionaries, plus metadata.
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

    # Block dangerous operations
    dangerous_keywords = ["DELETE", "DROP", "INSERT", "UPDATE", "TRUNCATE", "ALTER", "CREATE"]
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
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

        # Store in context for further analysis
        tool_context.state["last_query"] = sql
        tool_context.state["last_query_result"] = df
        tool_context.state["bigquery_query_result"] = df  # Compatible with analytics tools

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
    Preview rows from a BigQuery table.

    Args:
        dataset_id: The BigQuery dataset ID
        table_id: The table ID to preview
        limit: Number of rows to return (max 100)
        ctx: Tool context

    Returns:
        Sample rows from the table.
    """
    # Enforce reasonable limit
    limit = min(limit, 100)

    sql = f"SELECT * FROM `{PROJECT_ID}.{dataset_id}.{table_id}` LIMIT {limit}"
    return run_bigquery_sql(sql, tool_context)
