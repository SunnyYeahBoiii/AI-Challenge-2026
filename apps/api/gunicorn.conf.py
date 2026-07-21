"""Gunicorn defaults that avoid duplicating large embedding models in GPU memory."""

import os

bind = "0.0.0.0:5000"
workers = int(os.getenv("GUNICORN_WORKERS", "1"))
timeout = int(os.getenv("GUNICORN_TIMEOUT_SECONDS", "120"))
