"""Personal Data Analyst Agent Package."""

from .agent import data_analyst_agent

# ADK expects 'root_agent' for discovery
root_agent = data_analyst_agent

__all__ = ["data_analyst_agent", "root_agent"]
