# 007: Database schema

## Status

Proposed, 31.10.2026

## Context

[ADR 005](005-Database.md) decided that each microservice owns its data in a separate PostgreSQL
database. This document defines the schema of each of those databases.

## Decision

### General rules

- Primary keys are UUIDs. Points are integers. Timestamps are stored in UTC.
- There are no foreign keys across databases. A column such as `user_id` holds the ID from the owning
  service (e.g. `auth.users`), and services keep it in sync through events from [ADR 006](006-Message-broker.md).

### auth

Accounts, roles and sessions.

```mermaid
erDiagram
    users ||--o{ refresh_tokens : has
    users {
        uuid id PK
        string email UK
        string username UK
        string password_hash
        enum role "player | admin"
        timestamptz created_at
        timestamptz last_login_at
        timestamptz last_seen_at
        timestamptz deleted_at
    }
    refresh_tokens {
        uuid id PK
        uuid user_id FK
        string token_hash
        timestamptz expires_at
        timestamptz revoked_at
    }
```

### lotto

Game types, prize tiers, schedules and games.

- A **game type** is defined by the administrator: its rules, price and prizes.
- A **game** is one draw of a game type, at a given time. It copies the ticket price and jackpot from
  its game type, and the administrator can change them for a single game.
- **Prize tiers** list the hit counts that win. The tier with the highest `hits` is the main prize:
  its winners split the game's jackpot. Every other tier pays a certain `fixed_prize`.
- A **game schedule** creates games repeatedly, every `interval_minutes`. One-time games are
  created directly and have no schedule.
- `seed_hash` is published before the game and `seed` after it, so players can verify the result.

```mermaid
erDiagram
    game_types ||--o{ prize_tiers : defines
    game_types ||--o{ game_schedules : has
    game_types ||--o{ games : has
    game_schedules ||--o{ games : creates
    game_types {
        uuid id PK
        string name
        string description
        int number_pool_size
        int number_pick_count
        int ticket_price
        int default_jackpot
        bool is_active
    }
    prize_tiers {
        uuid id PK
        uuid game_type_id FK
        int hits "<= number_pick_count"
        int fixed_prize
    }
    game_schedules {
        uuid id PK
        uuid game_type_id FK
        int interval_minutes
        timestamptz next_game_at
        bool is_active
    }
    games {
        uuid id PK
        uuid game_type_id FK
        uuid game_schedule_id FK "null for one-time games"
        string name
        int ticket_price
        int jackpot
        enum status "scheduled | finished | cancelled"
        timestamptz scheduled_at
        timestamptz started_at
        timestamptz finished_at
        string seed_hash
        string seed
        int[] winning_numbers
    }
```

### betting

Coupons. `game_type_id` is stored for filtering the coupon history by game type. `hits` (matched
numbers) and `points_won` are set when the game is finished.

```mermaid
erDiagram
    coupons {
        uuid id PK
        uuid user_id "auth.users"
        uuid game_id "lotto.games"
        uuid game_type_id "lotto.game_types"
        int[] numbers
        bool is_quick_pick
        int price
        enum status "active | won | lost | refunded"
        int hits
        int point_won
        timestamptz created_at
    }
```

### wallet

Balances and the history of operations. Every change of balance is a transaction. `total_won` is kept
for the winnings leaderboard.

```mermaid
erDiagram
    wallets ||--o{ transactions : has
    wallets {
        uuid user_id PK "auth.users"
        int balance
        int total_won
        timestamptz updated_at
    }
    transactions {
        uuid id PK
        uuid user_id FK
        int amount
        int balance_after
        enum type "signup_bonus | purchase | prize | refund | admin_adjustment"
        uuid reference_id "coupon or admin action"
        timestamptz created_at
    }
```

### admin

A log of global administrator actions, and generated reports.

- `target_type` says which kind of object `target_id` points to, since it lives in another service.
- When a report is generated, statistics are read from the other services and saved as rows in the
  table for that report type:
  - `daily_summary`: one row per day, for the charts in the statistics view
  - `game_stats`: one row per game type, for game popularity
  - `user_activity`: one row per player

```mermaid
erDiagram
    reports ||--o{ daily_summary_report_rows : contains
    reports ||--o{ game_stats_report_rows : contains
    reports ||--o{ user_activity_report_rows : contains
    admin_actions {
        uuid id PK
        uuid admin_id "auth.users"
        enum action "user_deleted | points_adjusted | game_type_created | game_type_updated | game_type_disabled | game_schedule_created | game_schedule_updated | game_schedule_disabled | game_created | game_cancelled | report_generated"
        enum target_type "user | wallet | game_type | game_schedule | game | report"
        uuid target_id
        string description
        timestamptz created_at
    }
    reports {
        uuid id PK
        uuid created_by "auth.users"
        enum type "daily_summary | game_stats | user_activity"
        date period_from
        date period_to
        timestamptz created_at
    }
    daily_summary_report_rows {
        uuid id PK
        uuid report_id FK
        date day
        int games_played
        int active_players
        int points_spent
        int points_awarded
    }
    game_stats_report_rows {
        uuid id PK
        uuid report_id FK
        uuid game_type_id "lotto.game_types"
        int games_played
        int coupons_sold
        int points_spent
        int points_awarded
    }
    user_activity_report_rows {
        uuid id PK
        uuid report_id FK
        uuid user_id "auth.users"
        int coupons_bought
        int points_spent
        int points_won
        timestamptz last_seen_at
    }
```

### notifications

In-app notifications and per-user settings.

```mermaid
erDiagram
    notification_settings {
        uuid user_id PK "auth.users"
        string email
        bool email_enabled
    }
    notifications {
        uuid id PK
        uuid user_id "auth.users"
        enum type "game_result | prize | upcoming_game"
        string title
        string body
        timestamptz read_at
        timestamptz created_at
    }
```

## Consequences

All members of the team will stick to the schema presented in this document. Changes to the schema
are made through Alembic migrations, and larger changes are recorded in a new ADR.
