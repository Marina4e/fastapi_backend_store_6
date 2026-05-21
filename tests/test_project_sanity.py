from pathlib import Path


def test_project_entrypoints_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    expected_files = [
        root / "app" / "main.py",
        root / "app" / "api" / "routes" / "purchase.py",
        root / "app" / "services" / "purchase_service.py",
        root / "app" / "repositories" / "products.py",
        root / "nginx" / "default.conf",
        root / "tests" / "locustfile.py",
        root / "tests" / "load_test.py",
        root / "docker-compose.yml",
        root / "README.md",
    ]

    for path in expected_files:
        assert path.exists(), f"Missing required project file: {path}"
