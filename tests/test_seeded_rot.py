"""Seeded rot: does the agent loop lead a reader to a sentence the code just made false?

Each case takes one sentence S of the `seeded-rot` fixture that states something checkable
about its code, changes the code so that S is false, leaves every doc as it was, and runs
the three views the loop in the root `AGENTS.md` names for an uncommitted change:
`check --diff HEAD`, `list review --changed` and `context --after-edit --base-ref HEAD`.
What counts is what those views say after the edit and did not say before it: a finding,
a review-queue item, or one of the claim questions `context --after-edit` asks. The owner
map that command prints is not counted, because it names the owning doc of every changed
file and asks nothing, and neither are its next actions, which repeat the claim questions.
A view the loop does not name for an edit is not run: plain `list review` marks a sentence
whose named code changed after its doc was committed, which `test_list_review.py` covers.

The outcome is one of three:

- `sentence`: something new is reported on S's doc at a line of S's paragraph (S's line and
  the lines joined to it with no blank line between, which is where the anchor marker under
  a paragraph sits), or quotes S, or, where S carries a claim, quotes the claim's text or
  names its id on S's doc.
- `doc`: something new is reported on S's doc, and nothing names S.
- `miss`: nothing new is reported on S's doc.

`today` is the outcome observed when the case was written, with the finding codes and queue
markers that gave it, and the first test holds the tool to both, so recall cannot get worse
unseen. `wanted` is `sentence` for every case. Where the two differ, the second test asserts
`wanted` under a strict `xfail` whose reason names the accepted RFC or the `BACKLOG.md`
entry expected to close the gap, so the change that closes one fails here until it moves
`today`.

The fixture is committed on a fixed day in 2024 and the edit is uncommitted, which reads as
today, so `mtime-drift` sees an owning doc more than its 30 days behind the source in every
case. A doc committed within that threshold would not get the finding.

That a sentence is false after its edit is not taken on trust: each edit carries a probe, an
expression run against the fixture's code, and the value it gives while the sentence holds.

One case's sentence is anchored to a test of the fixture and not to its code. The edit that
makes it false changes nothing the views read, and what says so is the test, which fails.
No view runs a test, so that case carries a second edit, the one its writer must make before
the change can merge: the test is edited to pass again, and the views are judged after both.
The fixture's test is run the way a probe is, and this repository's own test run does not
collect it (`collect_ignore` in `conftest.py`), because it imports a package only the fixture
has.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from .conftest import commit_all, invoke, invoke_json, load_graph, replace_text, seed_repo
from .test_private_docs_siblings import _build_siblings

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "repos" / "seeded-rot"
SEEDED = _dt.datetime(2024, 1, 1, 12, tzinfo=_dt.UTC)

Outcome = Literal["sentence", "doc", "miss"]

LOANS = "docs/components/loans.md"
OVERVIEW = "docs/architecture/overview.md"
GUIDE = "docs/guides/lending.md"
DECISION = "docs/decisions/a-loan-is-renewed-at-most-twice.md"
README = "README.md"

CO_CHANGE = "co-change/unreflected-change"
MTIME_DRIFT = "mtime-drift/drift-detected"
PINNED_DRIFT = "claim-anchor/pinned-drift"
EVIDENCE_DRIFT = "claim-provenance/evidence-drift"
#: The review-queue marker of a claim whose evidence the change touched.
GOVERNING_CLAIM = "governing-claim"
#: The claim questions `context --after-edit` asks, which are not findings and carry no code.
CLAIM_REVIEWS = "claim_reviews"

#: What is expected to close a gap: an accepted RFC under `docs/rfcs/`, or a `BACKLOG.md` entry.
RFC_NAMES_CODE = "RFC a-change-re-asks-the-sentences-that-name-its-code"
BACKLOG_NO_CODE = "BACKLOG.md connected-doc-hides-unconnected-sections"
BACKLOG_GOVERNS = "BACKLOG.md governed-code-does-not-re-ask-its-record"


@dataclass(frozen=True)
class Edit:
    """One change to the fixture's code: the exact `old` text of `path` becomes `new`.

    `probe` is an expression over the fixture's functions, and `holds` what it gives while
    the sentences this edit is aimed at are true; after the edit it gives something else.
    """

    path: str
    old: str
    new: str
    probe: str
    holds: object


CAP = Edit("src/loans/policy.py", "* 25, 500)", "* 25, 800)", "late_fee(100)", 500)
EARLY = Edit("src/loans/policy.py", "max(days_late, 0)", "abs(days_late)", "late_fee(-3)", 0)
RENEWALS = Edit("src/loans/policy.py", "renewals < 2", "renewals < 3", "can_renew(2)", False)
LENGTH = Edit("src/loans/policy.py", "days: int = 14", "days: int = 21", "due_day(0)", 14)
CHECK_OUT = Edit(
    "src/loans/desk.py",
    '"renewals": 0}',
    '"renewals": 1}',
    'check_out("a book", 0)["renewals"]',
    0,
)
RENEW = Edit(
    "src/loans/desk.py",
    'due_day(day), "renewals": loan',
    'due_day(loan["due"]), "renewals": loan',
    'renew({"due": 5, "renewals": 0}, 10)["due"]',
    24,
)
REFUSE = Edit(
    "src/loans/desk.py",
    '    return late_fee(day - loan["due"])\n',
    '    if day - loan["due"] > 365:\n'
    '        raise ValueError("lost")\n'
    '    return late_fee(day - loan["due"])\n',
    'check_in({"due": 0}, 400)',
    500,
)
EDITS = (CAP, EARLY, RENEWALS, LENGTH, CHECK_OUT, RENEW, REFUSE)

#: The edit to the fixture's test of the cap that makes it pass again once `CAP` has made it
#: fail. Its probe calls the test, which gives None when the test passes.
CAP_TEST = Edit("tests/test_loans.py", "== 500", "== 800", "test_fee_is_capped()", None)


@dataclass(frozen=True)
class Case:
    """One sentence and the edit that makes it false.

    `sentence` is S as the doc at `doc` writes it, on one line. `kind` is the connection
    between S and the code `edit` changes. `by` names what gives `today`: finding codes,
    the first marker of a review-queue item, and `claim_reviews`. `claim` is the id of the
    claim S carries, and `closes` what is expected to move `today` to `wanted`. `repair`
    is the edit to the test S's paragraph is anchored to, which `edit` makes fail: it is
    made after `edit` and makes that test pass again.
    """

    id: str
    doc: str
    sentence: str
    edit: Edit
    kind: str
    today: Outcome
    by: tuple[str, ...] = ()
    claim: str | None = None
    wanted: Outcome = "sentence"
    closes: str | None = None
    repair: Edit | None = None


CASES = (
    Case(
        "anchored-paragraph",
        LOANS,
        "A late return is fined 25 cents a day, and the fine stops growing at 5 dollars.",
        CAP,
        "S's paragraph is anchored to the changed function",
        "sentence",
        (PINNED_DRIFT,),
    ),
    Case(
        "anchored-to-a-test",
        GUIDE,
        "The fine for a late book stops growing once it reaches 5 dollars.",
        CAP,
        "S's paragraph is anchored to a test, which the edit makes fail and `repair` passes",
        "sentence",
        (PINNED_DRIFT,),
        repair=CAP_TEST,
    ),
    Case(
        "component-claim",
        LOANS,
        "Renewing starts the loan again from the day of the renewal.",
        RENEW,
        "S carries a claim, in a component doc, whose evidence is the changed file",
        "sentence",
        (GOVERNING_CLAIM, CLAIM_REVIEWS),
        claim="a-renewal-restarts-the-loan",
    ),
    Case(
        "architecture-claim",
        OVERVIEW,
        "Taking a book back always succeeds.",
        REFUSE,
        "S carries a claim, in an architecture doc, whose evidence is the changed file",
        "sentence",
        (EVIDENCE_DRIFT, GOVERNING_CLAIM, CLAIM_REVIEWS),
        claim="a-return-is-never-refused",
    ),
    Case(
        "owner-names-the-function",
        LOANS,
        "`can_renew()` allows a loan two renewals and refuses a third.",
        RENEWALS,
        "S names the changed function in a code span, in the doc that owns the file",
        "doc",
        (CO_CHANGE, MTIME_DRIFT),
        closes=RFC_NAMES_CODE,
    ),
    Case(
        "owner-names-no-code",
        LOANS,
        "A loan runs for two weeks.",
        LENGTH,
        "S names no code, in the doc that owns the file",
        "doc",
        (CO_CHANGE, MTIME_DRIFT),
        closes=BACKLOG_NO_CODE,
    ),
    Case(
        "owner-names-no-code-beside-an-anchor",
        LOANS,
        "A book that comes back early or on its due day costs nothing.",
        EARLY,
        "S names no code, and another paragraph of its doc is anchored to the changed function",
        "doc",
        (PINNED_DRIFT, CO_CHANGE, MTIME_DRIFT),
        closes=BACKLOG_NO_CODE,
    ),
    Case(
        "guide-names-the-function",
        GUIDE,
        "Lend a book with `check_out()`, which returns a loan whose renewal count starts at zero.",
        CHECK_OUT,
        "S names the changed function in a code span, in a guide that owns nothing",
        "miss",
        closes=RFC_NAMES_CODE,
    ),
    Case(
        "guide-names-no-code",
        GUIDE,
        "A reader who brings a book back late never owes more than 5 dollars.",
        CAP,
        "S names no code, in a guide that owns nothing",
        "miss",
        closes=BACKLOG_NO_CODE,
    ),
    Case(
        "readme-names-the-function",
        README,
        "`late_fee()` stops at 5 dollars, however late the book comes back.",
        CAP,
        "S names the changed function in a code span, in a README under `paths.extra_docs`",
        "miss",
        closes=RFC_NAMES_CODE,
    ),
    Case(
        "readme-restates-a-default",
        README,
        "A book is lent for 14 days.",
        LENGTH,
        "S names no code, in a README under `paths.extra_docs`",
        "miss",
        closes=BACKLOG_NO_CODE,
    ),
    Case(
        "decision-governs-the-function",
        DECISION,
        "A loan is renewed at most twice, whoever asks.",
        RENEWALS,
        "S is the Decision of a record whose `governs:` names the changed function",
        "miss",
        closes=BACKLOG_GOVERNS,
    ),
)
GAPS = tuple(case for case in CASES if case.today != case.wanted)


@dataclass(frozen=True)
class Pointer:
    """One thing a view tells a reader: a finding, a review-queue item or a claim question."""

    view: str
    source: str
    path: str | None
    line: int | None
    text: str


@dataclass(frozen=True)
class Seen:
    """The outcome for one sentence, and the sources of the pointers that gave it."""

    outcome: Outcome
    by: tuple[str, ...] = ()


def _seen(outcome: Outcome, *by: str) -> Seen:
    return Seen(outcome, tuple(sorted(by)))


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _squash(text: str) -> str:
    return " ".join(text.split())


def _pointer(view: str, source: str, record: dict[str, object], path: object) -> Pointer:
    line = record.get("line")
    return Pointer(
        view=view,
        source=source,
        path=path if isinstance(path, str) else None,
        line=line if isinstance(line, int) else None,
        text=_squash(" ".join(_strings(record))),
    )


def _views(root: Path) -> list[Pointer]:
    """Everything the three views of the loop say about the uncommitted work at `root`."""
    check = invoke_json(root, "check", "--diff", "HEAD", "--fail-on", "hint,time")
    review = invoke_json(root, "list", "review", "--changed")
    after = invoke_json(root, "context", "--after-edit", "--base-ref", "HEAD")
    return [
        *(_pointer("check", f["code"], f, f["path"]) for f in check["findings"]),
        *(_pointer("review", i["markers"][0], i, i["path"]) for i in review["items"]),
        *(_pointer("after-edit", f["code"], f, f["path"]) for f in after["findings"]),
        *(
            _pointer("after-edit", CLAIM_REVIEWS, r, r["doc"]["path"])
            for r in after["claim_reviews"]
        ),
    ]


def _since(root: Path, before: Sequence[Pointer]) -> list[Pointer]:
    """What the views say now that `before`, the same views taken earlier, did not."""
    return [pointer for pointer in _views(root) if pointer not in before]


def _judge(
    root: Path, new: Sequence[Pointer], doc: str, sentence: str, claim: str | None = None
) -> Seen:
    """Whether `new` leads a reader to the sentence, to its doc, or to neither."""
    lines = (root / doc).read_text(encoding="utf-8").splitlines()
    holding = [number for number, line in enumerate(lines, start=1) if sentence in line]
    assert len(holding) == 1, f"{doc} holds {sentence!r} on {len(holding)} lines, not one"
    first = last = holding[0]
    while first > 1 and lines[first - 2].strip():
        first -= 1
    while last < len(lines) and lines[last].strip():
        last += 1
    paragraph = range(first, last + 1)

    quotes = [_squash(sentence)]
    if claim is not None:
        assert f"claim:{claim}" in lines[holding[0] - 1], f"{sentence!r} carries no claim {claim}"
        node = load_graph(root).doc_at(doc)
        assert node is not None
        quotes.extend(_squash(c.claim) for c in node.frontmatter.claims if c.id == claim)
        assert len(quotes) == 2, f"{doc} declares no claim {claim}"

    def names_sentence(pointer: Pointer) -> bool:
        return pointer.path == doc and (
            pointer.line in paragraph
            or any(quote in pointer.text for quote in quotes)
            or (claim is not None and claim in pointer.text)
        )

    on_sentence = [pointer for pointer in new if names_sentence(pointer)]
    if on_sentence:
        return _seen("sentence", *{pointer.source for pointer in on_sentence})
    on_doc = [pointer for pointer in new if pointer.path == doc]
    if on_doc:
        return _seen("doc", *{pointer.source for pointer in on_doc})
    return _seen("miss")


def _seeded(fixture_repo: Callable[[str], Path]) -> Path:
    """A copy of the fixture, committed whole at one fixed instant."""
    root = fixture_repo("seeded-rot")
    seed_repo(root, "the fixture as it stands", when=SEEDED)
    return root


def _make(root: Path, edit: Edit) -> None:
    replace_text(root, edit.path, edit.old, edit.new)


def _observe(root: Path, case: Case) -> Seen:
    """Make `case`'s edit in the working tree at `root`, then the repair of its test where
    it has one, and judge what that introduced."""
    before = _views(root)
    _make(root, case.edit)
    if case.repair is not None:
        _make(root, case.repair)
    return _judge(root, _since(root, before), case.doc, case.sentence, case.claim)


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_what_leads_to_a_sentence_the_code_made_false(
    case: Case, fixture_repo: Callable[[str], Path]
) -> None:
    assert _observe(_seeded(fixture_repo), case) == _seen(case.today, *case.by), case.kind


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case,
            id=case.id,
            marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=case.closes),
        )
        for case in GAPS
    ],
)
def test_a_sentence_the_code_made_false_is_pointed_at(
    case: Case, fixture_repo: Callable[[str], Path]
) -> None:
    assert _observe(_seeded(fixture_repo), case).outcome == case.wanted, case.kind


def test_every_gap_names_a_live_rfc_or_backlog_entry() -> None:
    """A gap's reason says what is expected to close it, so it has to name an RFC still
    waiting to be implemented or an entry the backlog still holds. When this fails, the case
    is out of date: move its `today` to what the views now report, or point its `closes` at
    whatever is now expected to close the gap."""
    assert all(case.wanted == "sentence" for case in CASES)
    assert [case.id for case in CASES if case.closes is not None] == [case.id for case in GAPS]
    backlog = (REPO_ROOT / "BACKLOG.md").read_text(encoding="utf-8")
    for closes in sorted({case.closes for case in GAPS if case.closes is not None}):
        where, slug = closes.split()
        if where == "RFC":
            rfc = (REPO_ROOT / "docs" / "rfcs" / f"{slug}.md").read_text(encoding="utf-8")
            assert "\nrfc_state: accepted\n" in rfc, (
                f"{slug} is no longer waiting to be built: update the cases that name it"
            )
        else:
            assert where == "BACKLOG.md"
            assert f"\n### `{slug}`\n" in backlog, (
                f"BACKLOG.md no longer holds {slug}: update the cases that name it"
            )


#: The fixture's Python files in the order they run, each with the import of the fixture's
#: own package that one shared namespace stands in for.
_FIXTURE_CODE = (
    ("src/loans/policy.py", None),
    ("src/loans/desk.py", "from loans.policy import can_renew, due_day, late_fee\n"),
    ("tests/test_loans.py", "from loans.policy import late_fee\n"),
)


def _behaviour(probe: str, *edits: Edit) -> object:
    """What `probe` gives against the fixture's code and its test, with `edits` made.

    The files run in one namespace in place of the imports between them, so nothing is
    imported and no bytecode of one run is read by the next. A raised error is an answer too,
    which is how a failing test answers: a probe that calls a test gives None when it passes
    and `AssertionError` when it does not.
    """
    scope: dict[str, object] = {}
    for rel, bridge in _FIXTURE_CODE:
        text = (FIXTURE / rel).read_text(encoding="utf-8")
        if bridge is not None:
            assert text.count(bridge) == 1, f"{rel} holds {bridge!r} {text.count(bridge)} times"
            text = text.replace(bridge, "")
        for edit in edits:
            if edit.path == rel:
                assert text.count(edit.old) == 1, (
                    f"{rel} holds {edit.old!r} {text.count(edit.old)} times"
                )
                text = text.replace(edit.old, edit.new)
        exec(compile(text, rel, "exec"), scope)
    try:
        return eval(probe, scope)
    except Exception as error:
        return type(error).__name__


@pytest.mark.parametrize("edit", EDITS, ids=[edit.probe for edit in EDITS])
def test_each_edit_changes_what_its_sentences_state(edit: Edit) -> None:
    """The oracle. A sentence is false after its edit because the behaviour it states
    changed: an edit to a docstring alone would draw the same pointers and falsify nothing."""
    assert _behaviour(edit.probe) == edit.holds
    assert _behaviour(edit.probe, edit) != edit.holds


def test_every_case_uses_a_probed_edit() -> None:
    assert {case.edit for case in CASES} == set(EDITS)


REPAIRED = tuple(case for case in CASES if case.repair is not None)


@pytest.mark.parametrize("case", REPAIRED, ids=[case.id for case in REPAIRED])
def test_the_edit_fails_the_test_its_sentence_is_anchored_to(case: Case) -> None:
    """The oracle of a sentence anchored to a test. The test passes while the sentence
    holds, the edit that makes the sentence false makes it fail, which is what tells its
    writer, and the repair makes it pass again without making the sentence true."""
    repair = case.repair
    assert repair is not None
    assert _behaviour(repair.probe) == repair.holds
    assert _behaviour(repair.probe, case.edit) == "AssertionError"
    assert _behaviour(repair.probe, case.edit, repair) == repair.holds
    assert _behaviour(case.edit.probe, case.edit, repair) != case.edit.holds


@pytest.mark.parametrize("case", REPAIRED, ids=[case.id for case in REPAIRED])
def test_only_the_repair_of_its_test_points_at_a_sentence_anchored_to_one(
    case: Case, fixture_repo: Callable[[str], Path]
) -> None:
    """No view runs a test, so the edit that makes the sentence false draws nothing on its
    doc. Editing the test to pass again changes what the paragraph is pinned to, and
    `claim-anchor/pinned-drift` then asks about the paragraph."""
    repair = case.repair
    assert repair is not None
    root = _seeded(fixture_repo)
    before = _views(root)

    _make(root, case.edit)
    assert _judge(root, _since(root, before), case.doc, case.sentence) == _seen("miss")

    _make(root, repair)
    seen = _judge(root, _since(root, before), case.doc, case.sentence)
    assert seen == _seen("sentence", PINNED_DRIFT)


def test_the_untouched_fixture_reports_nothing(fixture_repo: Callable[[str], Path]) -> None:
    """The control: with no edit the fixture passes both gates and the three views are empty,
    and stay empty when taken again, so every pointer a case counts is its edit's."""
    root = _seeded(fixture_repo)

    assert invoke(root, "check", "--fail-on", "hint,time")[0] == 0
    assert invoke(root, "check", "--diff", "HEAD", "--fail-on", "hint,time")[0] == 0
    before = _views(root)
    assert before == []
    assert _since(root, before) == []


def test_a_one_word_edit_elsewhere_in_the_owning_doc_clears_the_warning(
    fixture_repo: Callable[[str], Path],
) -> None:
    """Today's behaviour, and the gap `BACKLOG.md` records as
    `connected-doc-hides-unconnected-sections`: `co-change` asks for any edit to the owning
    doc, so one word changed in another section answers it, and `mtime-drift` with it, while
    the sentence the code made false stays as it was. The gate then passes, and the review
    queue holds only the writer's own edit: the reworded sentence and the doc's summary."""
    case = next(case for case in CASES if case.id == "owner-names-no-code")
    root = _seeded(fixture_repo)
    before = _views(root)
    replace_text(root, case.edit.path, case.edit.old, case.edit.new)
    warned = _judge(root, _since(root, before), case.doc, case.sentence)
    assert warned == _seen("doc", CO_CHANGE, MTIME_DRIFT)

    replace_text(root, case.doc, "keeps no record", "holds no record")

    left = _since(root, before)
    assert _judge(root, left, case.doc, case.sentence) == _seen("doc", "edited", "stale-summary")
    assert {pointer.view for pointer in left} == {"review"}
    assert invoke(root, "check", "--diff", "HEAD", "--fail-on", "hint,time")[0] == 0


@pytest.mark.parametrize(
    ("days_later", "seen"),
    [(1, _seen("miss")), (40, _seen("doc", MTIME_DRIFT))],
    ids=["the next day", "past the mtime-drift threshold"],
)
def test_a_change_committed_in_the_sibling_code_repository(
    tmp_path: Path, days_later: int, seen: Seen
) -> None:
    """Today's behaviour in the `siblings` layout: the three views read the docs
    repository's own change, so a sentence of the owning doc that a commit in the code
    repository made false is reported by nothing, until the code is more than
    `mtime-drift`'s 30 days ahead of the doc, and then only the doc is named."""
    docs = _build_siblings(tmp_path, doc_when=SEEDED, code_when=SEEDED)
    doc, sentence = "docs/components/core.md", "`f()` returns 1."
    replace_text(docs, doc, "The core module.", f"The core module. {sentence}")
    commit_all(docs, "say what f returns", when=SEEDED)
    before = _views(docs)
    assert before == []

    code = docs.parent / "code"
    replace_text(code, "src/core.py", "return 1", "return 2")
    commit_all(code, "f returns 2", when=SEEDED + _dt.timedelta(days=days_later))

    assert _judge(docs, _since(docs, before), doc, sentence) == seen
