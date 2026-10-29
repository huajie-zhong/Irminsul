---
id: good-large
title: A large RFC in the two-part layout
status: stable
summary: A large RFC in the two-part layout.
describes: []
rfc_state: accepted
affects: []
resolved_by: docs/decisions/pick.md
required_updates: []
weight: large
---

# A large RFC in the two-part layout

## Summary

An export gains a header row, so its columns are named. One decision waits for you.

## Problem

Today `export` writes only record rows, so a reader of a two-column file cannot tell which
column holds the name and which the date.

## How it works

The export writes a header row, then one row per record.

## Cost and risk

One writer function and its test.

## Decisions

1. Header or none. Recommended: a header.

## Design detail

The writer lives in `export.py`.

## Requirements

No new behavioral requirements: a fixture.

## Tasks

<!-- none -->

## Resolution

Accepted.
