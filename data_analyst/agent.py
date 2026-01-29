"""Personal Data Analyst Agent definition."""

import os
import logging
from typing import Optional

from google.adk import Agent
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest
from google.adk.planners import BuiltInPlanner
from google.genai.types import Content, ThinkingConfig, GenerateContentConfig

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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Callbacks for observability and debugging
async def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Log before each LLM call for debugging."""
    # Log the number of messages being sent
    if llm_request.contents:
        msg_count = len(llm_request.contents)
        logger.debug(f"Sending {msg_count} messages to LLM")
    return None  # Continue with normal execution


async def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """Log after each LLM response for debugging."""
    # Log if the model wants to use tools
    if llm_response.content and llm_response.content.parts:
        for part in llm_response.content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                logger.info(f"Agent calling tool: {part.function_call.name}")
    return None  # Continue with normal execution


async def before_agent_callback(
    callback_context: CallbackContext
) -> Optional[Content]:
    """Called before the agent starts processing."""
    logger.debug("Agent starting to process request")
    return None  # Continue with normal execution


# Model configuration
DEFAULT_MODEL = "gemini-2.5-flash"  # Upgraded from 2.0-flash for better reasoning
MODEL = os.getenv("ANALYST_MODEL", DEFAULT_MODEL)

# Enable thinking/planning for complex analysis tasks
ENABLE_PLANNING = os.getenv("ENABLE_PLANNING", "true").lower() == "true"
THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "8192"))  # Tokens for reasoning

# Build planner config if enabled
planner = None
if ENABLE_PLANNING:
    planner = BuiltInPlanner(
        thinking_config=ThinkingConfig(
            thinking_budget=THINKING_BUDGET,
            include_thoughts=False,  # Don't show internal reasoning to user
        )
    )

# Generation config for consistent, high-quality responses
generate_config = GenerateContentConfig(
    temperature=0.1,  # Low temperature for analytical accuracy
    top_p=0.95,
)

# Create the data analyst agent
data_analyst_agent = LlmAgent(
    name="personal_data_analyst",
    model=MODEL,
    description="A personal data analyst that helps you understand and analyze data from local files (CSV/Excel) and Google BigQuery through natural language conversation.",
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
    # Planning for complex multi-step analysis
    planner=planner,
    # Generation settings
    generate_content_config=generate_config,
    # Callbacks for observability
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
    before_agent_callback=before_agent_callback,
)
