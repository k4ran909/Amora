"""Create .env from .env.example with a freshly generated FERNET_KEY (never overwrites an existing .env)."""

from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    env, example = ROOT / ".env", ROOT / ".env.example"
    if env.exists():
        print(".env already exists; leaving it untouched.")
        return
    key = Fernet.generate_key().decode()
    lines = [f"FERNET_KEY={key}" if line.startswith("FERNET_KEY=") else line
             for line in example.read_text(encoding="utf-8").splitlines()]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Created .env with a new FERNET_KEY. Now fill in your bot tokens and owner IDs.")


if __name__ == "__main__":
    main()
