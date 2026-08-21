from django.urls import path
from .views import SupportRequestCreateView

app_name = "support"

urlpatterns = [
    path("requests/", SupportRequestCreateView.as_view(), name="create"),
]
