---
id: check-pipeline
title: Check Pipeline
status: stable
summary: How `irminsul check` flows from invocation to exit code.
describes: []
---

# Check Pipeline

How `irminsul check` flows from CLI invocation to exit code. The order matters because each stage decides what the next one can see; what each stage does is in the docstrings of `src/irminsul/checks/pipeline.py`.

1. **Build the graph.** The config is resolved and `build_graph` produces the one `DocGraph` every check receives.
2. **Run the checks.** The selected checks run first, then the passes no configuration can omit and, given a diff range, the passes that judge the change. None of them mutates the graph.
3. **Apply ignore comments, then classes, then the trailer step, then answers.** A doc's `irminsul:ignore` comments drop the hint and time findings they cover before classes apply, because which findings a comment may drop is set by the class a code declares, never by the severity a check chose. Classes then decide which findings are errors: a certain finding is one unless it sits on a draft doc and its code reports an unfinished doc ([drafts excuse an unfinished doc](../decisions/finding-classes-decide-what-blocks.md)), and a diff range drops time findings. The trailer step then accepts each finding that an `Irminsul-Reviewed` trailer of the change names by code, path and subject, and whose code declares `trailer`: it stays at info under its own code. Last, the suggestion of each finding whose code answers on its line names the ignore comment that waives it, and of each finding whose code answers by trailer names the trailer that signs it off.
4. **Sort, then filter.** Findings are sorted by severity, then path. A baseline then hides the findings it records, or `--delta` keeps only those the base revision lacks.
5. **Exit code.** `RunResult.failed` is the one pass/fail rule, and the exit code is the same for every output format.

## Scope & Limitations

This doc covers `irminsul check` only. The init and fix pipelines are not documented here.
