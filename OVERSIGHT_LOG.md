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
| 2026-09-22 | 88d3e0d | correctness | in-loop | agent-critique | A queryset still prefetched a relation removed by the taxonomy change, passing every static check while returning 500 on the homepage for every visitor. | Corrected the queryset to select_related the category FK and swept every app for other references orphaned by the same change. | no |
| 2026-09-22 | a162d59 | security | in-loop | agent-critique | The Blogger importer parsed untrusted external XML with the standard library behind only a response-size cap, which stops nothing structural — a 540-byte payload expanded 556x. | Switched the parser to defusedxml with DTDs and entities forbidden, and verified refusal against billion-laughs and XXE fixtures on both the Atom and RSS paths. | no |
| 2026-09-22 | 926123c | architecture | in-loop | self | Agents repeatedly edited committed infrastructure files as local workarounds, because the project offered no supported place to express a machine-specific port or environment value. | Added a gitignored docker-compose.override.yml mechanism with a committed example, and a CLAUDE.md rule forbidding local workarounds in committed files. | yes |
| 2026-09-22 | 3c76760 | design | in-loop | agent-critique | Five form fields signalled validation failure with colour alone, so a visitor who could not perceive the red border saw a form that refused to submit without stating why. | Rendered the server-generated message for every field in the existing pattern, with aria-describedby and aria-invalid. | no |
| 2026-09-22 | 652e956 | data-model | in-loop | agent-critique | Every payment event was written with a null booking FK, so the audit trail looked complete in the table but could not be reached from the booking it documented. | Resolved the booking before the insert and passed it into the same create() inside the existing transaction. | no |
| 2026-09-23 | 0c0fa2a | design | in-loop | agent-critique | Error messages were scoped to the form so every field falsely claimed an error, the focus ring measured 1.46:1 against a 3:1 requirement, and calendar tap targets were 29px at 320px. | Scoped error display per field via aria-invalid, replaced the box-shadow ring with the sitewide gold outline, and widened calendar targets to the maximum the grid allows. | no |
| 2026-09-23 | 8dd7234 | security | in-loop | agent-critique | The pinned Django, Wagtail and Pillow carried 94 known advisories, the admin had no login throttling, and uploads relied on unreviewed framework defaults. | Bumped each dependency within its branch, added django-axes on the authentication backend, and set the upload limits the pinned Wagtail actually reads. | no |
| 2026-09-23 | e96cbf2 | correctness | in-loop | agent-critique | Every public form POST returned a bare unstyled fragment without JavaScript, while the templates and my own commit message claimed a working full-page reload. | Branched each endpoint on request.htmx so non-htmx requests render the full owning page. | no |
| 2026-09-23 | dc1d952 | scope | in-loop | agent-critique | The booking page rendered two mutually contradictory invented cancellation policies and the homepage a blanket session duration, all §8 open items. | Deleted every invented literal, rendered BookingPage.cancellation_policy, and derived the duration from the featured reading. | no |
| 2026-09-23 | 82ce1d8 | design | in-loop | agent-critique | Keyboard focus was destroyed at every htmx step of the booking flow, the status poller replaced its own live region every two seconds, and the booking page skipped a heading level. | Gave every swapped control a stable id for htmx focus restoration, split the live region from its polling content, and restored heading order. | no |
| 2026-09-23 | 8a1ccbf | security | in-loop | agent-critique | Four third-party scripts loaded from CDNs with no integrity attribute on pages carrying the CSRF token and the booking form's birth data. | Computed and cross-validated real sha384 hashes for each file and added integrity and crossorigin attributes. | no |
| 2026-09-23 | 02d3cfa | security | in-loop | agent-critique | Four public POST endpoints had no rate limiting, letting an unauthenticated script hold every bookable slot indefinitely without paying. | Applied per-IP limits with a warm 429 on both request paths, and froze the clock the limiter reads so the burst tests are deterministic. | yes |
| 2026-09-23 | 141f4a0 | correctness | in-loop | agent-critique | The test suite passed at 110 green while every form's no-JS path returned an unstyled fragment, because the tests asserted status and body text but never response shape. | Added paired full-page and fragment shape assertions to every form endpoint's tests, each proved to fail against the reconstructed pre-fix response. | yes |
| 2026-09-23 | 2eec3d1 | critique-override | in-loop | agent-critique | The site collects and indefinitely retains birth data, contact submissions and newsletter signups with no retention policy. | Deferred to the client and added to PROJECT-SCOPE.md §8 rather than inventing a retention period. | no |
| 2026-09-23 | 2ac85ef | critique-override | in-loop | agent-critique | The no-JS mobile menu places its checkbox before the brand link in DOM order, so keyboard tab order does not follow visual order. | Deferred deliberately; the only alternative preserving tab order relies on :has(), whose failure mode is a silently unnavigable menu. | no |
| 2026-09-23 | 3bf095e | design | acceptance | self | The blog pager rendered all 163 page links in a flex row that could not wrap, overflowing the page, and every review passed because the code was only ever exercised against a handful of seeded posts. | Rendered an elided page range from the view and added flex-wrap to the pager, so neither the template nor the CSS alone can reproduce the overflow. | yes |
| 2026-09-23 | a7d778a | correctness | acceptance | self | htmx cancelled the browser's own navigation on every filter and pager link, then silently did nothing when its request failed, leaving the controls dead with no error and no fallback. | Added a handler for htmx sendError, responseError and timeout that navigates to the element's href, restoring the behaviour the anchor would have had. | no |
| 2026-09-23 | f989c39 | correctness | acceptance | self | Two htmx handlers read the swapped element off e.detail.target, which points at the detached pre-swap node, so blog tiles stayed invisible after filtering and a form focus handler never fired at all. | Changed both handlers to e.target, documented the distinction at the top of the htmx section, and verified tile visibility in a browser by computed opacity. | yes |
| 2026-09-24 | b6b5f7f | correctness | acceptance | agent-critique | The form-confirmation focus handler tested for a class htmx had not yet applied, so it never fired on any form, and my previous fix to the same handler left that untouched while claiming it was resolved. | Moved the handler to htmx:afterSettle, verified the other two handlers are correct on afterSwap by instrumenting both events, and documented the class-deferral rule. | yes |
| 2026-09-24 | da8bc82 | correctness | in-loop | agent-critique | Wagtail's Site record was left at its localhost default, so the blog RSS feed would have published http://localhost links for all 1460 posts in any deployment, while passing every check and test because localhost is correct in development. | Added an idempotent entrypoint step that syncs the Site hostname and port from the environment under the existing migrations gate. | no |
| 2026-09-24 | aded696 | business-rule | in-loop | self | The site assumed the agency's country for the client's, offering every booking slot in New Zealand hours and pricing every reading in New Zealand dollars with the currency hardcoded into a model and its migration. | Moved timezone and locale to US values, replaced the hardcoded currency with a configurable setting defaulting to USD, and swept out the symbol and label assumptions in templates, help text and the backoffice. | no |
| 2026-09-25 | 949cddf | security | acceptance | self | The production compose published gunicorn on 0.0.0.0, leaving the application directly reachable over plain HTTP and bypassing nginx's TLS and security headers entirely. | Bound the published port to 127.0.0.1, confirmed the database publishes nothing, and committed an nginx template documenting the forwarded-proto and media requirements. | no |
| 2026-09-25 | 32e1b56 | correctness | acceptance | self | The importer compared its content fingerprint before copying images, so once an environment problem had caused every image to fail, no re-run would ever retry them and the posts were permanently imageless. | Made a hash match still verify and repair missing images, reported repairs separately, and detect an unwritable media root up front as an environment problem. | yes |
| 2026-09-25 | dfbd96b | correctness | acceptance | self | Reveal animations only covered elements inside a hardcoded container list, so the blog hero image and share links sat at opacity 0 permanently, and a failed GSAP load would have hidden every such element sitewide. | Made both passes record what they claim and added a sweep that reveals anything unclaimed, treated a missing GSAP as reduced motion, and added a browser test asserting nothing is left invisible. | yes |

<!-- Append one row per Oversight- trailered commit, newest last. Do not add
     illustrative or placeholder rows: a false entry is worse than a missing
     one. Never edit or remove a row that is already here. -->

<!-- Data-quality note, 2026-09-22: commit 926123c carries Oversight- trailers
     AND the 110-test suite, which is unrelated feature work. CLAUDE.md requires
     a correction be committed on its own; a careless `git add -A` folded the two
     together. Not amended, because amending a trailered commit is forbidden.
     Recorded here so the anomaly is visible to analysis rather than hidden. -->
