"""The level-2 sections a record's body must carry, read once for the checks that name them.

`adr-structure` and `rfc-structure` each list the sections their record needs, and this module
answers the same three questions of either list: which is absent, which is repeated, and which
holds nothing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from irminsul.docgraph import DocNode
from irminsul.docgraph_index import Heading, extract_section
from irminsul.init.placeholders import placeholder_lines

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKDOWN_DECORATION_RE = re.compile(r"[\s`*_>#.\-:;!?]+")


@dataclass(frozen=True)
class RequiredSection:
    slug: str
    """The heading's slug, which is how a heading is matched whatever its case."""
    title: str
    """The heading text a finding names."""
    substantive: bool = False
    """Whether the section must say something beyond comments and marked prompts."""


@dataclass(frozen=True)
class SectionGap:
    section: RequiredSection
    kind: Literal["missing", "duplicate", "empty"]
    line: int | None
    """The body line of the heading at fault: the second of a duplicate, the first of an
    empty one, and none for a section that is absent."""


def section_gaps(
    node: DocNode, headings: Sequence[Heading], required: Sequence[RequiredSection]
) -> list[SectionGap]:
    """What `node`'s body lacks of `required`, in the order `required` lists the sections.

    Only a heading of level 2 counts, and `headings` are the body's parsed headings, so a
    heading in a fence or a comment satisfies nothing.
    """
    gaps: list[SectionGap] = []
    for section in required:
        matches = [h for h in headings if h.level == 2 and h.slug == section.slug]
        if not matches:
            gaps.append(SectionGap(section, "missing", None))
        elif len(matches) > 1:
            gaps.append(SectionGap(section, "duplicate", matches[1].line))
        if matches and section.substantive and not _has_substance(node, section.slug):
            gaps.append(SectionGap(section, "empty", matches[0].line))
    return gaps


def _has_substance(node: DocNode, slug: str) -> bool:
    """Whether the section says anything beyond comments and marked prompts.

    What the words say is the reader's to judge: a prompt counts as one only when the
    template that wrote it marked it.
    """
    section = extract_section(node.body, slug)
    if section is None:
        return False
    raw = "\n".join(line for _, line in section.lines)
    covered = set(placeholder_lines(raw))
    unmarked = "\n".join(
        line for number, line in enumerate(raw.splitlines(), start=1) if number not in covered
    )
    without_comments = _HTML_COMMENT_RE.sub("", unmarked)
    return bool(_MARKDOWN_DECORATION_RE.sub(" ", without_comments).strip())
