"""Load Athenaeum module content (the markdown the Modules tab renders).

Content files live in the sibling ``athenaeum`` package, one markdown file per
module with YAML-ish frontmatter carrying its ``id``. We index by that id so a
``module_id`` (e.g. ``cb-c01-m01``) maps to its title + rendered-ready body.
Read-only; cached per resolved content root.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_ID = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)
_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)


def _content_root() -> Path:
    # content.py -> catalog -> app -> backend -> ayanakoji
    return Path(__file__).resolve().parents[3] / "athenaeum" / "content"


@dataclass(frozen=True)
class ModuleContent:
    """One module's title + markdown body (frontmatter stripped)."""

    module_id: str
    title: str
    body: str


@lru_cache(maxsize=4)
def _index(root_str: str) -> dict[str, ModuleContent]:
    root = Path(root_str)
    index: dict[str, ModuleContent] = {}
    for path in root.rglob("module-*.md"):
        match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
        if not match:
            continue
        front, body = match.group(1), match.group(2).strip()
        id_match = _ID.search(front)
        if not id_match:
            continue
        title_match = _TITLE.search(front)
        module_id = id_match.group(1)
        title = title_match.group(1).strip().strip('"') if title_match else module_id
        index[module_id] = ModuleContent(module_id=module_id, title=title, body=body)
    return index


def get_module_content(module_id: str) -> ModuleContent | None:
    """Title + markdown body for a module, or None if there is no content file."""
    return _index(str(_content_root())).get(module_id)
