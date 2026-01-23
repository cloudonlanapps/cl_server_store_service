# QUICK – Test Commands

Quick reference for common test commands. See [README.md](README.md) for comprehensive testing guide.

## Run all tests (with coverage)

```bash
uv run pytest
```

Duration: ~1 second
Coverage: 90% minimum required (HTML + terminal reports)

---

## Run all unit tests (no integration)

```bash
uv run pytest -m "not integration"
```

Duration: ~0.3 seconds
No external services required

---

## Run all integration tests

```bash
uv run pytest tests/test_store/test_integration/ -v
```

Duration: ~0.5 seconds
Uses in-memory databases, no external services required

---

## Run specific test file

```bash
uv run pytest tests/test_m_insight_worker.py -v
```

Duration: ~0.1 seconds

---

## Run single test function

```bash
uv run pytest tests/test_entity_crud.py::test_create_entity -v
```

Duration: < 0.1 seconds

---

## Run without coverage (faster development)

```bash
uv run pytest --no-cov
```

Duration: ~0.5 seconds
No coverage reports generated - useful for quick iteration

---

## Run tests matching keyword

```bash
uv run pytest -k "mqtt" -v
```

Runs all tests with "mqtt" in name
Duration: ~0.2 seconds

---

## Run tests for specific module

```bash
# Store service tests
uv run pytest tests/test_store/ -v

# mInsight tests
uv run pytest tests/test_m_insight_*.py -v

# MQTT tests
uv run pytest tests/test_mqtt_*.py tests/test_m_insight_mqtt.py -v
```

---

## View coverage report

```bash
# Open HTML coverage report
open htmlcov/index.html

# Or on Linux
xdg-open htmlcov/index.html
```

Shows line-by-line coverage with highlighted uncovered lines

---

## Override coverage threshold (for debugging)

```bash
uv run pytest --cov-fail-under=0
```

Allows tests to pass even with < 90% coverage

---

## Run tests with verbose output

```bash
uv run pytest -vv
```

Shows full test names and detailed assertion output

---

## Run tests and stop on first failure

```bash
uv run pytest -x
```

Useful for quickly identifying first failing test

---

## Run only failed tests from last run

```bash
uv run pytest --lf
```

Re-runs only tests that failed last time

---

## Run tests in parallel (if pytest-xdist installed)

```bash
uv run pytest -n auto
```

Note: pytest-xdist is not installed by default, requires `uv add --dev pytest-xdist`

---

## Check test count

```bash
uv run pytest --collect-only
```

Shows all tests that would be run without executing them
Total: 257 tests across 34 test files

---

## Common Troubleshooting Commands

### Check for file handle leaks
```bash
# macOS/Linux
lsof -p $(pgrep -f pytest) | wc -l
```

### Increase file descriptor limit
```bash
ulimit -n 4096
```

### Clear pytest cache
```bash
rm -rf .pytest_cache htmlcov
```

### Verify ExifTool and ffprobe installed
```bash
exiftool -ver && ffprobe -version
```

---

## Performance Testing

### Run tests 10 times to check for flakiness
```bash
for i in {1..10}; do uv run pytest tests/test_specific.py || break; done
```

### Time a specific test
```bash
time uv run pytest tests/test_m_insight_worker.py --no-cov
```

---

**See [README.md](README.md) for comprehensive testing guide and [Troubleshooting section](README.md#troubleshooting) for common issues.**
