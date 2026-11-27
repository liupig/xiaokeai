"""Install the bundled skill for local agents. Requires Python 3.8 or later."""
import argparse
import filecmp
import os
import shutil
import sys
import tempfile
from pathlib import Path


NAME = "xiaokeai-character-studio"
SOURCE = Path(__file__).resolve().parent / NAME


def files(root):
    return {f.relative_to(root) for f in root.rglob("*")
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"}


def same_tree(dest):
    names = files(SOURCE)
    return dest.is_dir() and names == files(dest) and all(
        filecmp.cmp(SOURCE / f, dest / f, shallow=False) for f in names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",choices=("all","codex","claude","cursor"),default="all")
    parser.add_argument("--project",type=Path,help="Install for an existing project instead of your user account")
    args = parser.parse_args()
    if not (SOURCE/"SKILL.md").is_file():
        parser.error(f"Extract the complete ZIP first. Missing {SOURCE/'SKILL.md'}")
    root = args.project.expanduser().resolve() if args.project else Path.home()
    if not root.is_dir():
        parser.error(f"Project directory not found: {root}")
    shared = root/".agents"/"skills"
    claude = root/".claude"/"skills"
    if not args.project and os.environ.get("CLAUDE_CONFIG_DIR"):
        claude = Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser().resolve()/"skills"
    roots = {"all":[shared,claude],"codex":[shared],"cursor":[shared],"claude":[claude]}
    pending = []
    for directory in dict.fromkeys(roots[args.target]):
        dest = directory/NAME
        if dest.exists() or dest.is_symlink():
            if not same_tree(dest):
                parser.exit(1,f"A different copy already exists at {dest}. Keep it or move it aside before installing.\n")
            print(f"Already installed: {dest}")
        else:
            pending.append(dest)
    for dest in pending:
        dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".install-",dir=dest.parent) as tmp:
            staged = Path(tmp)/NAME
            shutil.copytree(SOURCE,staged,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
            try:
                staged.rename(dest)
            except OSError:
                if not same_tree(dest):
                    raise
        print(f"Installed: {dest}")
    return 0


if __name__=="__main__":
    sys.exit(main())
