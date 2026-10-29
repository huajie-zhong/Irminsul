---
id: user-errors
title: "User errors"
status: stable
summary: The one error type a command reports as a message and exit status, shared by CLI and MCP server.
describes:
  - "src/irminsul/errors.py"
recommended_tests:
  - "tests/test_cli.py"
---

# User errors

A failure the person who ran the command can act on is a `UserError`: the module that finds the problem raises it with the message and does not print it, so one function serves the CLI and the [MCP server](mcp-server.md), each reporting it its own way. `IrminsulGroup` in [`cli`](cli.md) prints it and exits with its `code`; the MCP tool wrapper hands the message to the agent as a tool error, because the SDK withholds the text of any other exception.

`code` is 2 unless the raise site says otherwise ([One command per question, and one rule per flag](../decisions/one-command-per-question-and-one-rule-per-flag.md)). A remedy that belongs to one caller's flags is part of the error that carries it, as `UnchangedTreeError` ends with the remedy its caller names: the exception is raised complete, not completed where it is caught.

## Scope & Limitations

Only failures with a message the person can act on are user errors; a bug, a broken invariant or an unreadable file that no flag explains stays an ordinary exception and surfaces as a crash in both. A consumer that needs to tell two failures apart reads the subclass.
