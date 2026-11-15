"""Generate and build the Atech wearable project without flashing hardware."""
import argparse
import json
import shlex
from pathlib import Path
import subprocess
import sys

from atech import Project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate-only", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    project = Project.load(here / "project.yaml")
    output = project.generate(here / "build")
    print(f"Generated project: {output}", flush=True)
    if not args.generate_only:
        subprocess.run([sys.executable, "-m", "platformio", "run", "-d", str(output)], check=True)
        subprocess.run([sys.executable, "-m", "platformio", "run", "-d", str(output), "-t", "compiledb"], check=True)
        database = output / "compile_commands.json"
        entries = json.loads(database.read_text())
        main = next(e for e in entries
                    if (Path(e["directory"]) / e["file"]).resolve()
                    == (output / "src" / "main.cpp").resolve())
        # wearable.cpp is included by main.cpp; index it with the same SDK flags.
        app = dict(main)
        app["file"] = str(here / "wearable.cpp")
        arguments = shlex.split(app.pop("command"))
        app["arguments"] = [
            app["file"] if (Path(main["directory"]) / arg).resolve()
            == (output / "src" / "main.cpp").resolve() else arg
            for arg in arguments
        ]
        entries.append(app)
        database.write_text(json.dumps(entries, indent=2) + "\n")


if __name__ == "__main__":
    main()
