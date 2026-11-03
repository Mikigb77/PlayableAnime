from django.urls import path

from media import views

urlpatterns = [
    path("<path:key>", views.local_file, name="media-local-file"),
]
