"""Tests for health check endpoints."""



class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint(self, client):
        """Test basic health endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data

    def test_ready_endpoint(self, client):
        """Test readiness endpoint."""
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "checks" in data

    def test_metrics_endpoint_is_honest_501(self, client):
        """/metrics answers 501 (metrics not implemented) — it must
        never serve fake placeholder series again."""
        response = client.get("/metrics")

        assert response.status_code == 501
        assert "not implemented" in response.json()["detail"]
        assert "gateway_requests_total" not in response.text
