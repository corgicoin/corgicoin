# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 4.8.x   | :white_check_mark: |
| < 4.8   | :x:                |

Only the latest release receives security fixes; there is no long-term support branch. Upgrade to it. In particular,
v4.5–v4.7 have a wallet bug that leaves HD-wallet coins unspendable and, in encrypted HD wallets, private keys
unencrypted on disk (fixed in v4.8.0.0).

## Reporting a Vulnerability

**Please do not open a public issue or pull request for a security
vulnerability.** Discussing an exploitable bug in the open before a fix
is released can put funds and running nodes at risk.

Report privately instead, through **GitHub Security Advisories**: use the
"Report a vulnerability" button under this repo's Security tab. This opens a
private advisory visible only to maintainers, where you can discuss the issue
and a fix before anything goes public.

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
