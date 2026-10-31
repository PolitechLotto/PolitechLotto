# 003: Frontend architecture

## Status

Proposed, 31.10.2026

## Context

We want a formal decision on our frontend architecture and libraries before committing to the first
sprint. The frontend is a single web application that serves guests, players and the administrator
panel, and communicates with the backend microservices described in
[ADR 002](002-Microservice-architecture.md) over REST.

## Decision

### Framework

The team has agreed upon using [React](https://react.dev/) with [TypeScript](https://www.typescriptlang.org/),
built with [Vite](https://vite.dev/). We will be using the newest stable versions available at the time of starting the project.

### Libraries

- Routing: [TanStack Router](https://tanstack.com/router/latest)
- Data fetching: [TanStack Query](https://tanstack.com/query/latest)
- UI library: [HeroUI](https://heroui.com/)
- CSS framework: [Tailwind CSS](https://tailwindcss.com/)

### Testing

The team has agreed upon [Vitest](https://vitest.dev/) with [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/) for unit and
component testing.

### Application structure

The team has agreed upon a feature-based structure:

```shell
frontend/
├── src
│   ├── api
│   ├── components
│   ├── features
│   │   └── feature-name
│   │       ├── components
│   │       ├── hooks
│   │       └── index.ts
│   ├── routes
│   │   ├── __root.tsx
│   │   ├── index.tsx
│   │   └── coupons.tsx
│   └── main.tsx
├── test
├── Dockerfile
├── package.json
├── tsconfig.json
└── vite.config.ts
```

Layers explanation:

- `api/` - HTTP client and typed functions calling the backend, one file per service
- `components/` - shared, reusable UI components
- `features/` - feature modules, each with its own components and TanStack Query hooks
- `routes/` - TanStack Router file-based route definitions
- `test/` - directory for unit and component tests

### Development libraries

Other notable libraries for keeping high code quality, that the team agreed upon using:

- [Biome](https://biomejs.dev/) - linter and formatter
- `tsc` in strict mode - static type checking

## Consequences

All members of the team will stick to the architecture presented in this document.
