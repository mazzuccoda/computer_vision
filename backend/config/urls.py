from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.vision.urls")),
    path("api/", include("apps.training.urls")),
    path("api/converter/", include("apps.converter.urls")),
    path("api/reentrenamiento/", include("apps.feedback.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
