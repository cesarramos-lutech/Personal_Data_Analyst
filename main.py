"""
Personal Data Analyst - Main Entry Point

A simplified data analyst agent that helps you analyze local CSV and Excel files.

Usage:
    # Interactive CLI mode
    python main.py

    # Or run with ADK CLI
    adk run data_analyst
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ensure data directory exists
data_dir = Path(os.getenv("DATA_DIR", "./data"))
data_dir.mkdir(exist_ok=True)

# Import the agent
from data_analyst import data_analyst_agent


def main():
    """Run the data analyst in interactive mode."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    print("=" * 60)
    print("  Personal Data Analyst")
    print("=" * 60)
    print(f"\nData directory: {data_dir.resolve()}")
    print("Place your CSV/Excel files in this directory to analyze them.")
    print("\nType 'quit' or 'exit' to stop.\n")

    # Create session service and runner
    session_service = InMemorySessionService()
    runner = Runner(
        agent=data_analyst_agent,
        app_name="personal-data-analyst",
        session_service=session_service,
    )

    # Create a session
    session = session_service.create_session(
        app_name="personal-data-analyst",
        user_id="local_user",
    )

    # Interactive loop
    while True:
        try:
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                print("\nGoodbye!")
                break

            # Run the agent
            print("\nAnalyst: ", end="", flush=True)

            response = runner.run(
                user_id="local_user",
                session_id=session.id,
                new_message=user_input,
            )

            # Print the response
            for event in response:
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts'):
                        for part in event.content.parts:
                            if hasattr(part, 'text'):
                                print(part.text, end="")
            print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
