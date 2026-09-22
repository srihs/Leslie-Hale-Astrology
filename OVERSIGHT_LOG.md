# Oversight log

Research data for a PhD on human oversight in agentic software development.

Every row is an OVERSIGHT EPISODE: a point where a human correction changed,
or deliberately declined to change, what an agent produced. Each row
corresponds to exactly one commit carrying `Oversight-` git trailers; the
commit is the primary record and this table is the index over it. The rules
that govern what counts are in the "Oversight capture" section of
`CLAUDE.md`.

Rows are appended in commit order and are never edited or deleted, including
when a later episode contradicts an earlier one. Superseded entries stay, so
the sequence of corrections remains visible.

Two kinds of row are easy to lose and must not be:

- **Post-handover episodes** (`Stage: acceptance` or `production`). Anything
  caught after delivery is something in-loop review let through, which is the
  measurement this study turns on.
- **Overruled critiques** (`Type: critique-override`, `Durable: no`). When an
  agent review surfaces something judged wrong, or right but not worth acting
  on, no code changes — the episode is recorded by committing the review
  document with the adjudication written into it. These rows exist precisely
  because nothing was fixed.

The baseline commit (`6b40a5f`, 22 September 2026) and the commit that added
this capture mechanism carry no trailers and appear in no row. Work predating
instrumentation has no episodes recorded, and that absence is a property of
the period, not a finding about it.

| Date | Commit | Type | Stage | Source | What looked right but was not | What was done | Durable |
| --- | --- | --- | --- | --- | --- | --- | --- |

<!-- No episodes recorded yet. Append one row per Oversight- trailered commit,
     newest last. Do not add illustrative or placeholder rows: a false entry
     is worse than a missing one. -->
