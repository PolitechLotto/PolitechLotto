# 002: Microservice architecture

## Status

Proposed, 16.10.2026

## Context

An informal decision has been made when pitching the project, that we should be using a microservice
architecture for our backend. This document will formalize this decision, and make concrete
decisions when it comes to architecture of these microservices.

## Decision

### Framework

The team has agreed upon [FastAPI](https://fastapi.tiangolo.com/), a Python framework. We will be
using Python 3.14, as well as newest FastAPI version which support Python 3.14, which at the time of
writing is version 0.143.0.

### Testing

The team has agreed upon [pytest](https://docs.pytest.org/en/stable/) as our testing library of
choice for unit testing.

### Microservice structure

The team has agreed upon a simplified version of a hexagonal architecture:

```shell
example_service/
├── src
│   └── example_service
│       ├── connectors
│       │   ├── __init__.py
│       │   └── db.py
│       ├── handlers
│       │   ├── __init__.py
│       │   └── handlers_v1.py
│       ├── routers
│       │   ├── __init__.py
│       │   └── api_v1.py
│       ├── __init__.py
│       └── main.py
├── test
│   ├── __init__.py
│   ├── test_api.py
│   ├── test_db.py
│   └── test_handlers.py
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── tox.ini
```

Layers explaination:

- `connectors/` - adapters, which implement communication with a database
- `handlers/` - adapters, which implement business logic
- `routers/` - REST endpoints definitions
- `test/` - directory for unit tests, with a file for each module of the service

### Development libraries

Other notable libraries for keeping high code quality, that the team agreed upon using:

- [tox](https://github.com/tox-dev/tox) - virtual environment management + testing CLI tool
- [ruff](https://docs.astral.sh/ruff/) - linter and code formatter
- [mypy](https://mypy-lang.org/) - static type checker

## Consequences

All members of the team will stick to the architecture presented in this document.

