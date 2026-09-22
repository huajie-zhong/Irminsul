# Glossary

## Composer

match: ["Composer"]
forbidden_synonyms: ["request composer"]
case_sensitive: true

The component that turns a request into a plan.

## Planner

match: ["Planner", "planners"]
case_sensitive: false

Finalizes execution order from a draft plan.

## Anti-Glossary

- request — too generic; say what kind
- thing — never use this term in docs

## PlanNode

match: ["PlanNode", "PlanNodes"]
case_sensitive: true

A single step in a plan, always written as a code identifier.
