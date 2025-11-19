# Qt 5 Migration Guide

## Overview
This document outlines the migration from Qt 4 to Qt 5 for the CorgiCoin Qt GUI. Qt 4 reached end-of-life in 2015, and Qt 5 provides better performance, modern features, and continued security support.

## Qt Version Compatibility
- **Current**: Qt 4.x (EOL December 2015)
- **Target**: Qt 5.6+ LTS or Qt 5.15 LTS
- **Future**: Qt 6.x ready

## Major Changes from Qt 4 to Qt 5

### 1. Module Reorganization (Most Critical)
Qt 5 split QtGui into multiple modules:
- **QtWidgets**: All widget classes (QWidget, QDialog, QMainWindow, QPushButton, etc.)
- **QtGui**: Low-level GUI classes (QImage, QFont, QColor, etc.)
- **QtPrintSupport**: Printing classes

**Required .pro file changes:**
```qmake
# Qt 4:
QT += core gui

# Qt 5:
greaterThan(QT_MAJOR_VERSION, 4): QT += widgets
```

### 2. Deprecated API Replacements

#### Qt::escape() → QString::toHtmlEscaped()
- **Files affected**: guiutil.cpp, sendcoinsdialog.cpp
- **Qt 4**: `Qt::escape(str)`
- **Qt 5**: `str.toHtmlEscaped()`

#### QString::toAscii() → QString::toLatin1()
- **Files affected**: miningpage.cpp (4 instances)
- **Qt 4**: `str.toAscii()`
- **Qt 5**: `str.toLatin1()` or `str.toUtf8()`

### 3. Header Changes
Some headers moved locations:
- **QtGui/QMenu** → **QMenu** (in QtWidgets)
- **QtGui/QWidget** → **QWidget** (in QtWidgets)

## Migration Plan

### Phase 1: Build System Updates ✅
1. Update .pro file to support Qt 5
2. Add QtWidgets module for Qt 5
3. Maintain backward compatibility with Qt 4

### Phase 2: API Replacements
1. Replace Qt::escape() with QString::toHtmlEscaped()
2. Replace toAscii() with toLatin1()
3. Update deprecated Qt::WA_* constants if any

### Phase 3: Testing
1. Build with Qt 4 (verify backward compatibility)
2. Build with Qt 5.6+ (verify forward compatibility)
3. Test all GUI functionality
4. Test platform-specific features (Mac, Windows, Linux)

## API Changes Detected

### guiutil.cpp:145
```cpp
// Qt 4:
QString escaped = Qt::escape(str);

// Qt 5:
QString escaped = str.toHtmlEscaped();
```

### sendcoinsdialog.cpp:95
```cpp
// Qt 4:
formatted.append(tr("<b>%1</b> to %2 (%3)")
    .arg(BitcoinUnits::formatWithUnit(BitcoinUnits::BTC, rcp.amount),
         Qt::escape(rcp.label), rcp.address));

// Qt 5:
formatted.append(tr("<b>%1</b> to %2 (%3)")
    .arg(BitcoinUnits::formatWithUnit(BitcoinUnits::BTC, rcp.amount),
         rcp.label.toHtmlEscaped(), rcp.address));
```

### miningpage.cpp:89-92
```cpp
// Qt 4:
args << "--scantime" << ui->scantimeBox->text().toAscii();
args << "--url" << urlLine.toAscii();
args << "--userpass" << userpassLine.toAscii();
args << "--threads" << ui->threadsBox->text().toAscii();

// Qt 5:
args << "--scantime" << ui->scantimeBox->text().toLatin1();
args << "--url" << urlLine.toLatin1();
args << "--userpass" << userpassLine.toLatin1();
args << "--threads" << ui->threadsBox->text().toLatin1();
```

## Build Configuration Changes

### corgicoin-qt.pro
Add Qt 5 widgets module:
```qmake
# Add after QT += section
greaterThan(QT_MAJOR_VERSION, 4): QT += widgets
```

## Compatibility Strategy

This migration maintains **backward compatibility** with Qt 4 while adding Qt 5 support:
- Code compiles with both Qt 4 and Qt 5
- Conditional compilation where needed
- Graceful transition path

## Testing Checklist

- [ ] Build with Qt 4.8 (verify backward compatibility)
- [ ] Build with Qt 5.6 LTS (minimum Qt 5 version)
- [ ] Build with Qt 5.15 LTS (latest Qt 5)
- [ ] Test GUI rendering and layouts
- [ ] Test wallet operations (send, receive)
- [ ] Test address book
- [ ] Test settings dialog
- [ ] Test mining page
- [ ] Test console
- [ ] Test system tray icon
- [ ] Test notifications
- [ ] Platform-specific testing:
  - [ ] Linux (Ubuntu, Fedora)
  - [ ] Windows (7, 10, 11)
  - [ ] macOS (10.13+)

## Benefits of Qt 5

- **Better performance**: Improved rendering and event handling
- **Modern features**: Better HiDPI support, touch events
- **Security updates**: Qt 4 has no security patches since 2015
- **Active maintenance**: Qt 5.15 LTS supported until 2024
- **Forward compatibility**: Easier migration to Qt 6 later

## Known Issues

### None Expected
The CorgiCoin Qt code is relatively simple and uses standard Qt widgets. No complex custom rendering or platform-specific code that would cause issues.

## References

- [Qt 5.0 C++ API Changes](https://doc.qt.io/qt-5/sourcebreaks.html)
- [Porting from Qt 4 to Qt 5](https://doc.qt.io/qt-5/portingguide.html)
- [Qt 5 Widgets Module](https://doc.qt.io/qt-5/qtwidgets-index.html)

---

Last Updated: 2025-11-19
Status: Ready for Implementation
