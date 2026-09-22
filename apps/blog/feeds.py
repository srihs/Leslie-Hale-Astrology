"""
The blog's RSS feed.

Standard Django syndication (`django.contrib.syndication`) rather than a
hand-rolled XML view — no new dependency, and it gets conditional GET,
correct MIME type and escaping for free. Wired in config/urls.py at a
fixed `/blog/rss/` address, ahead of Wagtail's page-serving catch-all, so
it exists independently of whatever slug the Blog index page ends up with.

Only ever lists posts that are actually `live().public()` — the same
published/draft rule the blog index and RSS readers both expect; a
Blogger-imported draft (see apps.blog.blogger_import) never appears here
until an editor publishes it.
"""

from django.contrib.syndication.views import Feed

from apps.blog.models import BlogIndexPage, BlogPost

#: How many of the most recent posts the feed carries. Not a §8 business
#: figure — a conventional RSS feed length, safe for htmx-frontend/
#: seo-analytics to change without touching the blog models.
FEED_ITEM_COUNT = 20


class BlogFeed(Feed):
    title = "Leslie Hale Astrology — Blog"
    description = "Notes on the sky and everyday astrology from Leslie Hale."

    def link(self):
        index_page = BlogIndexPage.objects.first()
        return index_page.full_url if index_page else "/"

    def items(self):
        return (
            BlogPost.objects.live()
            .public()
            .select_related("featured_image", "category")
            .order_by("-published_date")[:FEED_ITEM_COUNT]
        )

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.excerpt or ""

    def item_link(self, item):
        return item.full_url

    def item_pubdate(self, item):
        return item.published_date

    def item_updateddate(self, item):
        return item.last_published_at or item.published_date

    def item_author_name(self, item):
        return item.author_name

    def item_categories(self, item):
        return [item.category.name] if item.category else []
