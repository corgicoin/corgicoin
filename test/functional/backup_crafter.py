"""Craft encrypted wallet backups (CORGIBK1) the way src/walletdump.cpp reads them, for tests that need a file the node would not write itself.

  "CORGIBK1" | log2(N) (1 byte) | salt (16) | nonce (12) | AES-256-GCM ciphertext | tag (16)

The key is scrypt(passphrase, salt, N, r = 8, p = 1); the header is the additional data. scrypt is hashlib's; AES-GCM is OpenSSL's, through ctypes
(the Python in the test environment has no AES-GCM of its own). A test that needs it calls require_crypto(test) first, which skips it where
libcrypto cannot be found.
"""
import ctypes
import ctypes.util
import hashlib
import json
import os
import sys

MAGIC = b"CORGIBK1"
TAG_LEN = 16
_lib = None


def _load():
    global _lib
    if _lib is not None:
        return _lib
    # Only versioned libraries. On macOS an unversioned libcrypto.dylib (what find_library("crypto") returns there: /usr/lib's) is
    # refused by the system with abort(), which kills the interpreter outright rather than raising OSError, so it is never tried.
    # On macOS a Homebrew or MacPorts OpenSSL 3 is looked for by path.
    candidates = ["libcrypto.so.3", "libcrypto.so.1.1"]
    if sys.platform == "darwin":
        candidates += ["/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib", "/usr/local/opt/openssl@3/lib/libcrypto.3.dylib",
                       "/opt/local/lib/libcrypto.3.dylib"]
    else:
        found = ctypes.util.find_library("crypto")
        if found:
            candidates.insert(0, found)
    for name in candidates:
        if sys.platform == "darwin" and not os.path.exists(name):
            continue
        try:
            lib = ctypes.CDLL(name)
            lib.EVP_aes_256_gcm  # noqa: B018 (the symbol must be there)
        except (OSError, AttributeError):
            continue
        vp, ci = ctypes.c_void_p, ctypes.c_int
        lib.EVP_CIPHER_CTX_new.restype = vp
        lib.EVP_CIPHER_CTX_free.argtypes = [vp]
        lib.EVP_aes_256_gcm.restype = vp
        lib.EVP_EncryptInit_ex.argtypes = [vp, vp, vp, ctypes.c_char_p, ctypes.c_char_p]
        lib.EVP_CIPHER_CTX_ctrl.argtypes = [vp, ci, ci, vp]
        lib.EVP_EncryptUpdate.argtypes = [vp, vp, ctypes.POINTER(ci), ctypes.c_char_p, ci]
        lib.EVP_EncryptFinal_ex.argtypes = [vp, vp, ctypes.POINTER(ci)]
        _lib = lib
        return lib
    return None


def require_crypto(test):
    """Skip the test where AES-GCM cannot be had."""
    if _load() is None:
        test.skip_test("no libcrypto with AES-GCM for ctypes")


def _aes_gcm_encrypt(key, nonce, aad, plain):
    lib = _load()
    ctx = lib.EVP_CIPHER_CTX_new()
    try:
        n = ctypes.c_int(0)
        assert lib.EVP_EncryptInit_ex(ctx, lib.EVP_aes_256_gcm(), None, None, None) == 1
        assert lib.EVP_CIPHER_CTX_ctrl(ctx, 0x9, len(nonce), None) == 1         # EVP_CTRL_GCM_SET_IVLEN
        assert lib.EVP_EncryptInit_ex(ctx, None, None, key, nonce) == 1
        assert lib.EVP_EncryptUpdate(ctx, None, ctypes.byref(n), aad, len(aad)) == 1
        out = ctypes.create_string_buffer(len(plain) + 32)
        assert lib.EVP_EncryptUpdate(ctx, out, ctypes.byref(n), plain, len(plain)) == 1
        total = n.value
        tail = ctypes.create_string_buffer(32)
        assert lib.EVP_EncryptFinal_ex(ctx, tail, ctypes.byref(n)) == 1
        ct = out.raw[:total] + tail.raw[:n.value]
        tag = ctypes.create_string_buffer(TAG_LEN)
        assert lib.EVP_CIPHER_CTX_ctrl(ctx, 0x10, TAG_LEN, tag) == 1            # EVP_CTRL_GCM_GET_TAG
        return ct + tag.raw
    finally:
        lib.EVP_CIPHER_CTX_free(ctx)


def craft(passphrase, plain, log2n=14, salt=b"\x01" * 16, nonce=b"\x02" * 12):
    """The bytes of a backup file holding `plain` (bytes, or a dict that is written as JSON)."""
    if isinstance(plain, (dict, list)):
        plain = json.dumps(plain).encode()
    header = MAGIC + bytes([log2n]) + salt + nonce
    n = 1 << log2n
    key = hashlib.scrypt(passphrase.encode(), salt=salt, n=n, r=8, p=1, maxmem=128 * n * 8 + (16 << 20), dklen=32)
    return header + _aes_gcm_encrypt(key, nonce, header, plain)


def payload(chain="regtest", **fields):
    """A backup's JSON as the node writes it (version 1), with any field replaced or added."""
    root = {"version": 1, "created": 1700000000, "chain": chain, "hdmnemonic": "", "hdindex": 0,
            "keys": [], "labels": [], "watchonly": [], "cscript": []}
    root.update(fields)
    return root


_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58check_encode(payload_bytes):
    data = payload_bytes + hashlib.sha256(hashlib.sha256(payload_bytes).digest()).digest()[:4]
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\x00"))) + out


def b58check_decode(text):
    n = 0
    for c in text:
        n = n * 58 + _B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    raw = b"\x00" * (len(text) - len(text.lstrip("1"))) + raw
    return raw[:-4]


def wif(secret32, prefix_byte, compressed=True):
    """A private key in wallet import format, with the network's prefix byte."""
    return b58check_encode(bytes([prefix_byte]) + secret32 + (b"\x01" if compressed else b""))


def decrypt(passphrase, data):
    """The plain text of a backup file (bytes), or an AssertionError if it does not decrypt (wrong passphrase, a changed byte)."""
    lib = _load()
    assert data[:8] == MAGIC, "not a backup"
    log2n = data[8]
    salt, nonce = data[9:25], data[25:37]
    header, ct, tag = data[:37], data[37:-TAG_LEN], data[-TAG_LEN:]
    n = 1 << log2n
    key = hashlib.scrypt(passphrase.encode(), salt=salt, n=n, r=8, p=1, maxmem=128 * n * 8 + (16 << 20), dklen=32)
    lib.EVP_DecryptInit_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.EVP_DecryptUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int]
    lib.EVP_DecryptFinal_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    ctx = lib.EVP_CIPHER_CTX_new()
    try:
        n_out = ctypes.c_int(0)
        assert lib.EVP_DecryptInit_ex(ctx, lib.EVP_aes_256_gcm(), None, None, None) == 1
        assert lib.EVP_CIPHER_CTX_ctrl(ctx, 0x9, len(nonce), None) == 1
        assert lib.EVP_DecryptInit_ex(ctx, None, None, key, nonce) == 1
        assert lib.EVP_DecryptUpdate(ctx, None, ctypes.byref(n_out), header, len(header)) == 1
        out = ctypes.create_string_buffer(len(ct) + 32)
        assert lib.EVP_DecryptUpdate(ctx, out, ctypes.byref(n_out), ct, len(ct)) == 1
        total = n_out.value
        tag_buf = ctypes.create_string_buffer(tag, TAG_LEN)
        assert lib.EVP_CIPHER_CTX_ctrl(ctx, 0x11, TAG_LEN, tag_buf) == 1            # EVP_CTRL_GCM_SET_TAG
        tail = ctypes.create_string_buffer(32)
        assert lib.EVP_DecryptFinal_ex(ctx, tail, ctypes.byref(n_out)) == 1, "the tag does not match"
        return out.raw[:total] + tail.raw[:n_out.value]
    finally:
        lib.EVP_CIPHER_CTX_free(ctx)
