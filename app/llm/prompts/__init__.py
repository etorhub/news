"""Load prompt templates from .txt files."""

from pathlib import Path


def load_prompt(name: str) -> str:
    """Load a prompt template by name. Reads {name}.txt from this directory."""
    dir_path = Path(__file__).resolve().parent
    path = dir_path / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {name}")
    return path.read_text(encoding="utf-8").strip()
