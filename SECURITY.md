# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 4.8.x   | :white_check_mark: |
| 4.7.x   | :white_check_mark: |
| 4.2.x – 4.6.x | :x:           |
| < 4.2   | :x:                |

Only the two most recent releases receive security fixes. There is no
long-term support branch.

## Reporting a Vulnerability

**Please do not open a public issue or pull request for a security
vulnerability.** Discussing an exploitable bug in the open before a fix
is released can put funds and running nodes at risk.

Report privately instead, using one of:

1. **GitHub Security Advisories (preferred):** use the "Report a
   vulnerability" button under this repo's Security tab. This opens a
   private advisory visible only to maintainers, where you can discuss
   the issue and a fix before anything goes public.
2. **Email:** `<maintainer email>` (fill in — or drop this line and rely
   on GitHub Advisories alone).

Please include a description of the impact (crash, fund loss, consensus
split, etc.), reproduction steps or a minimal test case, and a suggested
fix if you have one.

You can expect an acknowledgement within a few days. If the report is
accepted, we'll agree on a disclosure timeline with you before any public
advisory or fix lands; if declined, we'll explain why.

## Scope

Covers the `corgicoind` daemon, wallet, RPC/P2P interfaces, and build
scripts in this repository. Third-party pool software, exchanges, and
unrelated forks are out of scope.
