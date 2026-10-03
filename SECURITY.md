# Security policy

Quorlo connects to production data platforms, so we take security reports seriously.

## Reporting a vulnerability

**Please don't report security issues in public issues, discussions or pull requests.**

Report them privately through GitHub's private vulnerability reporting:
[Report a vulnerability](https://github.com/Quorlo/quorlo/security/advisories/new).

Please include:

- what the issue is and what an attacker could do with it;
- the steps to reproduce it, or a proof of concept;
- the Quorlo version or commit, and the connector involved, if any.

We'll acknowledge your report within a few days, keep you updated as we investigate,
and credit you in the advisory unless you'd rather stay anonymous.

## Supported versions

Quorlo is pre-alpha and has no releases yet. Fixes land on `main`.

## What is in scope

Anything that breaks the promises in the [principles](https://quorlo.github.io/quorlo/concepts/principles/), for example:

- a scan that reads table data, or writes anything, when it should only read metadata;
- credentials or connection strings leaking into output, logs, errors or the run history;
- a way to run unintended SQL through a connector.
