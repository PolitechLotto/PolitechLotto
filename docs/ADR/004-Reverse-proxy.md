# 004: Reverse proxy and API gateway

## Status

Proposed, 31.10.2026

## Context

The backend consists of several FastAPI microservices (`auth`, `lotto`, `betting`, `wallet`, `admin`,
`notifications`), described in [ADR 002](002-Microservice-architecture.md), all running in Docker
Compose.

We need a component which will:

- route requests to the correct service by path (e.g. `/api/wallet/*` to `wallet`)
- verify the JWT of every protected request, and pass the user's identity to the services
- apply rate limiting (e.g. on login and coupon purchase)
- handle CORS

The candidates are [Traefik](https://traefik.io/traefik/), [nginx](https://nginx.org/) and
[OpenResty](https://openresty.org/).

## Comparison

| | Traefik | nginx | OpenResty |
|---|---|---|---|
| Configuration | Docker labels on each service + a small static file | Hand-written `nginx.conf` | Hand-written `nginx.conf` + Lua scripts |
| Adding a new service | Add labels to the service in `docker-compose.yml` | Edit config, reload | Edit config, reload |
| JWT verification | `ForwardAuth` to `auth` | `auth_request` to `auth` | In the gateway, with `lua-resty-jwt` |
| Rate limiting | `RateLimit` middleware | `limit_req` | `limit_req`, or Lua for custom rules |
| CORS | `Headers` middleware | Manual `add_header` and `OPTIONS` handling | Same as nginx, or Lua |

## Decision

The team has agreed upon using **OpenResty** as the reverse proxy and API gateway. We will be using
the newest stable version available at the time of setting it up.

### Configuration

- Routing is defined by path in `nginx.conf`, one `location` per service (e.g. `/api/wallet/`).
- Upstreams are resolved with Docker's internal DNS, so the gateway starts even when a service is not up yet.
- Rate limiting is configured with `limit_req`, at least on login, token refresh and coupon purchase.
- CORS headers and `OPTIONS` preflight requests are handled in `nginx.conf`.

### Testing

The Lua code is tested with pytest integration tests, which send requests through the gateway
running in Docker Compose.

## Consequences

All members of the team will stick to the decisions made in this document.
