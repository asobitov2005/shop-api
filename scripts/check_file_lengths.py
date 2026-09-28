from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_SUFFIXES = {".py", ".sh"}
EXCLUDED_PARTS = {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache"}


def main() -> int:
    failures = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in CODE_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > 300:
            failures.append((path.relative_to(ROOT), count))
    for path, count in failures:
        print(f"{path}: {count} lines (maximum 300)")
    if failures:
        return 1
    print("All authored code files are within the 300-line limit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
