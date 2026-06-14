from rest_framework.routers import DefaultRouter

from .views import DatasetViewSet, ModeloViewSet

router = DefaultRouter()
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("modelos", ModeloViewSet, basename="modelo")

urlpatterns = router.urls
