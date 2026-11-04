"""`python -m jobwright.cli` (used by run_daily_brief.sh and generated Hermes wrappers)."""

from jobwright.cli import app

# Keep last: every command is registered when jobwright.cli is imported.
if __name__ == "__main__":
    app()
