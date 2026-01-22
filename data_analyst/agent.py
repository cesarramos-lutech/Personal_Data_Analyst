"""Personal Data Analyst Agent definition."""

import os
from google.adk import Agent

from .prompts import get_analyst_instructions
from .tools import (
    list_available_data,
    load_data,
    run_analysis,
    get_data_info,
)
from .bigquery_tools import (
    list_bigquery_datasets,
    list_bigquery_tables,
    get_table_schema,
    run_bigquery_sql,
    preview_table,
)


# Create the data analyst agent
data_analyst_agent = Agent(
    name="personal_data_analyst",
    model=os.getenv("ANALYST_MODEL", "gemini-2.0-flash"),
    description="A personal data analyst that helps you understand and analyze data from local files and BigQuery.",
    instruction=get_analyst_instructions(),
    tools=[
        # Local file tools
        list_available_data,
        load_data,
        get_data_info,
        # BigQuery tools
        list_bigquery_datasets,
        list_bigquery_tables,
        get_table_schema,
        preview_table,
        run_bigquery_sql,
        # Analysis tools
        run_analysis,
    ],
)
