"""
No views yet. ContactPage is served by Wagtail's normal page-serving
mechanism. The form submission endpoint (validating and saving a
ContactSubmission, and the newsletter signup endpoint saving a
NewsletterSignup) is an htmx partial owned by htmx-frontend, built
against the models in apps.contact.models.
"""
