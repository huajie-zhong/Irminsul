"""Literal placeholder phrases written by `irminsul init --fresh`.

These are the verbatim prompt strings the fresh scaffold writes into the
foundation and architecture docs (`scaffolds/docs/00-foundation/principles.md.j2`
and `scaffolds/docs/10-architecture/overview.md.j2`). They live here, alongside
the scaffolds, so the `foundation-readiness` check and the `seed` command can
detect an un-filled scaffold without duplicating the strings. `tests/
test_init_placeholders.py` asserts every phrase still appears verbatim in the
scaffold templates so the two never drift.
"""

from __future__ import annotations

SCAFFOLD_PLACEHOLDER_PHRASES: tuple[str, ...] = (
    # docs/00-foundation/principles.md
    "Replace this paragraph with your own principle, idea, or belief about the app",
    "What do you believe this app should make possible?",
    "Who should it serve first?",
    "What should stay true even if features change later?",
    "What is this system for?",
    "What is this system explicitly not for?",
    "we prefer X over Y because of goal Z",
    # docs/10-architecture/overview.md
    "What this system does, in one sentence.",
    "Why we depend on it.",
    "Replace the diagram and prose to match your system",
)
