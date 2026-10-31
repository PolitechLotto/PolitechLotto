# 005: Database

## Status

Proposed, 31.10.2026

## Context

The backend microservices described in [ADR 002](002-Microservice-architecture.md) need persistent
storage for users, games, draws, coupons and wallets. An informal decision has been made when
pitching the project, that we should be using PostgreSQL. This document will formalize this decision.

## Decision

### Database

The team has agreed upon [PostgreSQL](https://www.postgresql.org/). We will be using the newest stable
version available at the time of setting it up, running in Docker Compose alongside the services.

### Data ownership

Each microservice owns its data and has a separate database. Services do not read or write other
services' databases, and communicate only through their APIs or the message queue.

### Libraries

- ORM: [SQLAlchemy](https://www.sqlalchemy.org/)
- Migrations: [Alembic](https://alembic.sqlalchemy.org/)

## Consequences

All members of the team will stick to the decisions made in this document.
