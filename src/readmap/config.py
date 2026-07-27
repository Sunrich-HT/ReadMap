"""Configuration Center — Single Source of Truth for all environment settings.

Business code MUST NOT call os.getenv directly. Import `cfg` from this module instead.

Validation is *lazy*. Requiring every Notion credential at import time meant that
``readmap --help`` crashed on a fresh checkout, and that offline commands which
never touch Notion — parsing a PDF, extracting figures — could not run at all.
A missing credential now fails when it is actually needed, and says which
command needed it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property
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
    """Require an environment variable, failing with a usable message."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"\n{'=' * 60}\n"
            f"  Missing required configuration: {name}\n"
            f"{'=' * 60}\n"
            f"  Add it to your .env file:\n"
            f"    {name}=<your-value>\n"
            f"  See docs/notion-setup.md for how to obtain this value.\n"
            f"  (Commands that do not touch Notion — fetch, figures, compose,\n"
            f"   gate — run without it.)\n"
            f"{'=' * 60}"
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _flag(name: str, default: bool = False) -> bool:
    raw = _optional(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Config sections
# ---------------------------------------------------------------------------

class NotionConfig:
    """Notion credentials, resolved on first use rather than at import."""

    @cached_property
    def token(self) -> str:
        return _require("NOTION_TOKEN")

    @cached_property
    def paper_db_id(self) -> str:
        return _require("NOTION_PAPER_DB_ID")

    @cached_property
    def queue_db_id(self) -> str:
        return _require("NOTION_QUEUE_ID")

    @cached_property
    def project_db_id(self) -> str:
        return _require("NOTION_PROJECT_DB_ID")

    @cached_property
    def concept_db_id(self) -> str:
        return _require("NOTION_CONCEPT_DB_ID")

    @property
    def configured(self) -> bool:
        """Whether Notion is usable, without raising."""
        return all(
            _optional(name)
            for name in (
                "NOTION_TOKEN", "NOTION_PAPER_DB_ID", "NOTION_QUEUE_ID",
                "NOTION_PROJECT_DB_ID", "NOTION_CONCEPT_DB_ID",
            )
        )

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
class FigureConfig:
    """Settings for the figure/table extraction step."""

    dpi: int
    kinds: str
    tiers: str
    enabled: bool


@dataclass(frozen=True)
class AppConfig:
    notion: NotionConfig
    imgur: ImgurConfig
    figures: FigureConfig
    user_name: str
    research_lines: str
    active_project: str
    papers_dir: Path
    wiki_dir: Path

    @property
    def research_line_list(self) -> list[str]:
        return [line.strip() for line in self.research_lines.split(",") if line.strip()]

    def template_vars(self) -> dict[str, str]:
        """Values substituted into prompts and templates.

        The prompts have always carried ``{{USER_NAME}}`` placeholders, and
        nothing ever replaced them — the config read the values and no code
        consumed them, so every user edited the prompt files by hand.
        """
        return {
            "USER_NAME": self.user_name,
            "RESEARCH_LINES": self.research_lines,
            "ACTIVE_PROJECT": self.active_project,
        }


cfg = AppConfig(
    notion=NotionConfig(),
    imgur=ImgurConfig(client_id=_optional("IMGUR_CLIENT_ID")),
    figures=FigureConfig(
        dpi=int(_optional("FIGURE_DPI", "300") or 300),
        kinds=_optional("FIGURE_KINDS", "all"),
        tiers=_optional("FIGURE_TIERS", "A,B,C"),
        enabled=_flag("FIGURE_EXTRACTION", True),
    ),
    user_name=_optional("USER_NAME", "Researcher"),
    research_lines=_optional("RESEARCH_LINES"),
    active_project=_optional("ACTIVE_PROJECT"),
    papers_dir=Path(_optional("PAPERS_OUTPUT_DIR", "./papers")),
    wiki_dir=Path(_optional("WIKI_OUTPUT_DIR", "./wiki")),
)
