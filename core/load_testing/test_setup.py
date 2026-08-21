#!/usr/bin/env python3
"""
Test script to verify load testing setup.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        from load_testing.config import LoadProfile, TestConfig  # noqa: F401 -- import IS the test

        print("[OK] Config module imported successfully")
    except ImportError as e:
        print(f"[FAIL] Failed to import config: {e}")
        return False

    try:
        from load_testing.data_generators import DataGenerator  # noqa: F401 -- import IS the test

        print("[OK] Data generators imported successfully")
    except ImportError as e:
        print(f"[FAIL] Failed to import data generators: {e}")
        return False

    try:
        from load_testing.baselines import BaselineTracker  # noqa: F401 -- import IS the test

        print("[OK] Baseline tracker imported successfully")
    except ImportError as e:
        print(f"[FAIL] Failed to import baselines: {e}")
        return False

    try:
        from load_testing.reports import ReportGenerator  # noqa: F401 -- import IS the test

        print("[OK] Report generator imported successfully")
    except ImportError as e:
        print(f"[FAIL] Failed to import reports: {e}")
        return False

    try:
        import locust

        print(f"[OK] Locust {locust.__version__} imported successfully")
    except ImportError as e:
        print(f"[FAIL] Failed to import locust: {e}")
        return False

    return True


def test_data_generation():
    """Test data generation functionality."""
    print("\nTesting data generation...")

    from load_testing.data_generators import DataGenerator

    gen = DataGenerator(seed=42)

    # Test user generation
    user = gen.generate_user()
    assert "email" in user
    assert "password" in user
    print(f"[OK] Generated user: {user['email']}")

    # Test project generation
    project = gen.generate_project()
    assert "name" in project
    assert "settings" in project
    print(f"[OK] Generated project: {project['name']}")

    # Test dataset generation
    dataset = gen.generate_dataset(num_samples=10)
    assert "name" in dataset
    assert "type" in dataset
    print(f"[OK] Generated dataset: {dataset['name']}")

    # Test samples generation
    samples = gen.generate_dataset_samples(num_samples=5)
    assert len(samples) == 5
    print(f"[OK] Generated {len(samples)} samples")

    # Test rubric generation
    rubric = gen.generate_rubric()
    assert "name" in rubric
    assert "model_tier" in rubric
    print(f"[OK] Generated rubric: {rubric['name']}")

    # Test criteria generation
    criteria = gen.generate_criteria(num_criteria=3)
    assert len(criteria) == 3
    print(f"[OK] Generated {len(criteria)} criteria")

    return True


def test_baseline_tracking():
    """Test baseline tracking functionality."""
    print("\nTesting baseline tracking...")

    from load_testing.baselines import BaselineTracker, PerformanceMetric
    from datetime import datetime

    tracker = BaselineTracker()

    # Create a test metric
    metric = PerformanceMetric(
        endpoint="test_endpoint",
        timestamp=datetime.now(),
        request_count=100,
        failure_count=2,
        median_response_time=50,
        average_response_time=55,
        min_response_time=10,
        max_response_time=200,
        p50=50,
        p95=150,
        p99=190,
        requests_per_second=10.5,
    )

    # Record the metric
    tracker.record_metric(metric)
    print("[OK] Recorded performance metric")

    # Test summary generation
    summary = tracker.generate_summary()
    assert "endpoints" in summary
    assert "overall_passed" in summary
    print("[OK] Generated performance summary")

    return True


def test_config():
    """Test configuration."""
    print("\nTesting configuration...")

    from load_testing.config import LoadProfile, TestConfig

    # Test load profiles
    profiles = list(LoadProfile)
    print(f"[OK] Found {len(profiles)} load profiles: {[p.value for p in profiles]}")

    # Test profile configuration
    load_config = TestConfig.get_profile(LoadProfile.LOAD)
    assert "users" in load_config
    assert load_config["users"] == 100
    print(f"[OK] Load profile configured: {load_config['users']} users")

    # Test URL generation
    url = TestConfig.get_full_url("login")
    assert "/api/auth/login/" in url
    print(f"[OK] Generated URL: {url}")

    # Test baselines
    assert len(TestConfig.PERFORMANCE_BASELINES) > 0
    print(f"[OK] Found {len(TestConfig.PERFORMANCE_BASELINES)} baseline configurations")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Load Testing Setup Verification")
    print("=" * 60)

    all_passed = True

    # Test imports
    if not test_imports():
        all_passed = False
        print("\nImport test failed. Please install dependencies:")
        print("  pip install locust gevent greenlet faker")
        return 1

    # Test configuration
    if not test_config():
        all_passed = False
        print("\nConfiguration test failed")
        return 1

    # Test data generation
    try:
        if not test_data_generation():
            all_passed = False
            print("\nData generation test failed")
    except Exception as e:
        print(f"\nData generation test error: {e}")
        all_passed = False

    # Test baseline tracking
    try:
        if not test_baseline_tracking():
            all_passed = False
            print("\nBaseline tracking test failed")
    except Exception as e:
        print(f"\nBaseline tracking test error: {e}")
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed! Load testing suite is ready.")
        print("\nNext steps:")
        print("1. Start your Django server: make dev")
        print("2. Create test user: See README.md")
        print("3. Run load tests: make load-test-smoke")
        print("4. View reports: make load-test-report")
    else:
        print("Some tests failed. Please check the errors above.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
