from rest_framework.routers import DefaultRouter

from .views import SesionConversionViewSet

router = DefaultRouter()
router.register("sesiones", SesionConversionViewSet, basename="sesion")

urlpatterns = router.urls
