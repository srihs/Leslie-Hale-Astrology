"""
A tiny real image for tests that need a `wagtailimages.Image` — StreamField
blocks like `ImageChooserBlock` are required fields on several locked
homepage/about-page sections (see apps/home/blocks.py, apps/core/blocks.py),
so building a page with valid content means having a real, savable image,
not a mock. No network call: the bytes are generated in-process with
Pillow, which is already a pinned dependency (pyproject.toml).
"""

from __future__ import annotations

import io

from django.core.files.images import ImageFile
from PIL import Image as PILImage


def make_test_image(title: str = "Test image"):
    from wagtail.images import get_image_model

    ImageModel = get_image_model()

    buffer = io.BytesIO()
    PILImage.new("RGB", (10, 10), color="grey").save(buffer, format="PNG")
    buffer.seek(0)

    return ImageModel.objects.create(
        title=title,
        file=ImageFile(buffer, name=f"{title.lower().replace(' ', '-')}.png"),
    )
