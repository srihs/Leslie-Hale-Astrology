"""
templates/blog/post.html — the article hero photo and the "Share" links
never appeared on any blog post. Confirmed live: the image itself loaded
fine (real bytes, correct src, visible in a raw <img> preview), it was
just permanently at `opacity:0`, the state static/css/_base.css's
`[data-reveal]{opacity:0;transform:translateY(24px)}` puts every
`[data-reveal]` element in until some GSAP timeline tweens it to
`opacity:1`.

static/js/main.js only ever ran that tween from two places, each scoped
to a fixed, named list of containers:

  1. the hero-intro timeline — `[data-reveal]` elements INSIDE
     `.hero`/`.page-hero`
  2. the section-reveal scan — `[data-reveal]` elements inside
     `section:not(.hero):not(.page-hero), .detail, footer`

`<figure class="article-hero" data-reveal>` and `<div class="share"
data-reveal>` in blog/post.html sit inside a `<div class="wrap
article">` that is a SIBLING of `<section class="page-hero">`, not a
descendant of it, and is itself none of `section`, `.detail` or
`footer` — so neither pass ever touched them. No error, no console
warning, correct DOM, correct src: it just looked like a broken image.

The actual defect was never this one template — it's that the reveal
system requires every `[data-reveal]` element to live inside a container
some hardcoded selector list already knows about, and an element outside
all of them fails identically and silently. This file's job is to make
sure that class of bug stays fixed: it doesn't hardcode which container
shape it's checking for, it just demands that nothing carrying
`[data-reveal]`, anywhere in the rendered page, is left at computed
opacity 0 once the page and its motion layer have finished loading.

Run this against the code as it stood before the fix (comment out the
"orphan safety net" block in static/js/main.js, or check out the commit
before it) and `test_blog_post_has_no_invisible_reveals` fails — the
article hero figure and the share links are still `opacity: 0`. Every
other test in this file passes even before the fix, because every other
page's `[data-reveal]` elements already happen to sit inside a container
the old, fixed selector list recognised; that's the point — the old
system worked by coincidence of markup shape, not by construction, and
this file is what would have caught the blog post case (and would catch
whatever container shape trips the same trap next) before it shipped.
"""

from __future__ import annotations


def _assert_no_invisible_reveals(page, *, context_label):
    """
    Scrolls the full page in a few steps (so ScrollTrigger-based reveals
    below the fold get the scroll position change they trigger on, not
    just whatever happened to be in the first viewport on load), gives
    any in-flight GSAP tween a moment to finish, then asserts every
    [data-reveal] element's *computed* opacity is 1 — never DOM presence,
    since an element sitting at opacity 0 is exactly the bug and is very
    much present in the DOM.
    """
    total = page.locator("[data-reveal]").count()
    assert total > 0, f"{context_label}: no [data-reveal] elements found to check at all"

    height = page.evaluate("() => document.documentElement.scrollHeight")
    steps = 6
    for step in range(1, steps + 1):
        page.evaluate("(y) => window.scrollTo(0, y)", height * step / steps)
        page.wait_for_timeout(150)
    # Longest single reveal tween in static/js/main.js is 0.9s (hero
    # words); this margin covers it plus GSAP's own scroll-triggered
    # dispatch delay.
    page.wait_for_timeout(1000)

    invisible = page.evaluate(
        """() => Array.from(document.querySelectorAll('[data-reveal]')).map((el, i) => ({
            index: i,
            tag: el.tagName.toLowerCase(),
            cls: el.className,
            opacity: getComputedStyle(el).opacity,
        })).filter(r => r.opacity !== '1')"""
    )
    assert not invisible, (
        f"{context_label}: {len(invisible)} of {total} [data-reveal] element(s) still at "
        f"computed opacity != 1 after the page finished loading and was scrolled through — "
        f"present in the DOM but invisible: {invisible!r}"
    )


def test_blog_post_has_no_invisible_reveals(page, base_url):
    page.goto(f"{base_url}/blog/")
    href = page.locator("#post-list .post[data-reveal]").first.get_attribute("href")
    assert href, "no blog post link found on /blog/ to open — cannot exercise this page at all"
    page.goto(f"{base_url}{href}" if href.startswith("/") else href)
    _assert_no_invisible_reveals(page, context_label=f"blog post {href}")


def test_blog_index_has_no_invisible_reveals(page, base_url):
    page.goto(f"{base_url}/blog/")
    _assert_no_invisible_reveals(page, context_label="/blog/")


def test_reading_detail_has_no_invisible_reveals(page, base_url):
    page.goto(f"{base_url}/readings/")
    href = page.locator(".detail .meta a.link").first.get_attribute("href")
    assert href, (
        "no reading detail page link ('Learn more') found on /readings/ — cannot "
        "exercise this page at all"
    )
    page.goto(f"{base_url}{href}" if href.startswith("/") else href)
    _assert_no_invisible_reveals(page, context_label=f"reading detail {href}")


def test_about_has_no_invisible_reveals(page, base_url):
    page.goto(f"{base_url}/about/")
    _assert_no_invisible_reveals(page, context_label="/about/")


def test_contact_has_no_invisible_reveals(page, base_url):
    page.goto(f"{base_url}/contact/")
    _assert_no_invisible_reveals(page, context_label="/contact/")


def test_booking_has_no_invisible_reveals(page, base_url):
    # Discovered off the primary nav rather than a hardcoded slug — see
    # includes/_nav.html; the booking page is a Wagtail page reached
    # through `{% pageurl %}`, not a fixed Django URL.
    page.goto(f"{base_url}/about/")
    href = page.locator("#menu a", has_text="Book a reading").first.get_attribute("href")
    assert href, "no 'Book a reading' nav link found — cannot exercise this page at all"
    page.goto(f"{base_url}{href}" if href.startswith("/") else href)
    _assert_no_invisible_reveals(page, context_label=f"booking page {href}")
