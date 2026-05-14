"""
Configuration Center — Single Source of Truth for all environment settings.

Business code MUST NOT call os.getenv directly. Import `cfg` from this module instead.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env: cwd first, then walk up to project root
# ---------------------------------------------------------------------------
load_dotenv()
_script_dir = Path(__file__).resolve().parent
for _parent in list(_script_dir.parents)[:6]:
    _env_file = _parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=True)
        break


class ConfigError(Exception):
    """Raised when a required configuration is missing or invalid."""


def _require(name: str) -> str:
    """Require an environment variable to be set. Fail fast with a helpful message."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"\n{'=' * 60}\n"
            f"  Missing required configuration: {name}\n"
            f"{'=' * 60}\n"
            f"  Please add it to your .env file:\n"
            f"    {name}=<your-value>\n"
            f"  See docs/notion-setup.md for how to obtain this value.\n"
            f"{'=' * 60}"
        )
    return value


def _optional(name: str, default: str = "") -> str:
    """Read an optional environment variable."""
    return os.getenv(name, default).strip()


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NotionConfig:
    token: str
    paper_db_id: str
    queue_db_id: str
    project_db_id: str
    concept_db_id: str

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }


@dataclass(frozen=True)
class ImgurConfig:
    client_id: str

    @property
    def enabled(self) -> bool:
        return bool(self.client_id)


@dataclass(frozen=True)
class AppConfig:
    notion: NotionConfig
    imgur: ImgurConfig
    user_name: str
    research_lines: str
    active_project: str
    papers_dir: Path
    wiki_dir: Path


# ---------------------------------------------------------------------------
# Global singleton — validated at import time
# ---------------------------------------------------------------------------

cfg = AppConfig(
    notion=NotionConfig(
        token=_require("NOTION_TOKEN"),
        paper_db_id=_require("NOTION_PAPER_DB_ID"),
        queue_db_id=_require("NOTION_QUEUE_ID"),
        project_db_id=_require("NOTION_PROJECT_DB_ID"),
        concept_db_id=_require("NOTION_CONCEPT_DB_ID"),
    ),
    imgur=ImgurConfig(
        client_id=_optional("IMGUR_CLIENT_ID"),
    ),
    user_name=_optional("USER_NAME", "Researcher"),
    research_lines=_optional("RESEARCH_LINES"),
    active_project=_optional("ACTIVE_PROJECT"),
    papers_dir=Path(_optional("PAPERS_OUTPUT_DIR", "./papers")),
    wiki_dir=Path(_optional("WIKI_OUTPUT_DIR", "./wiki")),
)
