# OpenSSL 3.x Migration Plan

## Overview

This document outlines the migration strategy from OpenSSL 1.0.x to OpenSSL 3.x for the CorgiCoin codebase. This is a **CRITICAL security update** as OpenSSL 1.0.x reached end-of-life in December 2016 and contains numerous known vulnerabilities including Heartbleed (CVE-2014-0160).

## Current State Analysis

### OpenSSL Usage in Codebase

**Files using OpenSSL:**
- `src/util.cpp` - Random number generation, threading/locking
- `src/crypter.cpp` - AES encryption/decryption (wallet encryption)
- `src/key.cpp` - ECDSA signatures, EC key operations
- `src/net.h` - Random number generation
- `src/addrman.h` - Random number generation
- `src/util.h` - SHA256, RIPEMD160 hashing
- `src/bignum.h` - Big number operations
- `src/scrypt.c` - Scrypt key derivation (SHA256)
- `src/qt/rpcconsole.cpp` - OpenSSL version display

### Deprecated APIs Identified

#### 1. **Threading/Locking (util.cpp:82-119)** - REMOVED in OpenSSL 3.0
**Status**: CRITICAL - Code will not compile with OpenSSL 3.0

```cpp
// DEPRECATED - These functions were removed in OpenSSL 3.0:
CRYPTO_num_locks()           // Line 99, 100
CRYPTO_set_locking_callback() // Line 102, 115
```

**Migration**: OpenSSL 1.1.0+ handles threading automatically. These functions and the locking callback must be removed entirely when targeting OpenSSL 1.1.0+.

#### 2. **EVP Cipher Context (crypter.cpp:74-82, 101-109)** - Deprecated in 1.1.0
**Status**: HIGH PRIORITY - Stack allocation deprecated

```cpp
// DEPRECATED in OpenSSL 1.1.0:
EVP_CIPHER_CTX ctx;              // Stack allocation (lines 74, 101)
EVP_CIPHER_CTX_init(&ctx);       // Lines 78, 105
EVP_CIPHER_CTX_cleanup(&ctx);    // Lines 82, 109
```

**Migration**: Use heap allocation with modern API:
```cpp
// MODERN API:
EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
// ... use ctx ...
EVP_CIPHER_CTX_free(ctx);
```

#### 3. **EVP_BytesToKey (crypter.cpp:31)** - Deprecated in 3.0
**Status**: MEDIUM PRIORITY - Still works but deprecated

```cpp
// DEPRECATED in OpenSSL 3.0:
EVP_BytesToKey(EVP_aes_256_cbc(), EVP_sha512(), ...)
```

**Migration**: Use EVP_KDF API (PBKDF2):
```cpp
// MODERN API (OpenSSL 3.0+):
EVP_KDF *kdf = EVP_KDF_fetch(NULL, "PBKDF2", NULL);
EVP_KDF_CTX *kctx = EVP_KDF_CTX_new(kdf);
// ... set parameters ...
EVP_KDF_derive(kctx, out, outlen, params);
```

**Note**: For compatibility with OpenSSL 1.1.x, can use PKCS5_PBKDF2_HMAC_SHA1() as intermediate step.

#### 4. **ECDSA_SIG Member Access (key.cpp:84, 105, 107)** - Deprecated in 1.1.0
**Status**: HIGH PRIORITY - Direct struct access deprecated

```cpp
// DEPRECATED - Direct member access:
ecsig->r  // Lines 84, 105
ecsig->s  // Line 107
```

**Migration**: Use getter/setter functions:
```cpp
// MODERN API:
const BIGNUM *r, *s;
ECDSA_SIG_get0(ecsig, &r, &s);

// For setting (if needed):
BIGNUM *r_new = BN_new();
BIGNUM *s_new = BN_new();
ECDSA_SIG_set0(ecsig, r_new, s_new);
```

#### 5. **EC_KEY Opaque Structure** - Partially deprecated in 1.1.0
**Status**: MEDIUM PRIORITY - Many helper functions available

The `EC_KEY` structure became opaque in OpenSSL 1.1.0. Most operations use accessor functions which are already being used correctly in the codebase.

## Migration Strategy

### Phase 1: Support OpenSSL 1.1.x (Backward Compatible) ✅ IN PROGRESS

**Goal**: Make code compile and run with OpenSSL 1.1.x while maintaining backward compatibility with 1.0.x

**Tasks**:
1. ✅ Create version detection macros (already done in compat_openssl.h)
2. Remove/conditionally compile threading code for OpenSSL 1.1.0+
3. Modernize EVP_CIPHER_CTX usage with version checks
4. Fix ECDSA_SIG member access with version checks
5. Test with both OpenSSL 1.0.x and 1.1.x

**Timeline**: 2-3 days

### Phase 2: Target OpenSSL 3.0+ (Preferred)

**Goal**: Fully migrate to OpenSSL 3.0 APIs, drop OpenSSL 1.0.x support

**Tasks**:
1. Replace EVP_BytesToKey with EVP_KDF API
2. Update all remaining deprecated function calls
3. Run OpenSSL 3.0 deprecation warnings
4. Comprehensive testing

**Timeline**: 3-4 days

### Phase 3: Testing & Validation

**Critical Tests Required**:
1. **Wallet Encryption/Decryption**: Verify existing encrypted wallets can be decrypted
2. **Key Generation**: Test private/public key pair generation
3. **Signature Verification**: Verify ECDSA signatures validate correctly
4. **Hash Functions**: Validate SHA256 and RIPEMD160 outputs
5. **Random Number Generation**: Test RAND_bytes for sufficient entropy
6. **Scrypt Hashing**: Verify scrypt still produces correct outputs

**Test Methodology**:
- Unit tests with known inputs/outputs
- Integration tests with existing wallets (BACKUP FIRST!)
- Regression tests comparing old vs new OpenSSL outputs

**Timeline**: 2-3 days

## Implementation Plan

### Step 1: Threading/Locking Removal (util.cpp)

**Change**:
```cpp
#if OPENSSL_VERSION_NUMBER < 0x10100000L
    // OpenSSL 1.0.x requires manual thread setup
    static std::vector<std::unique_ptr<CCriticalSection>> vpmutexOpenSSL;
    void locking_callback(int mode, int i, const char* file, int line) { ... }

    // In CInit constructor:
    vpmutexOpenSSL.resize(CRYPTO_num_locks());
    for (int i = 0; i < CRYPTO_num_locks(); i++)
        vpmutexOpenSSL[i] = std::make_unique<CCriticalSection>();
    CRYPTO_set_locking_callback(locking_callback);

    // In CInit destructor:
    CRYPTO_set_locking_callback(nullptr);
    vpmutexOpenSSL.clear();
#else
    // OpenSSL 1.1.0+ handles threading automatically - no action needed
#endif
```

**Testing**: Verify multi-threaded operations (RPC calls, network operations) work correctly.

### Step 2: EVP_CIPHER_CTX Modernization (crypter.cpp)

**Change in CCrypter::Encrypt() and Decrypt()**:
```cpp
bool CCrypter::Encrypt(const CKeyingMaterial& vchPlaintext, std::vector<unsigned char> &vchCiphertext)
{
    if (!fKeySet)
        return false;

    int nLen = vchPlaintext.size();
    int nCLen = nLen + AES_BLOCK_SIZE, nFLen = 0;
    vchCiphertext = std::vector<unsigned char>(nCLen);

#if OPENSSL_VERSION_NUMBER >= 0x10100000L
    // OpenSSL 1.1.0+: Use heap-allocated context
    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return false;

    bool fOk = true;
    if (fOk) fOk = EVP_EncryptInit_ex(ctx, EVP_aes_256_cbc(), nullptr, chKey, chIV);
    if (fOk) fOk = EVP_EncryptUpdate(ctx, &vchCiphertext[0], &nCLen, &vchPlaintext[0], nLen);
    if (fOk) fOk = EVP_EncryptFinal_ex(ctx, (&vchCiphertext[0])+nCLen, &nFLen);

    EVP_CIPHER_CTX_free(ctx);
#else
    // OpenSSL 1.0.x: Use stack-allocated context
    EVP_CIPHER_CTX ctx;
    bool fOk = true;

    EVP_CIPHER_CTX_init(&ctx);
    if (fOk) fOk = EVP_EncryptInit_ex(&ctx, EVP_aes_256_cbc(), nullptr, chKey, chIV);
    if (fOk) fOk = EVP_EncryptUpdate(&ctx, &vchCiphertext[0], &nCLen, &vchPlaintext[0], nLen);
    if (fOk) fOk = EVP_EncryptFinal_ex(&ctx, (&vchCiphertext[0])+nCLen, &nFLen);
    EVP_CIPHER_CTX_cleanup(&ctx);
#endif

    if (!fOk) return false;

    vchCiphertext.resize(nCLen + nFLen);
    return true;
}
```

**Testing**: Encrypt/decrypt test vectors, verify existing encrypted wallets can be decrypted.

### Step 3: ECDSA_SIG Member Access (key.cpp)

**Change in ECDSA_SIG_recover_key_GFp()**:
```cpp
#if OPENSSL_VERSION_NUMBER >= 0x10100000L
    // OpenSSL 1.1.0+: Use getter functions
    const BIGNUM *sig_r, *sig_s;
    ECDSA_SIG_get0(ecsig, &sig_r, &sig_s);

    if (!BN_add(x, x, sig_r)) { ret=-1; goto err; }
    // ... use sig_r and sig_s ...
    if (!BN_mod_inverse(rr, sig_r, order, ctx)) { ret=-1; goto err; }
    if (!BN_mod_mul(sor, sig_s, rr, order, ctx)) { ret=-1; goto err; }
#else
    // OpenSSL 1.0.x: Direct member access
    if (!BN_add(x, x, ecsig->r)) { ret=-1; goto err; }
    if (!BN_mod_inverse(rr, ecsig->r, order, ctx)) { ret=-1; goto err; }
    if (!BN_mod_mul(sor, ecsig->s, rr, order, ctx)) { ret=-1; goto err; }
#endif
```

**Testing**: Signature generation and verification, key recovery functionality.

### Step 4: EVP_BytesToKey Replacement (Optional for Phase 2)

**Current** (crypter.cpp:31):
```cpp
i = EVP_BytesToKey(EVP_aes_256_cbc(), EVP_sha512(), &chSalt[0],
                  (unsigned char *)&strKeyData[0], strKeyData.size(),
                  nRounds, chKey, chIV);
```

**Replacement** (OpenSSL 3.0+):
```cpp
// Note: This is a breaking change - wallet format compatibility must be preserved!
// Consider keeping EVP_BytesToKey for existing wallets and only using new API for new wallets

// For backward compatibility, can use PKCS5_PBKDF2_HMAC which is available in 1.1.x and 3.x
#if OPENSSL_VERSION_NUMBER >= 0x10000000L
    // Use PBKDF2 (available in OpenSSL 1.0.0+)
    if (PKCS5_PBKDF2_HMAC((const char*)&strKeyData[0], strKeyData.size(),
                          &chSalt[0], chSalt.size(),
                          nRounds, EVP_sha512(),
                          WALLET_CRYPTO_KEY_SIZE, chKey) != 1)
        return false;

    // For IV, can use similar derivation or keep EVP_BytesToKey for IV only
    // WARNING: This changes the key derivation! Must migrate existing wallets carefully
#else
    i = EVP_BytesToKey(EVP_aes_256_cbc(), EVP_sha512(), &chSalt[0],
                      (unsigned char *)&strKeyData[0], strKeyData.size(),
                      nRounds, chKey, chIV);
#endif
```

**CRITICAL WARNING**: Changing key derivation breaks compatibility with existing encrypted wallets! This requires a wallet migration tool or maintaining dual paths.

## Compatibility Matrix

| OpenSSL Version | Support Status | Notes |
|----------------|----------------|-------|
| 1.0.x | ⚠️ Legacy (EOL 2016) | Currently supported, CRITICAL vulnerabilities |
| 1.1.0 | ✅ Target (Phase 1) | EOL September 2023 |
| 1.1.1 | ✅ Recommended | LTS, EOL September 2023 |
| 3.0.x | ✅ Target (Phase 2) | Current LTS, supported until 2026 |
| 3.1+ | ✅ Future | Latest stable |

## Testing Checklist

- [ ] Compile with OpenSSL 1.0.x (verify backward compatibility)
- [ ] Compile with OpenSSL 1.1.1 (verify Phase 1 changes)
- [ ] Compile with OpenSSL 3.0+ (verify Phase 2 changes)
- [ ] **Wallet Tests**:
  - [ ] Create new encrypted wallet
  - [ ] Decrypt existing wallet from OpenSSL 1.0.x build
  - [ ] Encrypt/decrypt operations match across versions
  - [ ] Wallet passphrase operations work correctly
- [ ] **Crypto Tests**:
  - [ ] Generate new key pairs
  - [ ] Sign transactions
  - [ ] Verify signatures
  - [ ] Hash operations (SHA256, RIPEMD160) produce identical outputs
- [ ] **Network Tests**:
  - [ ] Random number generation (RAND_bytes)
  - [ ] Multi-threaded operation stability
- [ ] **Scrypt Tests**:
  - [ ] Scrypt hashing produces correct outputs

## Risks & Mitigation

### Risk 1: Wallet Incompatibility
**Risk**: Changes to key derivation could make existing wallets unusable
**Mitigation**:
- Do NOT change EVP_BytesToKey in Phase 1
- If changing in Phase 2, provide migration tool
- Test with real wallet files (backed up!)

### Risk 2: Signature Incompatibility
**Risk**: Changes to ECDSA operations could invalidate existing signatures
**Mitigation**:
- Use exact same algorithms, only change API calls
- Extensive testing with known test vectors
- Verify signatures from old build validate in new build

### Risk 3: Random Number Quality
**Risk**: Changes to RNG could weaken security
**Mitigation**:
- OpenSSL's RAND_bytes is consistent across versions
- No changes to RNG usage
- Verify entropy sources still work

## Build System Updates

**CMakeLists.txt** changes:
```cmake
# Find OpenSSL
find_package(OpenSSL REQUIRED)

# Check OpenSSL version
if(OPENSSL_VERSION VERSION_LESS "1.1.0")
    message(WARNING "OpenSSL ${OPENSSL_VERSION} is end-of-life and contains CRITICAL vulnerabilities")
    message(WARNING "Including Heartbleed (CVE-2014-0160). Upgrade to OpenSSL 3.0+ immediately!")
endif()

if(OPENSSL_VERSION VERSION_GREATER_EQUAL "3.0.0")
    message(STATUS "OpenSSL 3.x detected - using modern API")
    add_compile_definitions(OPENSSL_3_0_OR_LATER)
endif()

target_link_libraries(corgicoin OpenSSL::SSL OpenSSL::Crypto)
```

**Makefile** changes:
Add version detection and warnings during build.

## References

- [OpenSSL 1.1.0 Changes](https://www.openssl.org/docs/man1.1.0/man7/migration_guide.html)
- [OpenSSL 3.0 Migration Guide](https://www.openssl.org/docs/man3.0/man7/migration_guide.html)
- [EVP API Changes](https://wiki.openssl.org/index.php/EVP)
- [ECDSA Changes in 1.1.0](https://wiki.openssl.org/index.php/OpenSSL_1.1.0_Changes)

## Timeline Summary

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1: OpenSSL 1.1.x Support | 2-3 days | Code compiles with 1.1.x, maintains 1.0.x compat |
| Phase 2: OpenSSL 3.x Migration | 3-4 days | Full 3.x API usage, deprecation warnings clean |
| Phase 3: Testing | 2-3 days | All tests passing, wallet compatibility verified |
| **Total** | **7-10 days** | Production-ready OpenSSL 3.x support |

## Current Status

- [x] Analysis complete - deprecated APIs identified
- [ ] Phase 1 implementation (OpenSSL 1.1.x support)
- [ ] Phase 2 implementation (OpenSSL 3.x migration)
- [ ] Testing & validation
- [ ] Documentation updates

---

Last Updated: 2025-11-19
Status: Planning Complete - Ready for Implementation
