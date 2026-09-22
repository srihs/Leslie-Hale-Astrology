"""
ASGI entrypoint. Not used by Gunicorn's default sync worker in this
deployment (see docker/Dockerfile), but present so an async server or
Django's own tooling can target this project without extra setup.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
