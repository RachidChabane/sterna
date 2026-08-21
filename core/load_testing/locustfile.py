"""
Main Locust file for load testing Sterna.

This file defines user behaviors and test scenarios for load testing.
"""

import random
import time
from typing import Dict
from locust import HttpUser, task, between, events
from locust.exception import RescheduleTask

from load_testing.config import TestConfig
from load_testing.data_generators import DataGenerator


class SternaUser(HttpUser):
    """Simulates a user interacting with the Sterna system."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    host = TestConfig.BASE_URL

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_gen = DataGenerator(seed=random.randint(1, 10000))
        self.auth_token = None
        self.refresh_token = None
        self.project_id = None
        self.dataset_id = None
        self.rubric_id = None
        self.evaluation_id = None
        self.webhook_id = None

    def on_start(self):
        """Called when a user starts. Performs login and initial setup."""
        self.login()
        if self.auth_token:
            self.create_or_select_project()

    def on_stop(self):
        """Called when a user stops. Performs cleanup."""
        if self.auth_token:
            self.logout()

    def login(self):
        """Authenticate and obtain JWT tokens."""
        with self.client.post(
            "/api/auth/login/",
            json={
                "email": TestConfig.TEST_USERNAME,
                "password": TestConfig.TEST_PASSWORD,
            },
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access")
                self.refresh_token = data.get("refresh")
                response.success()
            else:
                response.failure(f"Login failed: {response.text}")

    def logout(self):
        """Logout and invalidate tokens."""
        if self.refresh_token:
            headers = self.get_auth_headers()
            with self.client.post(
                "/api/auth/logout/",
                json={"refresh": self.refresh_token},
                headers=headers,
                catch_response=True,
            ) as response:
                if response.status_code in [200, 204]:
                    response.success()
                else:
                    response.failure(f"Logout failed: {response.text}")

    def get_auth_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if self.project_id:
            headers["X-Project-ID"] = str(self.project_id)
        return headers

    def create_or_select_project(self):
        """Create a new project or select an existing one."""
        headers = self.get_auth_headers()

        # Try to get existing projects first
        with self.client.get(
            "/api/projects/", headers=headers, catch_response=True
        ) as response:
            if response.status_code == 200:
                projects = response.json().get("results", [])
                if projects:
                    self.project_id = projects[0]["id"]
                    response.success()
                    return
                response.success()

        # Create a new project if none exist
        project_data = self.data_gen.generate_project()
        with self.client.post(
            "/api/projects/",
            json=project_data,
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.project_id = response.json()["id"]
                response.success()
            else:
                response.failure(f"Project creation failed: {response.text}")

    # Health check tasks
    @task(1)
    def check_health(self):
        """Check system health endpoint."""
        self.client.get("/health/")

    @task(1)
    def check_api_health(self):
        """Check API health endpoint."""
        self.client.get("/api/health/")

    # Dataset operations
    @task(5)
    def list_datasets(self):
        """List available datasets."""
        headers = self.get_auth_headers()
        params = self.data_gen.generate_search_query()

        with self.client.get(
            "/api/datasets/",
            params={k: v for k, v in params.items() if v is not None},
            headers=headers,
            name="/api/datasets/[LIST]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                datasets = response.json().get("results", [])
                if datasets and not self.dataset_id:
                    self.dataset_id = datasets[0]["id"]
                response.success()
            else:
                response.failure(f"Failed to list datasets: {response.text}")

    @task(3)
    def create_dataset(self):
        """Create a new dataset."""
        if not self.auth_token:
            raise RescheduleTask()

        headers = self.get_auth_headers()
        dataset_data = self.data_gen.generate_dataset()

        with self.client.post(
            "/api/datasets/",
            json=dataset_data,
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.dataset_id = response.json()["id"]
                response.success()
                # Add some samples to the dataset
                self.add_dataset_samples()
            else:
                response.failure(f"Dataset creation failed: {response.text}")

    def add_dataset_samples(self):
        """Add samples to a dataset."""
        if not self.dataset_id:
            return

        headers = self.get_auth_headers()
        samples = self.data_gen.generate_dataset_samples(
            num_samples=random.randint(5, 20)
        )

        with self.client.post(
            f"/api/datasets/{self.dataset_id}/samples/",
            json={"samples": samples},
            headers=headers,
            name="/api/datasets/[ID]/samples/",
            catch_response=True,
        ) as response:
            if response.status_code in [200, 201]:
                response.success()
            else:
                response.failure(f"Failed to add samples: {response.text}")

    @task(2)
    def import_dataset(self):
        """Import dataset from CSV."""
        if not self.auth_token:
            raise RescheduleTask()

        headers = self.get_auth_headers()
        headers.pop("Content-Type", None)  # Let requests set multipart content type

        csv_data = self.data_gen.generate_csv_data(num_rows=random.randint(50, 200))
        files = {"file": ("test_data.csv", csv_data, "text/csv")}

        with self.client.post(
            "/api/datasets/import/",
            files=files,
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code in [200, 201, 202]:
                response.success()
            else:
                response.failure(f"Dataset import failed: {response.text}")

    # Rubric operations
    @task(4)
    def list_rubrics(self):
        """List available rubrics."""
        headers = self.get_auth_headers()

        with self.client.get(
            "/api/rubrics/",
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                rubrics = response.json().get("results", [])
                if rubrics and not self.rubric_id:
                    self.rubric_id = rubrics[0]["id"]
                response.success()
            else:
                response.failure(f"Failed to list rubrics: {response.text}")

    @task(3)
    def create_rubric(self):
        """Create a new rubric with criteria."""
        if not self.auth_token:
            raise RescheduleTask()

        headers = self.get_auth_headers()
        rubric_data = self.data_gen.generate_rubric()

        with self.client.post(
            "/api/rubrics/",
            json=rubric_data,
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.rubric_id = response.json()["id"]
                response.success()
                # Add criteria to the rubric
                self.add_rubric_criteria()
            else:
                response.failure(f"Rubric creation failed: {response.text}")

    def add_rubric_criteria(self):
        """Add criteria to a rubric."""
        if not self.rubric_id:
            return

        headers = self.get_auth_headers()
        criteria = self.data_gen.generate_criteria(num_criteria=random.randint(3, 7))

        for criterion in criteria:
            with self.client.post(
                f"/api/rubrics/{self.rubric_id}/criteria/",
                json=criterion,
                headers=headers,
                name="/api/rubrics/[ID]/criteria/",
                catch_response=True,
            ) as response:
                if response.status_code == 201:
                    response.success()
                else:
                    response.failure(f"Failed to add criterion: {response.text}")

    # Evaluation operations
    @task(6)
    def list_evaluations(self):
        """List evaluation runs."""
        headers = self.get_auth_headers()
        params = self.data_gen.generate_search_query()

        with self.client.get(
            "/api/evaluations/runs/",
            params={k: v for k, v in params.items() if v is not None},
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                evaluations = response.json().get("results", [])
                if evaluations and not self.evaluation_id:
                    self.evaluation_id = evaluations[0]["id"]
                response.success()
            else:
                response.failure(f"Failed to list evaluations: {response.text}")

    @task(2)
    def create_evaluation(self):
        """Create and start an evaluation run."""
        if not all([self.auth_token, self.dataset_id, self.rubric_id]):
            raise RescheduleTask()

        headers = self.get_auth_headers()
        eval_data = self.data_gen.generate_evaluation_run()
        eval_data["dataset_id"] = self.dataset_id
        eval_data["rubric_id"] = self.rubric_id

        with self.client.post(
            "/api/evaluations/runs/",
            json=eval_data,
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.evaluation_id = response.json()["id"]
                response.success()
                # Start the evaluation
                self.start_evaluation()
            else:
                response.failure(f"Evaluation creation failed: {response.text}")

    def start_evaluation(self):
        """Start an evaluation run."""
        if not self.evaluation_id:
            return

        headers = self.get_auth_headers()

        with self.client.post(
            f"/api/evaluations/runs/{self.evaluation_id}/start/",
            headers=headers,
            name="/api/evaluations/runs/[ID]/start/",
            catch_response=True,
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"Failed to start evaluation: {response.text}")

    @task(4)
    def check_evaluation_status(self):
        """Check the status of an evaluation run."""
        if not self.evaluation_id:
            raise RescheduleTask()

        headers = self.get_auth_headers()

        with self.client.get(
            f"/api/evaluations/runs/{self.evaluation_id}/",
            headers=headers,
            name="/api/evaluations/runs/[ID]/",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to check evaluation status: {response.text}")

    @task(3)
    def get_evaluation_results(self):
        """Get results of an evaluation run."""
        if not self.evaluation_id:
            raise RescheduleTask()

        headers = self.get_auth_headers()

        with self.client.get(
            f"/api/evaluations/runs/{self.evaluation_id}/results/",
            headers=headers,
            name="/api/evaluations/runs/[ID]/results/",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to get evaluation results: {response.text}")

    # Monitoring operations
    @task(5)
    def get_metrics_summary(self):
        """Get performance metrics summary."""
        headers = self.get_auth_headers()
        params = self.data_gen.generate_metric_query()

        with self.client.get(
            "/api/monitoring/metrics/summary/",
            params=params,
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to get metrics summary: {response.text}")

    @task(3)
    def get_model_metrics(self):
        """Get model-specific performance metrics."""
        headers = self.get_auth_headers()

        with self.client.get(
            "/api/monitoring/metrics/models/",
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to get model metrics: {response.text}")

    @task(2)
    def check_anomalies(self):
        """Check for performance anomalies."""
        headers = self.get_auth_headers()

        with self.client.get(
            "/api/monitoring/metrics/anomalies/",
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to check anomalies: {response.text}")

    # Webhook operations
    @task(2)
    def create_webhook(self):
        """Create a webhook configuration."""
        if not self.auth_token:
            raise RescheduleTask()

        headers = self.get_auth_headers()
        webhook_data = self.data_gen.generate_webhook()

        with self.client.post(
            "/api/webhooks/",
            json=webhook_data,
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.webhook_id = response.json()["id"]
                response.success()
            else:
                response.failure(f"Webhook creation failed: {response.text}")

    @task(1)
    def test_webhook(self):
        """Test webhook delivery."""
        if not self.webhook_id:
            raise RescheduleTask()

        headers = self.get_auth_headers()

        with self.client.post(
            f"/api/webhooks/{self.webhook_id}/test/",
            headers=headers,
            name="/api/webhooks/[ID]/test/",
            catch_response=True,
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"Webhook test failed: {response.text}")

    # Complex workflow simulation
    @task(1)
    def complete_workflow(self):
        """Execute a complete workflow from dataset to evaluation."""
        if not self.auth_token:
            raise RescheduleTask()

        # Create dataset
        self.create_dataset()
        time.sleep(1)

        # Create rubric
        self.create_rubric()
        time.sleep(1)

        # Create and run evaluation
        if self.dataset_id and self.rubric_id:
            self.create_evaluation()
            time.sleep(2)

            # Check status multiple times
            for _ in range(3):
                self.check_evaluation_status()
                time.sleep(2)

            # Get results
            self.get_evaluation_results()


class AdminUser(SternaUser):
    """Simulates an admin user with different behavior patterns."""

    wait_time = between(2, 5)  # Admins interact less frequently

    @task(10)
    def view_dashboard_metrics(self):
        """Admin viewing system-wide metrics."""
        self.get_metrics_summary()
        self.get_model_metrics()
        self.check_anomalies()

    @task(5)
    def manage_projects(self):
        """Admin managing projects."""
        headers = self.get_auth_headers()

        # List all projects
        with self.client.get(
            "/api/projects/",
            params={"page_size": 50},
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to list projects: {response.text}")

    @task(3)
    def audit_operations(self):
        """Admin reviewing audit logs."""
        headers = self.get_auth_headers()

        with self.client.get(
            "/api/audit/logs/",
            params={"page_size": 100, "ordering": "-created_at"},
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to get audit logs: {response.text}")


# Event handlers for reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    print(f"Load test starting with host: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    print("Load test completed")
    print(f"Total requests: {environment.stats.total.num_requests}")
    print(f"Total failures: {environment.stats.total.num_failures}")
    print(f"Average response time: {environment.stats.total.avg_response_time:.2f}ms")
    print(f"RPS: {environment.stats.total.current_rps:.2f}")
