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
| 2026-09-22 | 484ecf7 | dependency | in-loop | agent-critique | pyproject.toml pinned `modelcluster==6.3`, a package name that does not exist on PyPI, so the dependency set looked complete but could never install. | Renamed the pin to `django-modelcluster==6.3` and verified every other dependency name and version against PyPI. | no |
| 2026-09-22 | 6947cc5 | scope | in-loop | agent-critique | Templates rendered a contact email and a years-of-experience figure as confirmed fact, for items §8 lists as open, with a wrong settings-model reference guaranteeing the invented values always rendered. | Corrected the settings model reference and replaced every invented value with a visible placeholder or an omitted element. | no |
| 2026-09-22 | 80b12e5 | architecture | in-loop | agent-critique | The scaffold looked complete but no page could render: templates reversed URL names that were never created, page models named no template file, and the two layers used different field names for the same data. | Moved page links onto Wagtail page routing, set the real template path on every page model, created URLs only for genuine form endpoints, and conformed templates to the authoritative model fields. | no |
| 2026-09-22 | dc2c98c | correctness | in-loop | agent-critique | The mobile nav looked correct and matched the locked design, but was hidden by CSS until JavaScript ran, leaving no-JS mobile visitors unable to navigate at all. | Replaced the JS-only disclosure with a checkbox-and-label mechanism that works with scripting disabled, preserving the locked appearance and the existing JS-on behaviour. | no |
| 2026-09-22 | 9bc47ea | correctness | in-loop | agent-critique | Two agent definitions I wrote asserted a specific contrast pair was risky and instructed agents to check it, when the pair measures 8.12:1 and was never at risk. | Replaced the claim in both definitions with the measured ratios for the whole palette and redirected the audit attention to pairs that are genuinely unverified. | yes |

<!-- Append one row per Oversight- trailered commit, newest last. Do not add
     illustrative or placeholder rows: a false entry is worse than a missing
     one. Never edit or remove a row that is already here. -->
