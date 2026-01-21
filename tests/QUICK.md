# QUICK – Test Commands

## Run all unit tests

```bash
uv run pytest tests/ -v -m "not integration"
```

Duration: ~0.3 seconds
No external services required

## Run all tests

```bash
uv run pytest
```

Duration: ~1 second
Coverage: 90% minimum required (HTML + terminal reports)

## Run all integration tests

```bash
uv run pytest tests/test_integration/ -v
```

Duration: ~0.5 seconds
No external services required (uses in-memory databases)
