# Release Folder Modernization Guide

## ⚠️ Current Status: OUTDATED (2014-era Dependencies)

The `release/` folder contains **Windows distribution assets from 2014** that are incompatible with the modernized codebase.

### What's Wrong

| Component | Current Version | Required Version | Status |
|-----------|----------------|------------------|--------|
| **Qt Libraries** | Qt 4.x DLLs | Qt 5.6+ or Qt 5.15 LTS | ❌ OUTDATED |
| **MinGW Runtime** | GCC 4.x (2013) | GCC 7.3+ or MinGW-w64 8.1+ | ❌ OUTDATED |
| **Boost Libraries** | 1.53 (2013) | 1.55.0 - 1.80+ | ❌ OUTDATED |
| **Math Libraries** | libgmp-10, libmpfr-1 | Current versions | ⚠️ VERIFY |
| **QR Code Library** | libqrencode (unknown) | libqrencode 4.x | ⚠️ VERIFY |

---

## Required Updates

### 1. Qt 5 Libraries (CRITICAL)

The codebase now supports **Qt 5** (v1.4.1.57), but the release folder still has Qt 4 DLLs.

**Remove these Qt 4 DLLs:**
```
QtCore4.dll         (2.89 MB)
QtGui4.dll          (10.15 MB)
QtNetwork4.dll      (1.31 MB)
```

**Replace with Qt 5.15 LTS DLLs:**
```
Qt5Core.dll         (~6 MB)
Qt5Gui.dll          (~6 MB)
Qt5Widgets.dll      (~5 MB) ← NEW in Qt 5
Qt5Network.dll      (~1.5 MB)
```

**Additional Qt 5 platform plugins required:**
```
platforms/qwindows.dll  ← Required for Qt 5 Windows builds
```

**Where to get Qt 5.15 LTS:**
- Official: https://www.qt.io/download-qt-installer
- Open source build: https://download.qt.io/official_releases/qt/5.15/
- MinGW pre-built: https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/qt5_515/

---

### 2. MinGW Runtime Libraries (HIGH PRIORITY)

Current libraries are from **GCC 4.6 era (2013)**. Modern builds require GCC 7.3+.

**Current outdated libraries:**
```
libgcc_s_dw2-1.dll     (118 KB) ← GCC 4.x exception handling
libstdc++-6.dll        (979 KB) ← GCC 4.x C++ runtime
mingwm10.dll           (47 KB)  ← Old MinGW manager
```

**Replace with MinGW-w64 8.1+ (for C++11/14/17 support):**
```
libgcc_s_seh-1.dll     ← SEH exception handling (64-bit)
libstdc++-6.dll        ← Modern C++ runtime with C++11/14/17
libwinpthread-1.dll    ← Modern threading (replaces pthreadGC2.dll)
```

**Where to get MinGW-w64:**
- Official: https://www.mingw-w64.org/downloads/
- Recommended: https://github.com/niXman/mingw-builds-binaries/releases
- With Qt: Bundled in Qt Creator MinGW builds

---

### 3. Threading Library (REQUIRED)

**Current:**
```
pthreadGC2.dll (94 KB) ← PThreads-Win32 (deprecated)
```

**Replace with:**
```
libwinpthread-1.dll    ← MinGW-w64 native Windows threading
```

Modern MinGW-w64 uses native Windows threading via `libwinpthread-1.dll` instead of the deprecated PThreads-Win32.

---

### 4. Boost Libraries (VERIFY)

The `.pro` file references **Boost 1.53 (2013)**, but the codebase supports **Boost 1.55-1.80+** (v1.4.1.55).

**No Boost DLLs currently in release folder** ✓ Good!
- Boost is likely statically linked (correct approach)
- Verify build configuration uses `-DBOOST_THREAD_USE_LIB`

**If adding Boost DLLs, use:**
```
boost_system-*.dll
boost_filesystem-*.dll
boost_program_options-*.dll
boost_thread-*.dll
```

From Boost 1.70+ (supports C++11/14/17).

---

### 5. Math Libraries (LOW PRIORITY)

**Current:**
```
libgmp-10.dll   (343 KB) ← GNU Multiple Precision Arithmetic
libmpfr-1.dll   (271 KB) ← Multiple Precision Floating-Point
```

**Status:** Likely still compatible, but verify:
- libgmp latest: 6.3.0 (https://gmplib.org/)
- libmpfr latest: 4.2.1 (https://www.mpfr.org/)

---

### 6. QR Code Library (VERIFY)

**Current:**
```
libqrencode.dll (52 KB) ← Version unknown
```

**Latest:** libqrencode 4.1.1 (https://fukuchi.org/works/qrencode/)

**Action:** Verify current version and update if < 4.0

---

## Step-by-Step Update Process

### Option 1: Build New Release Package (RECOMMENDED)

1. **Install Qt 5.15 LTS with MinGW-w64:**
   ```bash
   # Download Qt 5.15 LTS installer
   # Select: Qt 5.15.x → MinGW 8.1.0 64-bit
   # Install location: C:\Qt\5.15.x\mingw81_64
   ```

2. **Build CorgiCoin with Qt 5:**
   ```bash
   # Set Qt environment
   set PATH=C:\Qt\5.15.2\mingw81_64\bin;%PATH%
   set PATH=C:\Qt\Tools\mingw810_64\bin;%PATH%

   # Build
   qmake corgicoin-qt.pro
   mingw32-make
   ```

3. **Collect DLLs using windeployqt:**
   ```bash
   # Qt 5 provides windeployqt tool
   cd release
   C:\Qt\5.15.2\mingw81_64\bin\windeployqt.exe corgicoin-qt.exe

   # This automatically copies required Qt 5 DLLs and plugins
   ```

4. **Manually add non-Qt dependencies:**
   ```bash
   # Copy from MinGW bin directory
   copy C:\Qt\Tools\mingw810_64\bin\libgcc_s_seh-1.dll release\
   copy C:\Qt\Tools\mingw810_64\bin\libstdc++-6.dll release\
   copy C:\Qt\Tools\mingw810_64\bin\libwinpthread-1.dll release\

   # Copy from dependency builds
   copy C:\deps\qrencode\bin\libqrencode.dll release\
   ```

### Option 2: Manual DLL Collection

If you can't use `windeployqt`, manually copy:

1. **Qt 5 DLLs** from `C:\Qt\5.15.x\mingw81_64\bin\`:
   - Qt5Core.dll
   - Qt5Gui.dll
   - Qt5Widgets.dll
   - Qt5Network.dll

2. **Qt 5 Platform Plugin** from `C:\Qt\5.15.x\mingw81_64\plugins\platforms\`:
   - Create `platforms\` subdirectory in release folder
   - Copy `qwindows.dll` to `release\platforms\`

3. **MinGW Runtime** from `C:\Qt\Tools\mingw810_64\bin\`:
   - libgcc_s_seh-1.dll (or libgcc_s_dw2-1.dll for 32-bit)
   - libstdc++-6.dll
   - libwinpthread-1.dll

4. **Verify with Dependency Walker:**
   - Download: https://www.dependencywalker.com/
   - Open `corgicoin-qt.exe`
   - Check for missing DLLs

---

## Alternative: Use NSIS Installer Script

The existing `share/setup.nsi` may need updates for Qt 5:

```nsis
; Update Qt section in setup.nsi
Section "Qt Libraries"
  SetOutPath "$INSTDIR"
  File "Qt5Core.dll"
  File "Qt5Gui.dll"
  File "Qt5Widgets.dll"
  File "Qt5Network.dll"

  SetOutPath "$INSTDIR\platforms"
  File "platforms\qwindows.dll"
SectionEnd
```

---

## Testing Checklist

After updating release folder:

- [ ] **Basic launch**: `corgicoin-qt.exe` starts without DLL errors
- [ ] **GUI renders**: Qt 5 widgets display correctly
- [ ] **Networking**: Connects to peers (Qt5Network.dll)
- [ ] **QR codes**: Generate/scan QR codes (libqrencode.dll)
- [ ] **Threading**: Multiple operations work concurrently (libwinpthread-1.dll)
- [ ] **Wallet operations**: Encrypt, backup, restore work properly
- [ ] **Clean install**: Test on fresh Windows VM without Qt installed
- [ ] **Dependency check**: Run Dependency Walker to verify no missing DLLs

---

## Size Comparison

**Current (Qt 4):** ~15.9 MB total
```
QtCore4.dll          2.89 MB
QtGui4.dll          10.15 MB
QtNetwork4.dll       1.31 MB
Other DLLs           1.55 MB
```

**Expected (Qt 5):** ~20-25 MB total
```
Qt5Core.dll          ~6 MB
Qt5Gui.dll           ~6 MB
Qt5Widgets.dll       ~5 MB
Qt5Network.dll       ~1.5 MB
platforms/qwindows.dll ~1.5 MB
Other DLLs           ~2 MB
```

Qt 5 is larger but provides better performance, security, and HiDPI support.

---

## Security Implications

**Why this matters:**

1. **Qt 4 End-of-Life:** Qt 4 reached EOL in 2015 - no security updates for 9+ years
2. **MinGW GCC 4.x:** Lacks modern security features:
   - No Control Flow Guard (CFG)
   - No Address Space Layout Randomization (ASLR) improvements
   - No Stack Smashing Protector (SSP) improvements
3. **Threading vulnerabilities:** PThreads-Win32 has known race conditions

**Modern alternatives provide:**
- Regular security patches (Qt 5.15 LTS supported until 2025)
- Modern compiler protections (GCC 8.1+ with -fstack-protector-strong)
- Better memory safety (libstdc++ with C++11 move semantics)

---

## Recommended Action Plan

### Phase 1: Documentation (DONE)
- [x] Create this modernization guide
- [x] Update release/README.txt with deprecation notice

### Phase 2: Build Qt 5 Release
1. Set up Qt 5.15 LTS build environment
2. Build CorgiCoin with Qt 5
3. Collect dependencies using windeployqt
4. Test on clean Windows installation

### Phase 3: Update Repository
1. Create `release-qt5/` folder with modern DLLs
2. Move old Qt 4 DLLs to `release-qt4-deprecated/`
3. Update NSIS installer for Qt 5
4. Update build documentation

### Phase 4: Validation
1. Test on Windows 7/8/10/11
2. Verify all wallet operations
3. Check memory usage and performance
4. Create release checksums

---

## References

- Qt 5.15 LTS: https://doc.qt.io/qt-5.15/
- MinGW-w64: https://www.mingw-w64.org/
- Boost 1.70+: https://www.boost.org/
- Dependency Walker: https://www.dependencywalker.com/
- NSIS Installer: https://nsis.sourceforge.io/

---

## Questions?

This is a 2014 codebase with 2024 modernizations. The code is Qt 5 ready, but the distribution assets haven't been updated yet.

**Before building a production release:**
1. Follow the update process above
2. Test thoroughly on multiple Windows versions
3. Verify all dependencies with Dependency Walker
4. Create reproducible build instructions

See [MODERNIZATION.md](MODERNIZATION.md) for overall modernization status.
