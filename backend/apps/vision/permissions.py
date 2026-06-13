from rest_framework.permissions import IsAuthenticated

# All endpoints (except auth login/refresh) require an authenticated user.
# Kept as a dedicated module so per-object permissions can be added later.

__all__ = ["IsAuthenticated"]
