"""Administrator-only local commands for API token provisioning and revocation."""

import argparse
import hashlib
import secrets
import sys
from typing import TextIO

from app.config import Settings
from app.services import build_services
from app.vector_store import SQLiteVectorStore


def issue_user_token(
    store: SQLiteVectorStore,
    display_name: str,
    label: str | None,
    output: TextIO,
) -> tuple[str, str]:
    """Create a user/token and show the plaintext token once to a terminal."""
    if not output.isatty():
        raise RuntimeError(
            "Token issuance requires an interactive terminal so the secret is not redirected."
        )

    plaintext_token = f"eak_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(plaintext_token.encode("utf-8")).hexdigest()
    user, token = store.create_user_with_api_token_hash(
        display_name, token_hash, label
    )

    output.write(f"User ID: {user.user_id}\n")
    output.write(f"Token ID: {token.token_id}\n")
    output.write("API token (shown once; copy it now):\n")
    output.write(f"{plaintext_token}\n")
    output.flush()
    return user.user_id, token.token_id


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision or revoke API tokens in the configured local database."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="create a user and issue one API token")
    create.add_argument("--display-name", required=True)
    create.add_argument("--label", help="optional administrator-assigned token label")

    revoke = commands.add_parser("revoke", help="revoke a token by its token ID")
    revoke.add_argument("--token-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "create-user" and not sys.stdout.isatty():
        parser.error(
            "Token issuance requires an interactive terminal so the secret is not redirected."
        )
    store = build_services(Settings()).store

    if arguments.command == "create-user":
        try:
            issue_user_token(
                store,
                arguments.display_name,
                arguments.label,
                sys.stdout,
            )
        except (RuntimeError, ValueError) as error:
            parser.error(str(error))
        return 0

    revoked = store.revoke_api_token(arguments.token_id)
    if revoked:
        print("Token revoked.")
    else:
        print("Token was not found or was already revoked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
