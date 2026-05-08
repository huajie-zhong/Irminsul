---
id: leaky
title: Leaky
audience: explanation
tier: 3
status: stable
owner: "@anson"
last_reviewed: 2026-05-07
describes:
  - app/thing.py
---

# Leaky

This component doc accidentally pastes a Pydantic model and an interface,
which both belong in `40-reference/`.

```python
class Thing(BaseModel):
    name: str
```

And here is some TS:

```typescript
interface Thing {
  name: string;
}
```

But this fenced block is `toml` and should be ignored:

```toml
[section]
class = "ok"
interface = "ok"
```
