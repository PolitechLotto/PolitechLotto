# 001: Way of working

## Status

Proposed, 13.10.2026

## Context

A concrete set of rules is needed for an agile team to work. We need to find common ground and agree
on a way of working which will be acceptable to us.

## Decision

**Work methodology**: We will be following [scrum framework](https://www.scrum.org/resources/what-scrum-module).

**Communication**: We chose Discord as our main channel of communication.

**Task and issue tracking**: We chose [Linear](https://linear.app/politechlotto) as our task tracking application.

**Formalization of decisions**: Major decisions which will impact architecture or work methodology, should be saved in ADRs like this one.

### Technical practices

**Version management**: We chose to use `git` as our version management software and [GitHub](https://github.com/PolitechLotto) as a code management platform.

**Commiting changes**: We chose to follow [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) convention, with a change of **always** including Linear issue number in the commit title.

**PRs**: We chose to:

- Always create a per-issue branch, and to **never** commit straight to `main`;
- Never merge our own PR;
- Never merge an unreviewed PR;

**Tools**: We chose to not force any specific coding tool as of now.

## Consequences

All members of the team will stick to decisions made in this document.

