from rest_framework.routers import DefaultRouter

from .views import CicloReentrenamientoViewSet, ReentrenamientoViewSet

router = DefaultRouter()
router.register(
    "ciclos", CicloReentrenamientoViewSet, basename="ciclo-reentrenamiento"
)
router.register(
    "", ReentrenamientoViewSet, basename="reentrenamiento"
)

urlpatterns = router.urls
