# Design Review — Leslie Hale Astrology, three concepts

Reviewed 29 Aug 2026 against PROJECT-SCOPE.md §7. Method: `/visual-critique:critique-screen` (7 dimensions), `/visual-critique:critique-ux` (hierarchy · affordance · density) and `/design-ops:design-critique` (goal-tied, "I notice / I wonder / what if"). Evidence: headless-Chrome renders at 1440px and 390px of Home, plus Booking, Readings, Blog and About.

Context for the crit: goal = bookings from women 27–70, mobile-first, warm/non-judgemental tone. Stage = concept comparison (exploration crit, not polish). Placeholder copy/prices/testimonials are known and out of scope.

---

## Findings common to all three versions

### P1 — Critical
| # | Issue | Dimension | Fix |
|---|---|---|---|
| C1 | Hero uses `min-height: 100vh` with no cap. On tall/portrait desktops and large monitors the first viewport becomes a mostly empty navy band; content sits ~1 000px down. | Composition / Hierarchy | Cap: `min(100vh − nav, 860–940px)`. |
| C2 | Unsplash ID used for "compass on star chart" actually resolves to a beer-and-pizza photo — appears in the V1 hero, Readings #1, Blog card and V3 blog card. Breaks brand mood and the truthfulness of alt text. | Brand / Colour | Replace with a verified deep-space asset and matching alt text. |
| C3 | On mobile the "Book a Reading" nav button is hidden; the primary conversion is only reachable inside the hamburger or after scrolling to the hero CTA. | Affordance | Keep a compact Book button beside the menu toggle on ≤900px. |
| C4 | Booking summary (total + "Continue to payment") is last in DOM; on mobile the user fills three panels before seeing what they're paying. | Hierarchy / Density | On ≤900px move the summary above the steps (order −1), non-sticky. |

### P2 — Important
| # | Issue | Dimension | Fix |
|---|---|---|---|
| C5 | Calendar uses `role="grid"` on a flat div of buttons with no rows/gridcells — announces a broken grid to screen readers. | Affordance (a11y) | Use `role="group"` with a label; buttons carry the day. |
| C6 | Disabled "Choose a reading, date and time" button is styled as a dimmed gold primary — reads as an active but broken CTA. | Affordance | Disabled = outlined, muted text, no fill. |
| C7 | Hero stat "1:1" is cryptic at a glance for the 50–70 audience. | Density | Say "One‑to‑one". |
| C8 | Testimonial cards show "Client name / City" placeholders — must not ship; flagged for client. | Brand | Collect 3 real quotes (SCOPE §8). |
| C9 | Section reveals fire at `top 80%`; on very tall viewports a section can sit visible but un-revealed (seen on Readings FAQ). | Composition | Trigger at `top 90%` and refresh after load. |

### P3 — Polish
| # | Issue | Dimension | Fix |
|---|---|---|---|
| C10 | "Book →" text links inside service cards are small (13px) versus the 48px button standard elsewhere. | Affordance | Increase hit area (padding, min-height 44px). |
| C11 | Footer bottom text 12px on navy; legal but small for the audience. | Typography | 13px. |

---

## V1 · Ephemeris
**Strongest:** typography and framing — the serif/eyebrow system and 1px gold frames read exactly like the locked reference. **Weakest:** brand (C2 wrong image destroys the hero).
- I notice the split hero gives the headline the most weight and the CTA pair sits directly under it — entry point is correct. (Hierarchy ✓)
- I wonder whether the hero image caption "Charts · Transits · Timing" earns its place — it's decorative mono text at 11px. Kept; it's low cost. (P3)
- What if the mobile hero image (16/10, above headline) pushed the H1 below the fold on 390×740? Checked: headline is visible at ~55% of the fold. OK.
- Colour: gold on navy 9.8:1; muted body 8.1:1; eyebrow 11px gold passes AA for its weight. ✓
- Density: seven sections on Home is right for this audience; "How it works" answers the "what happens next" anxiety. ✓

## V2 · Night Sky
**Strongest:** memorable first viewport — moon + star-field + centred headline is the most "grabs attention" of the three (client's words). **Weakest:** density.
- P2 **N1** — The "At a glance" stats band repeats "20+ years" and "1:1" already shown in the hero-meta strip. Redundant. Fix: remove the band.
- P2 **N2** — Moon disc is `top:14%` with fixed size; on short landscape laptops (≤700px tall) it collides with the headline. Fix: size/position by `min()` and keep behind text at 55% opacity (already), plus clamp top.
- P3 **N3** — Blog section head is left-aligned while all other heads are centred. Fix: centre for consistency.
- Affordance: pill buttons are consistent; primary/secondary distinction is clear. ✓
- Three.js: single purpose (depth + pointer parallax), DPR capped at 1.5, pauses offscreen/hidden, poster fallback, context-loss handled. Justified. ✓

## V3 · Almanac
**Strongest:** brand/composition — alternating navy/ivory chapters and mono "§ 01" indices deliver the client's "modern/traditional" ask most literally, and ivory sections lift readability for the older end of the audience. **Weakest:** hierarchy in the hero on mobile.
- P2 **A1** — Mobile hero: the "Vol. I · Readings · Blog · Booking · Est. 2004" index row wraps to two lines above the H1 and competes with it. Fix: hide the middle item on ≤600px.
- P2 **A2** — Paper sections invert the palette; the gold `--gold` (#D9C08A) on ivory fails contrast for text, so eyebrows use `--gold-2` (#B89B5E, 3.3:1). Acceptable only at 11px uppercase bold; bump to 12px/500 weight. Fix in theme.
- P3 **A3** — Marquee is decorative and aria-hidden ✓, paused offscreen ✓; but on the paper page it appears only on Home — fine.
- Colour semantics hold across both surfaces (primary button flips to navy on paper). ✓

---

## Decisions / action items
1. Apply C1–C11, N1–N3, A1–A2 across the code (this pass). Owner: SAS Creative.
2. Client to supply: portrait, three testimonials, prices, contact details, booking/payment provider (SCOPE §8).
3. Recommendation for client presentation: lead with **V3** for the audience fit (readability + modern/traditional), **V2** as the "attention" option, **V1** as the closest-to-reference baseline.

---

## Outcome (same day)
Applied and re-rendered at 1440×900 and 520px: **C1–C7, C9–C11, N1–N3, A1–A2 fixed** (plus V2 scroll-cue spacing on narrow screens). **C8 (real testimonials) open — client action.** Verified: correct nebula asset on all pages, hero capped to the fold, mobile nav shows Book + Menu, booking summary first on mobile, calendar semantics fixed, disabled CTA reads as disabled.
Note: headless-Chrome screenshots below ~500px width are cropped (Chrome minimum window), so true 390px checks should be done in device emulation before client review.

---

## V4 · Stellarium-style (light) and V5 · Astralla-style (dark violet) — added 29 Aug 2026
Both are **outside the locked navy/gold guideline** at the client's request and follow the two named theme demos structurally: section order, palette mood, type mood, grid counts and motifs. No theme assets, copy or code were reused (paid themes) — imagery is Unsplash-licensed, zodiac/planet marks are Unicode glyphs, all copy is Leslie's.

Quick crit (same three methods, desktop 1440 + 520 narrow):
- **V4** — Strongest: composition (watercolour washes + right-aligned hero + 6×2 zodiac grid read exactly like the reference); Weakest: hierarchy — underlined text buttons are quiet, so the primary CTA is kept solid black (P2 mitigated). Contrast: #161616 on white ✓; 10px tracked labels are at the legibility floor for the 50–70 audience (P3, matches reference).
- **V5** — Strongest: brand mood (starfield, spaced serif wordmark, arrow-line button motif); Weakest: density — 12-sign grid + 4 service cards + 3 icons + 2 prose blocks is long; kept to mirror the reference, but the client should expect to trim. Mobile header stacks Appointment / Menu / wordmark cleanly (verified at 520px).

### V4/V5 replication pass (effects + lorem ipsum)
- V4: 3-slide fading hero with prev/next + dots (pauses on hover/focus/hidden tab), scroll-parallax watercolour washes, growing-underline text buttons, blob morph on zodiac hover, circular clip-path image reveals, floating planet row. All body copy → lorem ipsum.
- V5: live 2D-canvas twinkling starfield with pointer drift (DPR-capped, pauses when hidden), 12-sign constellation slider with arrows/autoplay, testimonial slider, 3-banner fading carousel with Ken Burns, hover image-swap service cards. All body copy → lorem ipsum.
- Fixed: duplicate reveal tweens (main.js + effects.js) left some grid cards invisible; effects.js now owns those grids.
- Reduced motion: sliders stop auto-advancing, starfield/parallax/Ken Burns off.

### V4 replication pass 2 (client: "Astralla is a match, Stellarium is not")
Rebuilt V4 home to the reference's exact composition: no hero photo — layered irregular watercolour splashes with right-aligned text and 3-slide fader; "—••—" divider; grey speckled watercolour band holding Horoscope Forecasts (6×2, glyph + offset wash + outline ring) and Subscribe (inline underlined Name / E-mail / Sun sign / SUBSCRIBE); ink circle row overlapping the band; Astro Blog ×3 with ink images + offset washes and hairline; View more; planet row over pink paint; Follow Us circles; minimal footer. Removed service cards, about block and black nav CTA (not in reference). Fixed slide-display specificity bug and select arrow sizing.

### V4 replication pass 3 — asset system (per /build-awwwards-quality-sites)
- Attempted original AI-illustrated assets (12 ink zodiac drawings, splashes, planets, blog art) via Higgsfield — blocked: "Requires basic plan or higher" on the connected free plan. Left as an upgrade path (prompts are in this session's history; the page is built to drop PNGs into `assets/`).
- Shipped instead: **procedural watercolour textures** generated by `assets/make_washes.py` (numpy/PIL: fBm-edged multi-layer pigment, rim darkening, granulation, paper grain, speckled grey band). These are textures, not authored illustrations, so they stay within the skill's asset rules. Wired into hero splashes, zodiac blobs, blog washes, grey band and a global paper-grain overlay; zodiac glyphs and planet row get an SVG feTurbulence ink-bleed filter.
- Fixed: solid-colour fallback leaking behind blog wash #3; hero wash sizing.
