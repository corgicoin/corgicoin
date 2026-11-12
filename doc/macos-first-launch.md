# Opening CorgiCoin on macOS

The macOS downloads are signed ad hoc, not with an Apple Developer ID, and are not notarized. macOS therefore
refuses to open them the first time ("Apple could not verify..."). To open them anyway:

**CorgiCoin-Qt.app (the wallet)**

1. Unzip the download and move `CorgiCoin-Qt.app` to Applications if you like.
2. Double-click it. macOS says it can't be opened; click **Done** (not "Move to Trash").
3. Open **System Settings → Privacy & Security**, scroll to the message about CorgiCoin-Qt, and click **Open Anyway**.
4. Confirm with your password. From then on it opens normally.

**corgicoind (the daemon)**, from Terminal, in the folder you unpacked:

```
xattr -dr com.apple.quarantine corgicoind lib
./corgicoind
```

Keep `corgicoind` and its `lib` folder together: the daemon loads its libraries from there, so it runs without
Homebrew.

Verify any download against `SHA256SUMS` on the release page first: `shasum -a 256 <file>`.
