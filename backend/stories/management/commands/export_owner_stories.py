"""Hands the owner's own stories to one reader, sealed (T16).

    uv run python manage.py export_owner_stories --key=PUBLIC_KEY   # seal, store, print a link
    uv run python manage.py export_owner_stories --forget           # delete the stored file

The reader makes a key pair first and opens the file with the private key, which never leaves
their machine (`python -m stories.sealed`). Only the owner accounts' stories are in it (K7), with
their world state, and nothing in it or in this command's output names an account or a row.

The sealed file goes to the pictures storage (`MEDIA_BUCKET`), which is private, under one fixed
name, so a new export replaces the last and nothing piles up. What is printed is a signed link
to it that stops working after `--minutes`. The link may be seen by anyone, as the logs of a
public repository's Actions are: the file behind it opens only with the reader's private key.
On Cloud Run this runs as the migration job with other arguments, started by the Deploy workflow
(docs/DEPLOY.md, "Reading the owner's own stories").
"""

import json

from django.core.management.base import BaseCommand, CommandError

from media.storage import get_storage
from stories import sealed
from stories.owner_export import export_owner_stories, owners

STORAGE_KEY = "exports/owner-stories.bin"
MINUTES = 30
MAX_MINUTES = 60


class Command(BaseCommand):
    help = "Seals the owner's own stories for one reader and prints a short-lived link to them."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--key",
            default="",
            help="The reader's public key, as `python -m stories.sealed keygen` prints it.",
        )
        parser.add_argument(
            "--minutes",
            type=int,
            default=MINUTES,
            help=f"How long the link works (default {MINUTES}, at most {MAX_MINUTES}).",
        )
        parser.add_argument(
            "--forget",
            action="store_true",
            help="Delete the stored file instead of making a new one.",
        )

    def handle(self, *args, key: str, minutes: int, forget: bool, **options):
        storage = get_storage()
        if forget:
            storage.delete(STORAGE_KEY)
            self.stdout.write("The stored export is deleted.")
            return
        if not key:
            raise CommandError("Give the reader's public key with --key, or --forget.")
        try:
            recipient = sealed.parse_key(key)
        except sealed.SealError as error:
            raise CommandError(f"--key: {error}") from error
        if not 1 <= minutes <= MAX_MINUTES:
            raise CommandError(f"--minutes must be from 1 to {MAX_MINUTES}.")
        if not owners().exists():
            raise CommandError(
                "No account holds the owner role with an email in OWNER_EMAILS, so there is "
                "nothing to export."
            )
        export = export_owner_stories()
        content = json.dumps(export, ensure_ascii=False, separators=(",", ":")).encode()
        try:
            file = sealed.seal(content, recipient)
        except sealed.SealError as error:
            raise CommandError(f"--key: {error}") from error
        storage.save(STORAGE_KEY, file, "application/octet-stream")
        link = storage.url(STORAGE_KEY, minutes * 60)
        scenes = sum(len(story["scenes"]) for story in export["stories"])
        self.stdout.write(
            f"Sealed {len(export['stories'])} stories with {scenes} scenes into {len(file)} "
            f"bytes. Only the private key of --key opens them. The link works for {minutes} "
            "minutes:"
        )
        self.stdout.write(link.url)
