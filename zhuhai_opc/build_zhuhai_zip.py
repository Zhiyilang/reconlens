# -*- coding: utf-8 -*-
"""Build the Zhuhai OPC submission package.

    python build_zhuhai_zip.py

Produces ``珠海OPC参赛材料_ReconLens_<captain>.zip`` — the outer package
(business plan + forms + demo video + source archive) for the Zhuhai OPC
entrepreneurship contest.

Two-stage build, both reproducible:

  1. The nested source archive is produced by the *parent* builder
     (``../build_submission.py``), which refuses to package anything unless
     the assertion suite is green and uses an explicit file list — so the
     source inside this package can never drift from the repository.
  2. This script packs the outer archive from an explicit list as well.

Run it after ANY edit to reconlens sources or to the four documents, and the
package is guaranteed fresh. A stale package is the classic silent failure:
everything looks submitted, but the judge unzips yesterday's code.
"""

import io
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
PROJECT = "ReconLens"
CAPTAIN = u"支一郎"
PREFIX = u"珠海OPC_%s_%s" % (PROJECT, CAPTAIN)          # inner directory name
OUT_NAME = u"珠海OPC参赛材料_%s_%s.zip" % (PROJECT, CAPTAIN)  # canonical archive name

# Outer package: explicit list, no directory walking.
INCLUDE = [
    u"BUSINESS_PLAN.md",
    u"REGISTRATION_FORM.md",
    u"COMMITMENT_LETTER.md",
    u"SUBMIT_CHECKLIST.md",
    u"reconlens_zhuhai.mp4",
]

NESTED_NAME = u"产品源码_%s_%s.zip" % (PROJECT, CAPTAIN)


def check_files():
    missing = [p for p in INCLUDE
               if not os.path.exists(os.path.join(HERE, p))]
    if missing:
        raise SystemExit("missing files: %s" % ", ".join(missing))


def build_nested_source():
    """Run the parent builder; return the fresh nested zip as bytes."""
    print("stage 1: building fresh source archive via ../build_submission.py")
    proc = subprocess.run([sys.executable, "build_submission.py"], cwd=PARENT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise SystemExit("parent builder failed:\n%s" % out[-2000:])
    for line in out.splitlines():
        if line.strip():
            print("  | %s" % line)
    nested_path = os.path.join(PARENT, "submission",
                               "%s_%s.zip" % (PROJECT, CAPTAIN))
    if not os.path.exists(nested_path):
        raise SystemExit("parent builder produced no archive at %s"
                         % nested_path)
    with io.open(nested_path, "rb") as fh:
        return fh.read()


def main():
    check_files()
    nested = build_nested_source()

    out_path = os.path.join(HERE, OUT_NAME)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            zf.write(os.path.join(HERE, rel), "%s/%s" % (PREFIX, rel))
        info = zipfile.ZipInfo("%s/%s" % (PREFIX, NESTED_NAME))
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, nested)

    # Post-build self-check: nothing stale may ship.
    with zipfile.ZipFile(out_path) as zf:
        names = zf.namelist()
        for rel in INCLUDE:
            if "%s/%s" % (PREFIX, rel) not in names:
                raise SystemExit("post-build check failed: %s missing" % rel)
        nz = zipfile.ZipFile(io.BytesIO(
            zf.read("%s/%s" % (PREFIX, NESTED_NAME))))
        inner_eval = nz.read("%s/eval.py" % PROJECT).decode("utf-8")
        src_eval = io.open(os.path.join(PARENT, "eval.py"),
                           encoding="utf-8").read()
        if inner_eval != src_eval:
            raise SystemExit("post-build check failed: nested eval.py stale")

    print("-" * 56)
    print("package    : %s" % OUT_NAME)
    print("size       : %d bytes" % os.path.getsize(out_path))
    print("contents   : %d docs/media + nested source (%d entries)"
          % (len(INCLUDE), len(nested and zipfile.ZipFile(io.BytesIO(nested)).namelist())))
    print("nested     : %s (fresh from ../build_submission.py)" % NESTED_NAME)
    print("self-check : nested eval.py identical to repository")
    print("path       : %s" % out_path)
    print("-" * 56)


if __name__ == "__main__":
    main()
