# Running corgicoind as a service

Three ready-made files live under `contrib/`. **They have been written and read through, but not run**: a systemd, Docker or
logrotate was not available where they were made. Try each on a spare machine before you rely on it, and send fixes.

| File | For |
|---|---|
| `contrib/systemd/corgicoind.service` | systemd on Linux. Steps to make the user and directories are in the file's header. |
| `contrib/docker/Dockerfile` | a container (two stages: build, then a small runtime image). |
| `contrib/logrotate/corgicoin` | rotating `debug.log` when the node logs to a file rather than the journal. |

## Stopping takes time

On SIGTERM the node closes its databases cleanly, and that can take several minutes after a long run or a big reorganisation. If it
is killed before it finishes, the databases may have to be recovered on the next start. So:

- systemd: `TimeoutStopSec=600` is set in the unit (the default is 90 seconds).
- Docker: run with `--stop-timeout 600` (the default is 10 seconds).
- Do not `kill -9` a node unless it is truly stuck.

## Logs

- Under systemd or Docker the node runs with `-printtoconsole` and logs go to the journal or `docker logs`, which rotate themselves.
- For a node that logs to `debug.log`, use the logrotate file: the node reopens its log when it gets SIGHUP.
- `-logformat=json` writes one JSON object per line (`time`, `msg`) for log collectors; peers' public IPv4 addresses are replaced
  by `[ip]` unless `-logips` is given. This only masks IPv4 addresses that appear as text in the log; do not rely on it as a
  privacy guarantee.

## Credentials

Do not put `rpcpassword` on a command line (it shows in `ps` and in the unit file). Use `rpcauth` lines in the config file
(`contrib/rpcauth.py` makes one) or the cookie file in the data directory.

## Health

`corgicoind getblockcount` (uses the cookie) answers once the RPC server is up. `corgicoind getmetrics` gives Prometheus text.
The Dockerfile's `HEALTHCHECK` uses `getblockcount` and allows five minutes for start-up.
