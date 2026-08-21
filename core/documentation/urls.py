"""
URL configuration for API documentation.
"""

from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns
from .schema import schema_view, swagger_ui_view, redoc_view
from .views import (
    AuthenticationGuideView,
    OpenRouterGuideView,
    ModelSelectionExamplesView,
    CostEstimationExamplesView,
)

app_name = "documentation"

urlpatterns = format_suffix_patterns(
    [
        # Raw OpenAPI document, e.g. /api/docs/swagger.json or swagger.yaml
        path("swagger", schema_view, name="schema-json"),
    ],
    allowed=["json", "yaml"],
)

urlpatterns += [
    # Swagger UI
    path("swagger/", swagger_ui_view, name="schema-swagger-ui"),
    # ReDoc UI
    path("redoc/", redoc_view, name="schema-redoc"),
    # Documentation guides
    path(
        "guides/authentication/",
        AuthenticationGuideView.as_view(),
        name="authentication-guide",
    ),
    path("guides/openrouter/", OpenRouterGuideView.as_view(), name="openrouter-guide"),
    path(
        "examples/model-selection/",
        ModelSelectionExamplesView.as_view(),
        name="model-selection-examples",
    ),
    path(
        "examples/cost-estimation/",
        CostEstimationExamplesView.as_view(),
        name="cost-estimation-examples",
    ),
]
