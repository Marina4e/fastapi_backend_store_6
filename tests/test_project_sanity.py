import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_entrypoints_exist() -> None:
    expected_files = [
        ROOT / "app" / "main.py",
        ROOT / "app" / "api" / "routes" / "purchase.py",
        ROOT / "app" / "services" / "purchase_service.py",
        ROOT / "app" / "repositories" / "products.py",
        ROOT / "nginx" / "default.conf",
        ROOT / "tests" / "locustfile.py",
        ROOT / "tests" / "load_test.py",
        ROOT / "docker-compose.yml",
        ROOT / "README.md",
        ROOT / ".env.example",
        ROOT / ".github" / "workflows" / "sanity.yml",
    ]

    for path in expected_files:
        assert path.exists(), f"Missing required project file: {path}"


def test_local_env_file_is_not_committed() -> None:
    assert not (ROOT / ".env").exists(), "Local .env must stay out of Git; use .env.example."


def test_python_files_are_parseable() -> None:
    source_roots = [ROOT / "app", ROOT / "tests"]
    for source_root in source_roots:
        for path in source_root.rglob("*.py"):
            if ".venv" in path.parts or "__pycache__" in path.parts:
                continue
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_app_pycache_outside_virtualenv() -> None:
    pycache_dirs = [
        path
        for path in (ROOT / "app").rglob("__pycache__")
        if ".venv" not in path.parts and "venv" not in path.parts
    ]
    assert pycache_dirs == [], f"Remove generated __pycache__ directories: {pycache_dirs}"
