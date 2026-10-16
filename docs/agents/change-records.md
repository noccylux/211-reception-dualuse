# Change records

Records in `docs/changes/` are the team's timeline for the weekend. They
feed the Devpost write-up and the "adapting to twists" score, so they keep
decisions and evidence, not narration.

## When to write one

* Record a design decision (problem framing, chosen approach, dropped
  idea), a twist response, a meaningful feature or integration, and test or
  demo outcomes. Pure questions, explanations and status reports need no
  record unless the user asks.
* One record per coherent task. While the task is in progress, update its
  record instead of adding another; start a new record for later work and
  link the earlier one.
* A twist response always gets its own record and a row in
  [../problem/twists.md](../problem/twists.md).
* When a record changes what the build is or how it works, update
  [../architecture.md](../architecture.md) in the same task.

## Naming

`YYYY-MM-DD-NNN-topic.md`, using the current date in Pacific time and the
next unused zero-padded daily sequence starting at `001`. Check existing
files first; a duplicate number is an error.

## Format

Keep Type and Scope; add Related only when useful. Omit empty sections; for
small tasks a few bullets are enough. Report only observed results, and
state what was not verified.

```markdown
# <Change title>

* Type: <design | twist | implementation | demo | ops>
* Scope: <affected modules or paths>
* Related: <earlier records, or omit>

## Context

* <Problem, evidence, constraint or twist that prompted the change.>

## Decision

* <What changed and why; rejected alternatives only where they explain the choice.>

## Verification

* <Checks actually run and their results; what remains unverified.>
```
