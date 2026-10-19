from django.urls import path

from .views import EventBatchView

app_name = "analytics"

urlpatterns = [
    path("events/", EventBatchView.as_view(), name="event-batch"),
]
