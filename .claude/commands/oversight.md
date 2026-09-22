---
description: Record an oversight episode as its own trailered commit and log row
argument-hint: [what I caught, in your own words — any trailer values you already know]
---

I have just caught something. Record it as an OVERSIGHT EPISODE.

What I said when invoking this command: $ARGUMENTS

Follow these steps in order. Do not skip step 1.

## 1. Collect the six trailer values

Read `$ARGUMENTS` and the conversation so far, and work out which of the six
values below I have already given, explicitly or clearly by implication. Then
**ask me for the ones still missing** — all of them in a single question, not
one at a time. Do not guess a value to avoid asking, and do not fill one in
from a default. A false entry is worse than a missing one.

| Trailer | Allowed values |
| --- | --- |
| `Oversight-Type` | `architecture`, `business-rule`, `correctness`, `security`, `scope`, `data-model`, `performance`, `dependency`, `design`, `critique-override` |
| `Oversight-Stage` | `in-loop` (caught during the build, before handover), `acceptance` (caught by a stakeholder reviewing the delivered output), `production` (caught after go-live) |
| `Oversight-Source` | `self` (I spotted it unaided), `agent-critique` (an agent review surfaced it), or `client` / `stakeholder` / `colleague` (a person other than me) |
| `Oversight-Trigger` | One sentence: what you produced that looked correct and was not |
| `Oversight-Action` | One sentence: what was done about it |
| `Oversight-Durable` | `yes` if this produced a new or changed rule in `CLAUDE.md`, a subagent definition, a test, or a lint rule; `no` otherwise |

Two checks before you continue:

- If `Oversight-Type` is `critique-override`, then `Oversight-Durable` is `no`
  and there is no code change. The thing to commit is the review document with
  my adjudication written into it. If that adjudication is not yet written
  down, ask me for it and write it into the review document now — the episode
  is lost otherwise.
- If `Oversight-Durable` is `yes`, confirm the durable artifact actually exists
  in the working tree. If I said `yes` but nothing changed in `CLAUDE.md`, a
  subagent definition, a test or a lint rule, tell me and ask which it should
  be. Never delete or overwrite an existing CLAUDE.md section or subagent
  definition — change it in place so the evolution stays visible.

## 2. Stage the current change

Run `git status --short` and show me what is there. Stage the files belonging
to this episode.

This commit is the correction and nothing else. If unrelated feature work is
also uncommitted, stage only the episode's files and tell me plainly what you
left behind. Do not fold a correction into a larger commit.

## 3. Write the commit

Subject line: one sentence describing the correction, in the imperative. Body:
what I caught and why it was wrong, in enough detail that the episode is
legible later without this conversation. Then a blank line, then exactly the
six trailers, in this order, one per line, no blank lines between them:

```
Oversight-Type: <value>
Oversight-Stage: <value>
Oversight-Source: <value>
Oversight-Trigger: <one sentence>
Oversight-Action: <one sentence>
Oversight-Durable: <yes|no>
```

Each trailer value must be on a single line — no wrapping, or `git
interpret-trailers` will not parse it.

Then verify the trailers parse before continuing:

```
git log -1 --format='%(trailers:key=Oversight-Type,valueonly)'
```

If that prints nothing, the trailer block is malformed. Fix it with a fresh
commit, not an amend.

## 4. Append the log row

Append one row to the table in `OVERSIGHT_LOG.md`, after the last existing
row, using the commit's short SHA:

```
| YYYY-MM-DD | <short SHA> | <type> | <stage> | <source> | <trigger> | <action> | <yes|no> |
```

Escape any `|` in my wording as `\|` so the table does not break. Do not edit
or remove existing rows, even if this episode contradicts an earlier one.

Commit that row separately, right after, with the message
`Log oversight episode <short SHA>` and no `Oversight-` trailers — the log row
is bookkeeping, not a second episode.

## 5. Print the result

Print the episode commit's full SHA, its subject, and its trailer block, so I
can see it worked:

```
git log -1 --format='%H%n%s%n%n%(trailers)' <episode SHA>
```

## Rules that bind you here

- Never squash, amend, rebase or force-push a commit carrying an `Oversight-`
  trailer. That history is the dataset. If a trailered commit is wrong, add a
  new commit correcting it.
- If you are unsure whether something counts as an episode at all, ask me
  rather than recording it.
