"""Dual-mode wiring: the standalone-service settings module must import
cleanly and describe a self-consistent minimal Django project.

``consigliere.settings_service`` is a *second* Django settings module,
used only when Consigliere runs as a standalone microservice (outside
the main ``sterna`` project). It is never activated during the test
run (``DJANGO_SETTINGS_MODULE`` stays ``sterna.settings.test``); these
tests only import it as a plain Python module and inspect its
top-level attributes, matching how ``manage.py`` would load it via
``DJANGO_SETTINGS_MODULE=consigliere.settings_service``.
"""

import importlib


def test_settings_service_imports_cleanly_with_expected_wiring():
    module = importlib.import_module("consigliere.settings_service")

    for required_app in ("authentication", "llm", "usage_quota", "consigliere", "conversations"):
        assert required_app in module.INSTALLED_APPS
    assert module.ROOT_URLCONF == "consigliere.urls_service"
    assert module.WSGI_APPLICATION == "consigliere.wsgi_service.application"
    assert module.AUTH_USER_MODEL == "authentication.User"
    auth_classes = module.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]
    assert "authentication.authentication.JWTAuthentication" in auth_classes


def test_urls_service_wires_consigliere_and_conversations_apis():
    urls_service = importlib.import_module("consigliere.urls_service")

    url_names = [
        pattern.pattern._route
        for pattern in urls_service.urlpatterns
        if hasattr(pattern.pattern, "_route")
    ]

    assert any(route.startswith("api/consigliere/") for route in url_names)
    assert any(route.startswith("api/") and "consigliere" not in route for route in url_names)


def test_wsgi_service_imports_without_raising():
    module = importlib.import_module("consigliere.wsgi_service")

    assert hasattr(module, "application")
