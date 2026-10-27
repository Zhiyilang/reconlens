"""Build the competition submission zip.

    python build_submission.py

Produces ``submission/ReconLens_<captain>.zip`` ready to email to
marketing@newtouch.com. The archive is assembled from an explicit list —
no directory walking — so its contents are reproducible and nothing
accidental (caches, editor files, local reports) can leak in.
"""

import io
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "submission")
PROJECT = "ReconLens"
CAPTAIN = u"支一郎"

INCLUDE = [
    "README.md",
    "README.zh.md",
    "AI_CODING_JOURNEY.md",
    "SUBMISSION_EMAIL.md",
    "LICENSE",
    "eval.py",
    "build_submission.py",
    ".gitignore",
    ".github/workflows/ci.yml",
    "reconlens/__init__.py",
    "reconlens/model.py",
    "reconlens/loader.py",
    "reconlens/matcher.py",
    "reconlens/explain.py",
    "reconlens/report.py",
    "reconlens/samples.py",
    "reconlens/__main__.py",
    "examples/bank.csv",
    "examples/ledger.csv",
]

# Generated into the archive so a judge can read the result without
# running anything.
GENERATED = [("report.md", ["--demo", "--format", "markdown"]),
             ("report.txt", ["--demo", "--format", "text"])]


def check_files():
    missing = [p for p in INCLUDE
               if not os.path.exists(os.path.join(HERE, p))]
    if missing:
        raise SystemExit("missing files: %s" % ", ".join(missing))


def verify_suite():
    """The suite must be green before anything is packaged."""
    print("running assertion suite ...")
    proc = subprocess.run([sys.executable, "eval.py"], cwd=HERE,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise SystemExit("assertion suite failed:\n%s" % out[-2000:])
    line = [l for l in out.splitlines() if l.startswith("passed")]
    print("  %s" % (line[0] if line else "?"))
    return out


def render_demo():
    generated = {}
    for name, argv in GENERATED:
        proc = subprocess.run(
            [sys.executable, "-m", "reconlens"] + argv, cwd=HERE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise SystemExit("demo render failed for %s: %s"
                             % (name, proc.stderr.decode("utf-8", "replace")))
        generated[name] = proc.stdout.decode("utf-8")
    return generated


def main():
    check_files()
    verify_suite()
    generated = render_demo()

    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)

    name = "%s_%s.zip" % (PROJECT, CAPTAIN)
    path = os.path.join(OUT_DIR, name)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            zf.write(os.path.join(HERE, rel), "%s/%s" % (PROJECT, rel))
        for fname, text in generated.items():
            info = zipfile.ZipInfo("%s/%s" % (PROJECT, fname))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, text.encode("utf-8"))

    size = os.path.getsize(path)
    print("-" * 56)
    print("submission : %s" % name)
    print("size       : %d bytes" % size)
    print("files      : %d (%d source + %d generated)"
          % (len(INCLUDE) + len(GENERATED), len(INCLUDE), len(GENERATED)))
    print("path       : %s" % path)
    print("-" * 56)
    print("send to    : marketing@newtouch.com")
    print("subject    : %s 参赛作品提交 - %s" % (PROJECT, CAPTAIN))

    with io.open(os.path.join(OUT_DIR, "CHECKS.txt"), "w",
                 encoding="utf-8") as fh:
        fh.write(u"# %s submission manifest\n" % PROJECT)
        fh.write(u"sha256-at-build: see below\n")
        for rel in INCLUDE:
            fh.write(u"INCLUDE %s\n" % rel)
        for fname, _ in GENERATED:
            fh.write(u"GENERATED %s\n" % fname)


if __name__ == "__main__":
    main()
