"""Development settings."""
from .base import *  # noqa: F401,F403

DEBUG = True

# Allow all origins during local development for convenience.
CORS_ALLOW_ALL_ORIGINS = True
