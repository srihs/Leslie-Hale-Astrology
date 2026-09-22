"""
Wagtail page models actually render 200 through real request routing —
not `manage.py check`, not a template syntax check, but a real GET
against the page's own live URL, exactly the class of test that would
have caught the homepage 500 fixed in 88d3e0d (a queryset evaluated at
request time, invisible to every static check). Every page type in
PROJECT-SCOPE.md §4's site map is covered here at least once, built with
real, minimally-valid content — not empty stand-ins that happen to dodge
the code path that actually broke.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.blog.tests.factories import BlogCategoryFactory, make_blog_index_page, make_blog_post
from apps.bookings.models import BookingPage
from apps.bookings.tests.factories import AvailabilityRuleFactory
from apps.core.tests.factories import TestimonialFactory, make_about_page
from apps.home.tests.factories import make_home_page
from apps.readings.models import ReadingDetailPage, ReadingsIndexPage
from apps.readings.tests.factories import ReadingFactory

pytestmark = pytest.mark.django_db


def test_homepage_renders_200():
    """The exact regression class 88d3e0d fixed: a HomePage built with
    real content (including a real `latest_blog` queryset access) must
    actually render, not merely pass `manage.py check`."""
    home = make_home_page()
    response = Client().get(home.url)
    assert response.status_code == 200


def test_homepage_renders_with_a_live_blog_post_and_a_featured_testimonial():
    """Exercises the two queryset-backed sections most likely to break at
    request time: `latest_posts` (a real BlogPost) and a featured
    Testimonial chosen into the testimonials StreamField."""
    testimonial = TestimonialFactory()
    home = make_home_page(
        testimonials=[("testimonials", {"heading": "What clients say", "testimonials": [testimonial]})]
    )
    index = make_blog_index_page(home)
    make_blog_post(index, title="A Real Post")

    response = Client().get(home.url)
    assert response.status_code == 200


def test_booking_page_renders_200_with_no_availability_configured():
    """No AvailabilityRule/Reading at all — the emptiest real state this
    page can be in (a brand new site) — must still render, not 500 on an
    empty queryset."""
    home = make_home_page()
    booking_page = BookingPage(title="Book a Reading", slug="book-a-reading")
    home.add_child(instance=booking_page)

    response = Client().get(booking_page.url)
    assert response.status_code == 200


def test_booking_page_renders_200_with_availability_and_readings_configured():
    home = make_home_page()
    booking_page = BookingPage(title="Book a Reading", slug="book-a-reading")
    home.add_child(instance=booking_page)
    ReadingFactory()
    AvailabilityRuleFactory(weekday=0)

    response = Client().get(f"{booking_page.url}?reading=1&month=2026-06")
    assert response.status_code == 200


def test_readings_index_page_renders_200():
    home = make_home_page()
    index = ReadingsIndexPage(title="Readings", slug="readings-test")
    home.add_child(instance=index)
    ReadingFactory()

    response = Client().get(index.url)
    assert response.status_code == 200


def test_reading_detail_page_renders_200():
    home = make_home_page()
    index = ReadingsIndexPage(title="Readings", slug="readings-test")
    home.add_child(instance=index)
    reading = ReadingFactory()
    detail = ReadingDetailPage(title=reading.name, slug="detail-test", reading=reading)
    index.add_child(instance=detail)

    response = Client().get(detail.url)
    assert response.status_code == 200


def test_blog_index_page_renders_200_empty():
    home = make_home_page()
    index = make_blog_index_page(home)

    response = Client().get(index.url)
    assert response.status_code == 200


def test_blog_index_page_renders_200_with_posts_and_category_filter():
    home = make_home_page()
    index = make_blog_index_page(home)
    category = BlogCategoryFactory(name="Transits")
    make_blog_post(index, title="Post One", category=category)
    make_blog_post(index, title="Post Two")

    response = Client().get(index.url)
    assert response.status_code == 200

    filtered = Client().get(f"{index.url}?category={category.slug}")
    assert filtered.status_code == 200

    paginated = Client().get(f"{index.url}?page=99")  # past the end — must clamp, not 500
    assert paginated.status_code == 200


def test_blog_post_renders_200():
    home = make_home_page()
    index = make_blog_index_page(home)
    post = make_blog_post(index, title="A Single Post")

    response = Client().get(post.url)
    assert response.status_code == 200


def test_contact_page_renders_200():
    from apps.contact.models import ContactPage

    home = make_home_page()
    page = ContactPage(title="Contact", slug="contact-test")
    home.add_child(instance=page)

    response = Client().get(page.url)
    assert response.status_code == 200


def test_about_page_renders_200():
    home = make_home_page()
    page = make_about_page(home)

    response = Client().get(page.url)
    assert response.status_code == 200
