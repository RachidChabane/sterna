"""
OpenAPI schema configuration using drf-spectacular.
"""

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# Raw OpenAPI document. Format is content-negotiated, or selected via the
# `.json` / `.yaml` URL suffix (see documentation/urls.py).
schema_view = SpectacularAPIView.as_view()

# Interactive documentation UIs, both pointing back at the raw schema above.
swagger_ui_view = SpectacularSwaggerView.as_view(url_name="documentation:schema-json")
redoc_view = SpectacularRedocView.as_view(url_name="documentation:schema-json")
