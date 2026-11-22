#!/usr/bin/env python3
"""Make a -rpcauth line for corgicoin.conf, so the file holds no password.

    contrib/rpcauth.py <user> [<password>]

With no password a random one is made and printed once. Put the `rpcauth=` line in corgicoin.conf (or give it as -rpcauth=...) and
log in with the user and the password. The line is <user>:<salt>$<hash>, the hash being HMAC-SHA256 of the password with the salt as key.
"""
import hmac
import secrets
import sys


def make(user, password=None):
    if ":" in user or "$" in user or not user:
        raise SystemExit("the user name may not be empty or contain ':' or '$'")
    generated = password is None
    if generated:
        password = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    digest = hmac.new(salt.encode(), password.encode(), "sha256").hexdigest()
    return "%s:%s$%s" % (user, salt, digest), password, generated


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    line, password, generated = make(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
    print("String to be appended to corgicoin.conf:")
    print("rpcauth=" + line)
    if generated:
        print("Your password:")
        print(password)
