# Leslie Hale Astrology

Static marketing and booking site. Hand-written HTML/CSS/JS; five design
directions under `versions/`. See `PROJECT-SCOPE.md` for scope.

This repository is also research data for a PhD on human oversight in
agentic software development. The rules below are part of that study.

## Oversight capture

When I correct you, reject your approach, override a decision, or tell you that
something you produced is wrong, treat that as an OVERSIGHT EPISODE. So is a
correction that reaches you later from a stakeholder reviewing the delivered
output, or from production. Those matter MORE, not less: anything found after
handover is something my own review let through, and that is the measurement the
whole study turns on.

An agent-run review counts too. If a critique agent surfaces something and I
accept it, that is an episode with `Oversight-Source: agent-critique`.

If a critique agent surfaces something and I DECIDE IT IS WRONG, or right but
not worth acting on, that is ALSO an episode, and an important one. It produces
no code change, so record it by committing the review document with my
adjudication written into it, using `Oversight-Type: critique-override` and
`Oversight-Durable: no`. Do not let those disappear just because nothing was
fixed.

Commit that correction on its own, separately from feature work, as soon as it
is resolved. Do not fold it into a larger commit.

The commit message must end with these git trailers, after a blank line:

```
Oversight-Type: <one of: architecture, business-rule, correctness,
                 security, scope, data-model, performance, dependency,
                 design, critique-override>
Oversight-Stage: <in-loop if caught during the build, before handover;
                  acceptance if caught by a stakeholder reviewing the
                  delivered output; production if caught after go-live>
Oversight-Source: <self if I spotted it unaided; agent-critique if an
                  agent review surfaced it; client, stakeholder or
                  colleague if a person other than me did>
Oversight-Trigger: <what you produced that looked correct and was not,
                    one sentence>
Oversight-Action: <what was done about it, one sentence>
Oversight-Durable: <yes if this produced a new or changed rule in
                    CLAUDE.md, a subagent definition, a test, or a lint
                    rule; no otherwise>
```

Never squash, amend, rebase or force-push a commit carrying an `Oversight-`
trailer. That history is the dataset.

Never delete or overwrite a subagent definition or a CLAUDE.md section. Change
it and commit the change, so the evolution stays visible.

After writing such a commit, append the matching row to `OVERSIGHT_LOG.md`.

If you are unsure whether something counts as an episode, ask me rather than
guessing. A false entry is worse than a missing one.

## Stack

Django + Wagtail (CMS) + htmx + Postgres + Docker. Design direction is
**v1-ephemeris** (`versions/v1-ephemeris/`), locked by `PROJECT-SCOPE.md` §7.
The other four `versions/` directories are rejected alternatives kept for the
record — do not build from them.

## Delegation

All project work runs through the subagents in `.claude/agents/`. Pick the
agent whose ownership covers the file you are about to touch, and delegate.
Do not do owned work inline because it looks small.

| Agent | Owns | Writes |
| --- | --- | --- |
| `wagtail-backend` | Page models, StreamField, migrations, editor experience | yes |
| `htmx-frontend` | Templates, htmx partials and endpoints, motion layer | yes |
| `design-system` | CSS tokens, components, responsive behaviour | yes |
| `booking-payments` | Booking, availability, payment, confirmations | yes |
| `blog-migration` | Blog models, feeds, Blogger import | yes |
| `docker-infra` | Dockerfile, compose, settings split, deployment | yes |
| `seo-analytics` | Metadata, structured data, sitemap, GA4 | yes |
| `test-engineer` | pytest-django suites, factories, fixtures | tests only |
| `code-critic` | Adversarial review, scope compliance | `reviews/` only |
| `accessibility-auditor` | WCAG 2.2 AA, keyboard, screen reader, mobile | no |
| `security-reviewer` | Settings, secrets, payments, input, dependencies | no |

The three review agents are deliberately read-only. They surface findings; I
adjudicate. That separation is what makes an agent finding a recordable
oversight episode rather than a silent self-correction.

Work that crosses agents is sequenced, not merged: the owning agent does its
part and hands over. When a piece of work is substantial, run `code-critic`
over it before committing.

### Review documents

`code-critic` writes `reviews/YYYY-MM-DD-<topic>.md` with every finding's
**Adjudication** left as `_pending_`. I fill each one in with `accepted`,
`rejected — <reason>` or `deferred — <reason>`.

- An **accepted** finding that produces a code change is an episode with
  `Oversight-Source: agent-critique`.
- A **rejected** or **deferred** finding produces no code change and is still
  an episode: commit the review document carrying my adjudication, with
  `Oversight-Type: critique-override` and `Oversight-Durable: no`.

Never discard a review document, and never edit a finding after I have
adjudicated it. Those documents are the record of what review caught and what
I chose to overrule.

### Skills

Agents invoke installed skills with the `Skill` tool, which is in every agent's
`tools:` allowlist. Each agent definition names the skills relevant to its work
and when to load them. Verified on 22 September 2026: subagents in this
project see the full installed catalogue, and both bare skills (resolving from
`~/.claude/skills/`) and `plugin:skill` names (resolving from the plugin cache)
invoke successfully.

The design agents inherit the site's actual design DNA this way.
`versions/v1-ephemeris/style.css` records that it was built following
`editorial-tech` and `book-serif-index`, so those are the skills that reproduce
its decisions rather than merely resembling them.

Two cautions, both learned the hard way:

- **Not every entry in the skill listing is a skill.** The `designer-skills`
  plugin ships `commands/` alongside `skills/`, and the listing shows both.
  `design-systems:tokenize`, `measurement-ops:define-metrics` and
  `visual-critique:critique-screen` are commands — invoke them as slash
  commands, not through the `Skill` tool. Before adding a skill name to an
  agent, confirm it resolves to a `skills/<name>/SKILL.md`.
- **Skills supply technique, never house style.** `PROJECT-SCOPE.md` §7 and
  `versions/v1-ephemeris/` are locked and win over any skill's defaults.
  Several catalogue skills will suggest rounded corners, box-shadows, their own
  accent colours or generic startup copy; all four are defects here. Every
  design-touching agent carries a Precedence section saying so, and agents must
  report which skill they overrode when this happens.
