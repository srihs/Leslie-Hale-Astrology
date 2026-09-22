"""
WSGI entrypoint. Gunicorn serves this in every environment; the settings
module it loads is controlled by DJANGO_SETTINGS_MODULE, defaulting to prod
because this is the production entry point.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
