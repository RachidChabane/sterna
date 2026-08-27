"""
Realistic data generators for load testing.

Provides functions to generate realistic test data for various API endpoints.
"""

import random
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from faker import Faker


class DataGenerator:
    """Generate realistic test data for load testing."""

    def __init__(self, seed: Optional[int] = None):
        """Initialize data generator with optional seed for reproducibility."""
        self.faker = Faker()
        if seed:
            Faker.seed(seed)
            random.seed(seed)

    def generate_user(self) -> Dict[str, str]:
        """Generate user registration data."""
        email = self.faker.unique.email()
        return {
            "email": email,
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "first_name": self.faker.first_name(),
            "last_name": self.faker.last_name(),
        }

    def generate_project(self) -> Dict[str, Any]:
        """Generate project creation data."""
        project_types = ["ml_research", "production", "experimentation", "testing"]
        return {
            "name": f"{self.faker.company()} {self.faker.bs()}",
            "description": self.faker.text(max_nb_chars=200),
            "settings": {
                "type": random.choice(project_types),
                "max_evaluations_per_day": random.randint(100, 1000),
                "default_model_tier": random.choice(["budget", "balanced", "quality"]),
                "cost_limit_per_month": random.randint(100, 5000),
            },
        }

    def generate_dataset(self, num_samples: Optional[int] = None) -> Dict[str, Any]:
        """Generate dataset creation data."""
        if num_samples is None:
            num_samples = random.randint(10, 100)

        dataset_types = [
            "qa_pairs",
            "text_generation",
            "classification",
            "summarization",
            "translation",
        ]

        return {
            "name": f"Dataset {self.faker.word()} {uuid.uuid4().hex[:8]}",
            "description": self.faker.sentence(),
            "type": random.choice(dataset_types),
            "metadata": {
                "source": self.faker.word(),
                "version": f"v{random.randint(1, 5)}.{random.randint(0, 9)}",
                "language": random.choice(["en", "es", "fr", "de", "ja"]),
            },
        }

    def generate_dataset_samples(self, num_samples: int = 10) -> List[Dict[str, Any]]:
        """Generate dataset samples."""
        samples = []
        for _ in range(num_samples):
            sample_type = random.choice(["qa", "generation", "classification"])

            sample: Dict[str, Any]
            if sample_type == "qa":
                sample = {
                    "input": self.faker.sentence(nb_words=15),
                    "expected_output": self.faker.sentence(nb_words=10),
                    "context": self.faker.paragraph(nb_sentences=3),
                }
            elif sample_type == "generation":
                sample = {
                    "prompt": self.faker.sentence(nb_words=20),
                    "expected_completion": self.faker.paragraph(nb_sentences=2),
                    "max_tokens": random.randint(50, 500),
                }
            else:  # classification
                sample = {
                    "text": self.faker.paragraph(nb_sentences=4),
                    "expected_label": random.choice(
                        ["positive", "negative", "neutral"]
                    ),
                    "confidence": random.uniform(0.7, 1.0),
                }

            sample["metadata"] = {
                "category": self.faker.word(),
                "difficulty": random.choice(["easy", "medium", "hard"]),
                "tags": [self.faker.word() for _ in range(random.randint(1, 5))],
            }
            samples.append(sample)

        return samples

    def generate_csv_data(self, num_rows: int = 100) -> str:
        """Generate CSV data for import testing."""
        headers = ["id", "input", "output", "category", "difficulty", "timestamp"]
        rows = [",".join(headers)]

        for i in range(num_rows):
            row = [
                str(i + 1),
                f'"{self.faker.sentence(nb_words=10)}"',
                f'"{self.faker.sentence(nb_words=8)}"',
                random.choice(["A", "B", "C", "D"]),
                random.choice(["easy", "medium", "hard"]),
                self.faker.date_time_between(
                    start_date="-30d", end_date="now"
                ).isoformat(),
            ]
            rows.append(",".join(row))

        return "\n".join(rows)

    def generate_rubric(self) -> Dict[str, Any]:
        """Generate rubric creation data."""
        model_tiers = ["budget", "balanced", "quality", "custom"]

        return {
            "name": f"Rubric {self.faker.word()} {uuid.uuid4().hex[:6]}",
            "description": self.faker.sentence(),
            "model_tier": random.choice(model_tiers),
            "settings": {
                "max_cost_per_eval": random.uniform(0.01, 0.5),
                "timeout_seconds": random.randint(30, 300),
                "retry_on_failure": random.choice([True, False]),
                "use_caching": random.choice([True, False]),
            },
        }

    def generate_criteria(self, num_criteria: int = 5) -> List[Dict[str, Any]]:
        """Generate rubric criteria."""
        criteria = []
        criterion_types = ["binary", "scale", "categorical", "numeric", "text"]

        for i in range(num_criteria):
            criterion_type = random.choice(criterion_types)

            base_criterion = {
                "name": f"Criterion {self.faker.word()}",
                "description": self.faker.sentence(),
                "type": criterion_type,
                "weight": random.uniform(0.5, 2.0),
                "required": random.choice([True, False]),
            }

            if criterion_type == "scale":
                base_criterion["scale_min"] = 1
                base_criterion["scale_max"] = random.choice([5, 10])
            elif criterion_type == "categorical":
                base_criterion["categories"] = [
                    self.faker.word() for _ in range(random.randint(3, 7))
                ]
            elif criterion_type == "numeric":
                base_criterion["min_value"] = 0
                base_criterion["max_value"] = random.randint(100, 1000)

            base_criterion["prompt_template"] = self.faker.paragraph(nb_sentences=2)
            criteria.append(base_criterion)

        return criteria

    def generate_evaluation_run(self) -> Dict[str, Any]:
        """Generate evaluation run configuration."""
        return {
            "name": f"Eval Run {self.faker.word()} {datetime.now().strftime('%Y%m%d_%H%M')}",
            "description": self.faker.sentence(),
            "config": {
                "model_tier": random.choice(["budget", "balanced", "quality"]),
                "sample_size": random.randint(10, 100),
                "parallel_workers": random.randint(1, 10),
                "timeout_per_sample": random.randint(10, 60),
                "stop_on_failure": random.choice([True, False]),
            },
        }

    def generate_webhook(self) -> Dict[str, Any]:
        """Generate webhook configuration."""
        event_types = [
            "dataset.created",
            "dataset.updated",
            "evaluation.started",
            "evaluation.completed",
            "evaluation.failed",
            "sterna.passed",
            "sterna.failed",
        ]

        return {
            "name": f"Webhook {self.faker.word()}",
            "url": self.faker.url(),
            "events": random.sample(event_types, k=random.randint(1, 4)),
            "active": True,
            "headers": {
                "X-Custom-Header": self.faker.uuid4(),
                "X-Environment": random.choice(["dev", "staging", "production"]),
            },
        }

    def generate_search_query(self) -> Dict[str, Any]:
        """Generate search/filter parameters."""
        date_from = self.faker.date_time_between(start_date="-30d", end_date="-7d")
        date_to = self.faker.date_time_between(start_date="-6d", end_date="now")

        return {
            "q": self.faker.word() if random.random() > 0.5 else None,
            "status": random.choice(
                [None, "pending", "running", "completed", "failed"]
            ),
            "date_from": date_from.isoformat() if random.random() > 0.5 else None,
            "date_to": date_to.isoformat() if random.random() > 0.5 else None,
            "page": random.randint(1, 5),
            "page_size": random.choice([10, 25, 50, 100]),
            "ordering": random.choice(
                [None, "created_at", "-created_at", "name", "-name", "status"]
            ),
        }

    def generate_metric_query(self) -> Dict[str, Any]:
        """Generate performance metric query parameters."""
        time_ranges = ["1h", "6h", "24h", "7d", "30d"]
        aggregations = ["mean", "median", "p50", "p95", "p99"]

        return {
            "time_range": random.choice(time_ranges),
            "aggregation": random.choice(aggregations),
            "group_by": random.choice([None, "model", "project", "user"]),
            "metrics": random.sample(
                ["latency", "tokens", "cost", "success_rate", "error_rate"],
                k=random.randint(1, 3),
            ),
        }

    def generate_bulk_operation(
        self, operation_type: str, num_items: int = 5
    ) -> Dict[str, Any]:
        """Generate bulk operation data."""
        operations: Dict[str, Dict[str, Any]] = {
            "delete": {
                "ids": [str(uuid.uuid4()) for _ in range(num_items)],
                "confirm": True,
            },
            "update": {
                "ids": [str(uuid.uuid4()) for _ in range(num_items)],
                "updates": {
                    "status": random.choice(["active", "inactive", "archived"]),
                    "metadata": {"bulk_updated": datetime.now().isoformat()},
                },
            },
            "export": {
                "ids": [str(uuid.uuid4()) for _ in range(num_items)],
                "format": random.choice(["csv", "json", "jsonl", "parquet"]),
                "include_metadata": random.choice([True, False]),
            },
        }

        return operations.get(operation_type, operations["delete"])

    def generate_file_upload(self, file_type: str = "csv", size_kb: int = 100) -> bytes:
        """Generate file data for upload testing."""
        if file_type == "csv":
            content = self.generate_csv_data(
                num_rows=size_kb * 10
            )  # Rough size estimate
            return content.encode("utf-8")
        elif file_type == "json":
            import json

            data = {
                "samples": self.generate_dataset_samples(num_samples=size_kb),
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "version": "1.0",
                },
            }
            return json.dumps(data, indent=2).encode("utf-8")
        else:
            # Generate random binary data
            return bytes(random.getrandbits(8) for _ in range(size_kb * 1024))

    def generate_complex_workflow(self) -> Dict[str, Any]:
        """Generate data for a complex multi-step workflow."""
        return {
            "workflow": {
                "create_project": self.generate_project(),
                "create_dataset": self.generate_dataset(),
                "samples": self.generate_dataset_samples(num_samples=20),
                "create_rubric": self.generate_rubric(),
                "criteria": self.generate_criteria(num_criteria=5),
                "run_evaluation": self.generate_evaluation_run(),
                "webhook": self.generate_webhook(),
            }
        }


# Singleton instance for convenience
data_generator = DataGenerator(seed=42)
