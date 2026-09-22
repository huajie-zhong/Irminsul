---
id: references
title: References
status: stable
---

# References

The fields follow Appendix B of the [atom reference](target.md).
The layout follows Appendix A of the [atom reference](target.md).
Every option is listed in the table below.
The retry policy is described in the backoff section below.
See the storage model above.
Quoting the phrase "see the storage model below" is a mention, not a pointer.

```yaml
status: stable   # see status list below
```

| Option | Meaning |
|--------|---------|
| `fast` | Skip checks |

## Retry backoff

Doubles each attempt.

The grammar is in Appendix B of RFC 9110.
The field rules are in Appendix C of [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110).
Our own layout is in Appendix Z of this document.
Appendix Y, see RFC 9110 for the grammar.
