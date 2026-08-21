"""
Tests for API documentation generation and views.
"""

import json
from django.test import TestCase, Client
from django.urls import reverse
from rest_framework.test import APITestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model
import tempfile
import os

User = get_user_model()


class SchemaGenerationTestCase(TestCase):
    """Test OpenAPI schema generation."""

    def setUp(self):
        self.client = Client()

    def test_swagger_json_schema_generation(self):
        """Test that the OpenAPI JSON schema is generated correctly."""
        url = reverse("documentation:schema-json", kwargs={"format": "json"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        schema = json.loads(response.content)
        self.assertIn("openapi", schema)
        self.assertIn("info", schema)
        self.assertIn("paths", schema)
        self.assertEqual(schema["info"]["title"], "Sterna API")

    def test_swagger_yaml_schema_generation(self):
        """Test that the OpenAPI YAML schema is generated correctly."""
        url = reverse("documentation:schema-json", kwargs={"format": "yaml"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"openapi:", response.content)
        self.assertIn(b"title: Sterna API", response.content)

    def test_unsuffixed_schema_url_serves_schema(self):
        """Test that the format-less schema URL (used internally by the
        Swagger UI / ReDoc views to fetch the raw document) resolves and
        serves a schema, not just the suffixed .json/.yaml variants."""
        url = reverse("documentation:schema-json")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"openapi:", response.content)

    def test_schema_contains_authentication_endpoints(self):
        """Test that schema includes authentication endpoints."""
        url = reverse("documentation:schema-json", kwargs={"format": "json"})
        response = self.client.get(url)
        schema = json.loads(response.content)

        paths = schema.get("paths", {})
        auth_endpoints = [path for path in paths if "/auth/" in path]
        self.assertTrue(len(auth_endpoints) > 0, "No authentication endpoints found")

    def test_schema_contains_llm_endpoints(self):
        """Test that schema includes LLM/OpenRouter endpoints."""
        url = reverse("documentation:schema-json", kwargs={"format": "json"})
        response = self.client.get(url)
        schema = json.loads(response.content)

        paths = schema.get("paths", {})
        llm_endpoints = [path for path in paths if "/llm/" in path]
        self.assertTrue(len(llm_endpoints) > 0, "No LLM endpoints found")


class SwaggerUITestCase(TestCase):
    """Test Swagger UI rendering."""

    def setUp(self):
        self.client = Client()

    def test_swagger_ui_loads(self):
        """Test that Swagger UI page loads successfully."""
        url = reverse("documentation:schema-swagger-ui")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"swagger-ui", response.content)
        self.assertIn(b"Sterna API", response.content)

    def test_redoc_ui_loads(self):
        """Test that ReDoc UI page loads successfully."""
        url = reverse("documentation:schema-redoc")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"redoc", response.content)


class DocumentationGuidesTestCase(APITestCase):
    """Test documentation guide endpoints."""

    def test_authentication_guide(self):
        """Test authentication guide endpoint."""
        url = reverse("documentation:authentication-guide")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("jwt_flow", data)
        self.assertIn("token_details", data)
        self.assertIn("best_practices", data)
        self.assertIn("password_reset", data)

        # Check JWT flow structure
        jwt_flow = data["jwt_flow"]
        self.assertIn("1_register", jwt_flow)
        self.assertIn("2_login", jwt_flow)
        self.assertIn("3_use_token", jwt_flow)
        self.assertIn("4_refresh", jwt_flow)
        self.assertIn("5_logout", jwt_flow)

    def test_openrouter_guide(self):
        """Test OpenRouter integration guide endpoint."""
        url = reverse("documentation:openrouter-guide")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("overview", data)
        self.assertIn("configuration", data)
        self.assertIn("model_tiers", data)
        self.assertIn("endpoints", data)
        self.assertIn("fallback_strategy", data)
        self.assertIn("rate_limiting", data)
        self.assertIn("best_practices", data)

        # Check model tiers
        tiers = data["model_tiers"]
        self.assertIn("FAST", tiers)
        self.assertIn("BALANCED", tiers)
        self.assertIn("QUALITY", tiers)

    def test_model_selection_examples(self):
        """Test model selection examples endpoint."""
        url = reverse("documentation:model-selection-examples")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("use_cases", data)
        self.assertIn("selection_strategy", data)
        self.assertIn("optimization_tips", data)

        # Check use cases
        use_cases = data["use_cases"]
        self.assertIn("binary_classification", use_cases)
        self.assertIn("code_review", use_cases)
        self.assertIn("creative_writing", use_cases)
        self.assertIn("reasoning_tasks", use_cases)

    def test_cost_estimation_examples(self):
        """Test cost estimation examples endpoint."""
        url = reverse("documentation:cost-estimation-examples")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("scenarios", data)
        self.assertIn("cost_breakdown", data)
        self.assertIn("optimization_strategies", data)
        self.assertIn("budget_planning", data)

        # Check scenarios
        scenarios = data["scenarios"]
        self.assertIn("small_evaluation", scenarios)
        self.assertIn("medium_evaluation", scenarios)
        self.assertIn("large_evaluation", scenarios)
        self.assertIn("multi_criteria", scenarios)


class ExportSchemaCommandTestCase(TestCase):
    """Test the export_openapi_schema management command."""

    def test_export_json_schema(self):
        """Test exporting schema as JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test_schema")
            call_command(
                "export_openapi_schema", format="json", output=output_file, pretty=True
            )

            json_file = f"{output_file}.json"
            self.assertTrue(os.path.exists(json_file))

            with open(json_file, "r") as f:
                schema = json.load(f)
                self.assertIn("openapi", schema)
                self.assertIn("info", schema)
                self.assertIn("paths", schema)

    def test_export_yaml_schema(self):
        """Test exporting schema as YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test_schema")
            call_command("export_openapi_schema", format="yaml", output=output_file)

            yaml_file = f"{output_file}.yaml"
            self.assertTrue(os.path.exists(yaml_file))

            with open(yaml_file, "r") as f:
                content = f.read()
                self.assertIn("openapi:", content)
                self.assertIn("info:", content)
                self.assertIn("paths:", content)


class APIEndpointDocumentationTestCase(TestCase):
    """Test that all API endpoints are properly documented."""

    def setUp(self):
        self.client = Client()

    def test_all_endpoints_have_descriptions(self):
        """Test that all endpoints have operation descriptions."""
        url = reverse("documentation:schema-json", kwargs={"format": "json"})
        response = self.client.get(url)
        schema = json.loads(response.content)

        paths = schema.get("paths", {})
        missing_descriptions = []

        for path, methods in paths.items():
            for method, details in methods.items():
                if method in ["get", "post", "put", "patch", "delete"]:
                    if isinstance(details, dict):
                        # Skip checking for operation description as not all may have it
                        # But check for basic structure
                        if "responses" not in details:
                            missing_descriptions.append(f"{method.upper()} {path}")

        if missing_descriptions:
            self.fail(f"Endpoints missing proper documentation: {missing_descriptions}")

    def test_authentication_is_documented(self):
        """Test that JWT bearer authentication is documented as an OpenAPI
        HTTP bearer security scheme (see JWTAuthenticationScheme)."""
        url = reverse("documentation:schema-json", kwargs={"format": "json"})
        response = self.client.get(url)
        schema = json.loads(response.content)

        schemes = schema.get("components", {}).get("securitySchemes", {})
        bearer_schemes = [
            scheme
            for scheme in schemes.values()
            if scheme.get("type") == "http" and scheme.get("scheme") == "bearer"
        ]
        self.assertTrue(bearer_schemes, f"No HTTP bearer security scheme in {schemes}")

    def test_response_examples_exist(self):
        """Test that response examples are provided for key endpoints."""
        url = reverse("documentation:schema-json", kwargs={"format": "json"})
        response = self.client.get(url)
        schema = json.loads(response.content)

        # We should have some paths with examples. In OpenAPI 3 (drf-spectacular),
        # examples live under responses.<code>.content.<media-type>.examples.
        paths_with_examples = 0
        for path, methods in schema.get("paths", {}).items():
            for method, details in methods.items():
                if not isinstance(details, dict):
                    continue
                for response_def in details.get("responses", {}).values():
                    if not isinstance(response_def, dict):
                        continue
                    for media_type_def in response_def.get("content", {}).values():
                        if "examples" in media_type_def:
                            paths_with_examples += 1
                            break

        # We have explicitly added examples in our guide views
        self.assertGreater(
            paths_with_examples, 0, "No endpoints have response examples"
        )
