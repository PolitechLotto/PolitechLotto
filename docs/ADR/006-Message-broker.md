# 006: Message broker

## Status

Proposed, 31.10.2026

## Context

The backend microservices described in [ADR 002](002-Microservice-architecture.md) need to react to
events from other services. We need a tool for asynchronous communication between services.

The candidates were [Kafka](https://kafka.apache.org/) and [RabbitMQ](https://www.rabbitmq.com/).

## Decision

The team has agreed upon [RabbitMQ](https://www.rabbitmq.com/) as the message broker. We will be
using the newest stable version available at the time of setting it up, running in Docker Compose
alongside the services.

Services publish events, and each interested service consumes them from its own queue.

### Rejected options

- **Kafka**: built for high-volume event streaming, which is much more than this project needs, and
  heavier to run and learn.

## Consequences

All members of the team will stick to the decisions made in this document.
