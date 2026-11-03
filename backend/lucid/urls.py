from django.contrib import admin
from django.urls import include, path

from lucid import views
from lucid.api import api

urlpatterns = [
    path("health", views.health, name="health"),
    path("v1/", api.urls),
    path("admin/", admin.site.urls),
    # Picture files in local development; production serves them from Cloud Storage (M4).
    path("media/", include("media.urls")),
]

handler400 = "lucid.errors.handler400"
handler403 = "lucid.errors.handler403"
handler404 = "lucid.errors.handler404"
handler500 = "lucid.errors.handler500"
