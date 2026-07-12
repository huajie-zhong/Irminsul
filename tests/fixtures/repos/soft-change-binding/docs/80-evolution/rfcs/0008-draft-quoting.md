---
id: 0008-draft-quoting
title: Draft RFC quoting the requirement grammar
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects: []
---

# RFC 0008: Quoting the grammar

Quotes a fenced grammar example inside a wider fence, the standard markdown
idiom for showing content that itself contains fences.

## Design

````markdown
## Requirements

### Requirement: Quoted
ID: quoted
Provenance: code

The system SHALL do nothing; this block is an example, not a contract.

#### Scenario: Quoted scenario
- **WHEN** an RFC quotes the grammar
- **THEN** the parser ignores the quoted block

```
a nested fence inside the quoted example
```
````

## Requirements

No new behavioral requirements: this proposal only documents the grammar.
