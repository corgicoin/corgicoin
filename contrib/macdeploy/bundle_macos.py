#!/usr/bin/env python3
"""Make CorgiCoin's macOS binaries self-contained, so they run on a Mac without Homebrew.

  bundle_macos.py app <corgicoin-qt.app>
      Run after macdeployqt. Drops the virtual-keyboard input plugin (Homebrew's Qt deploys it, and it drags in
      QML/Quick, which the wallet never uses), removes frameworks and libraries nothing references any more, gives
      every bundled library a bundle-relative id, and signs the bundle ad hoc.

  bundle_macos.py daemon <corgicoind> <outdir>
      Copies corgicoind to <outdir> with every non-system library it needs in <outdir>/lib, rewritten to load from
      there, and signs them ad hoc.

Both finish by checking that no binary still loads anything from outside the bundle or the OS (/usr/lib,
/System), and exit non-zero if one does. Apple Silicon refuses to run unsigned code, hence the ad-hoc signature;
it is not a Developer ID signature, so Gatekeeper still asks the user to confirm the first launch.
"""
import os
import re
import shutil
import subprocess
import sys

SYSTEM = ("/usr/lib/", "/System/")


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def is_macho(path):
    if os.path.islink(path) or not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        magic = f.read(4)
    return magic in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xcf", b"\xbe\xba\xfe\xca")


def deps(path):
    """Load commands of a Mach-O file, without its own install name."""
    own = run("otool", "-D", path).splitlines()[1:]
    out = []
    for line in run("otool", "-L", path).splitlines()[1:]:
        name = line.strip().split(" (compatibility")[0]
        if name and name not in own:
            out.append(name)
    return out


def rpaths(path):
    text = run("otool", "-l", path)
    return re.findall(r"cmd LC_RPATH\n\s+cmdsize \d+\n\s+path (\S+)", text)


MAIN_RPATHS = []   # the executable's LC_RPATHs: dyld also searches them for every library it loads


def resolve(dep, binary, exe_dir):
    """Where dep (as written in binary) would be found, or None."""
    loader = os.path.dirname(binary)
    if dep.startswith("@executable_path/"):
        cands = [os.path.join(exe_dir, dep[len("@executable_path/"):])]
    elif dep.startswith("@loader_path/"):
        cands = [os.path.join(loader, dep[len("@loader_path/"):])]
    elif dep.startswith("@rpath/"):
        cands = []
        for rp in rpaths(binary) + MAIN_RPATHS:
            rp = rp.replace("@loader_path", loader).replace("@executable_path", exe_dir)
            cands.append(os.path.join(rp, dep[len("@rpath/"):]))
    else:
        cands = [dep]
    for c in cands:
        if os.path.exists(c):
            return os.path.realpath(c)
    return None


def machos(root):
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            if is_macho(p):
                yield p


def check(root, exe_dir):
    """Every dependency is a system library or resolves inside root."""
    bad = []
    root_real = os.path.realpath(root)
    for b in machos(root):
        for dep in deps(b):
            if dep.startswith(SYSTEM):
                continue
            r = resolve(dep, b, exe_dir)
            if r is None or not r.startswith(root_real + os.sep):
                bad.append("%s -> %s" % (os.path.relpath(b, root), dep))
    return bad


def sign(target):
    run("codesign", "--force", "--deep", "--sign", "-", target)
    run("codesign", "--verify", "--deep", "--strict", target)


# Plugins the wallet uses: the Cocoa platform and macOS style, TLS backends, and the image formats of its resources
# and of icons the system may hand it (PNG is built into QtGui; .mng drives the sync animation). The rest of what
# Homebrew's Qt deploys (SVG, PDF via QtWebEngine, WebP, TIFF, GLib network info, the virtual keyboard) only drags in
# libraries.
KEEP_PLUGINS = {
    "platforms/libqcocoa.dylib", "styles/libqmacstyle.dylib",
    "tls/libqsecuretransportbackend.dylib", "tls/libqopensslbackend.dylib", "tls/libqcertonlybackend.dylib",
    "imageformats/libqmng.dylib", "imageformats/libqgif.dylib", "imageformats/libqico.dylib",
    "imageformats/libqjpeg.dylib", "imageformats/libqicns.dylib",
    "networkinformation/libqapplenetworkinformation.dylib",
}
LIB_SEARCH = ["/opt/homebrew/lib", "/usr/local/lib"]


def find_outside(dep):
    """The file or framework directory a dependency names, looked up outside the bundle."""
    if dep.startswith("@rpath/"):
        rel = dep[len("@rpath/"):]
        for d in LIB_SEARCH:
            if os.path.exists(os.path.join(d, rel)):
                head = rel.split("/")[0]
                return os.path.join(d, head) if head.endswith(".framework") else os.path.join(d, rel)
        return None
    if dep.startswith("/") and os.path.exists(dep):
        m = re.match(r"(.*?/[^/]+\.framework)/", dep)
        return m.group(1) if m else dep
    return None


def bundle_app(app):
    contents = os.path.join(app, "Contents")
    exe_dir = os.path.join(contents, "MacOS")
    frameworks = os.path.join(contents, "Frameworks")
    plugins = os.path.join(contents, "PlugIns")
    os.makedirs(frameworks, exist_ok=True)

    for p in list(machos(plugins)):
        if os.path.relpath(p, plugins) not in KEEP_PLUGINS:
            os.remove(p)
    for d, dirs, files in os.walk(plugins, topdown=False):
        if not os.listdir(d) and d != plugins:
            os.rmdir(d)

    # Search the bundle, never Homebrew: drop absolute rpaths, give the executable the Frameworks directory
    for b in machos(app):
        for rp in rpaths(b):
            if not rp.startswith("@"):
                run("install_name_tool", "-delete_rpath", rp, b)
    for exe in machos(exe_dir):
        if "@executable_path/../Frameworks" not in rpaths(exe):
            run("install_name_tool", "-add_rpath", "@executable_path/../Frameworks", exe)
    MAIN_RPATHS[:] = ["@executable_path/../Frameworks"]

    # Copy in whatever is still missing, until the bundle is closed
    changed = True
    while changed:
        changed = False
        for b in list(machos(app)):
            for dep in deps(b):
                if dep.startswith(SYSTEM):
                    continue
                r = resolve(dep, b, exe_dir)
                if r and r.startswith(os.path.realpath(app) + os.sep):
                    continue
                src = find_outside(dep)
                if src is None:
                    sys.exit("cannot find %s (needed by %s)" % (dep, os.path.relpath(b, app)))
                name = os.path.basename(src)
                dst = os.path.join(frameworks, name)
                if not os.path.exists(dst):
                    print("adding", name)
                    if os.path.isdir(src):
                        shutil.copytree(os.path.realpath(src), dst, symlinks=True)
                    else:
                        shutil.copy2(os.path.realpath(src), dst)
                        os.chmod(dst, 0o644)
                if not dep.startswith("@rpath/"):
                    rel = dep[dep.index(name):] if name in dep else name
                    run("install_name_tool", "-change", dep, "@rpath/" + rel, b)
                changed = True

    # Keep only what the executable and the remaining plugins actually reach
    roots = list(machos(exe_dir)) + list(machos(plugins))
    reached, todo = set(), list(roots)
    while todo:
        b = todo.pop()
        for dep in deps(b):
            r = resolve(dep, b, exe_dir)
            if r and r.startswith(os.path.realpath(frameworks)) and r not in reached:
                reached.add(r)
                todo.append(r)
    for entry in os.listdir(frameworks):
        p = os.path.join(frameworks, entry)
        inner = [os.path.realpath(x) for x in machos(p)] if os.path.isdir(p) else [os.path.realpath(p)]
        if not any(x in reached for x in inner):
            print("removing unused", entry)
            shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)

    for lib in machos(frameworks):
        own = run("otool", "-D", lib).splitlines()[1:]
        if own and not own[0].startswith("@"):
            rel = os.path.relpath(lib, frameworks)
            run("install_name_tool", "-id", "@rpath/" + rel, lib)

    bad = check(app, exe_dir)
    if bad:
        sys.exit("outside the bundle:\n  " + "\n  ".join(bad))
    sign(app)
    print("ok:", app)


def bundle_daemon(binary, outdir):
    libdir = os.path.join(outdir, "lib")
    os.makedirs(libdir, exist_ok=True)
    exe = os.path.join(outdir, os.path.basename(binary))
    shutil.copy2(binary, exe)
    os.chmod(exe, 0o755)

    copied = {}   # real source path -> bundled name
    todo = [(exe, os.path.realpath(binary))]   # (bundled file, the original it was copied from)
    while todo:
        b, orig = todo.pop()
        for dep in deps(b):
            if dep.startswith(SYSTEM):
                continue
            # resolve against the original file, where its @loader_path and rpaths still make sense
            src = resolve(dep, orig, os.path.dirname(os.path.realpath(binary)))
            if src is None:
                sys.exit("cannot find %s (needed by %s)" % (dep, orig))
            name = os.path.basename(src)
            if src not in copied:
                copied[src] = name
                dst = os.path.join(libdir, name)
                shutil.copy2(src, dst)
                os.chmod(dst, 0o644)
                run("install_name_tool", "-id", "@loader_path/" + name, dst)
                todo.append((dst, src))
            new = ("@executable_path/lib/" if b == exe else "@loader_path/") + name
            run("install_name_tool", "-change", dep, new, b)
        for rp in rpaths(b):
            if not rp.startswith("@"):
                run("install_name_tool", "-delete_rpath", rp, b)

    bad = check(outdir, outdir)
    if bad:
        sys.exit("outside the bundle:\n  " + "\n  ".join(bad))
    for f in machos(outdir):
        run("codesign", "--force", "--sign", "-", f)
    print("ok: %s with %d libraries" % (exe, len(copied)))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "app":
        bundle_app(sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] == "daemon":
        bundle_daemon(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
