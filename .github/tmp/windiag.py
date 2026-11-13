import os, sys, tempfile, stat
from pathlib import Path
sys.path.insert(0, "scripts")
import command_guard_policy as policy
print("python", sys.version)
print("tempdir", tempfile.gettempdir(), "TEMP", os.environ.get("TEMP"), "RUNNER_TEMP", os.environ.get("RUNNER_TEMP"))
print("SYSTEM_TREES", sorted(policy.SYSTEM_TREES))
with tempfile.TemporaryDirectory() as temp:
    project = Path(temp).resolve() / "project"
    project.mkdir()
    small = project / "small.txt"
    small.write_text("abc", encoding="utf-8")
    print("project", project, "parts", project.parts)
    info = small.lstat()
    print("lstat", info)
    print("file_attributes", hex(getattr(info, "st_file_attributes", 0)), "ismount", os.path.ismount(small), "project dev", project.stat().st_dev)
    for command in ("rm -- small.txt", "mv small.txt other.txt", "cp small.txt copy.txt", "chmod 600 small.txt", "truncate -s 0 small.txt", "cat small.txt"):
        d = policy.classify(command, project, project)
        print(repr(command), "->", d.tier, "|", d.reason)
