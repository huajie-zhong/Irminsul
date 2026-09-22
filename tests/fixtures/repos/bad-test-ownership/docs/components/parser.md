---
id: parser
title: Parser
status: stable
describes:
  - parser/parser.go
owns_tests:
  - parser/parser_test.go
recommended_tests:
  - parser/
---

# Parser

Owns its colocated test. `parser/scanner_test.go` sits beside it with no owner, which is
what `unowned-test` reports.
