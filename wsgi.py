"""WSGI entry point: ``gunicorn wsgi:application``."""

from ehri_skgif.app import app as application
