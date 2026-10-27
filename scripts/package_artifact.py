"""Create a deployable source ZIP from an explicit allowlist after tests pass."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
FILES = ("app.py", "application.py", "Procfile", "requirements.txt", "VERSION")


def main():
    for name in FILES:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(name)
    output = ROOT / "dist" / "blacklist-api.zip"
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix(".tmp")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for name in FILES:
                archive.write(ROOT / name, name)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Artifact created: {output.name} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
