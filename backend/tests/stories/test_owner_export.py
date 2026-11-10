"""`manage.py export_owner_stories`: the owner's own stories, sealed for one reader (T16)."""

import io
import json

import pytest
from django.core.management import CommandError, call_command

from accounts.models import Role
from media.storage import get_storage
from stories import sealed
from stories.management.commands.export_owner_stories import STORAGE_KEY
from stories.models import PendingEvent, Scene, SceneKind, Story

OWNER = "owner@example.com"
NARRATION = "Rain hammers the slate roof of the Jade Pavilion."


@pytest.fixture
def reader():
    """A reader's key pair: the private key, and the public key as the command takes it."""
    private_key = sealed.new_private_key()
    return private_key, sealed.key_text(sealed.public_key(private_key))


@pytest.fixture
def owner(make_user, settings):
    settings.OWNER_EMAILS = [OWNER]
    return make_user(OWNER, role=Role.OWNER)


def _story(user, title: str, **fields) -> Story:
    story = Story.objects.create(
        owner=user,
        title=title,
        premise="A sect in the mountains.",
        genre="cultivation",
        state={"world": {"secret": "The elder is the thief."}},
        turn=1,
        **fields,
    )
    Scene.objects.create(
        story=story,
        turn=1,
        kind=SceneKind.ACTION,
        player_action="I climb the wall.",
        narration=NARRATION,
        details={"steps": [{"kind": "move"}]},
        world_start_s=0,
        world_end_s=60,
        image_planned=True,
        image_url=f"https://pictures.example/stories/{story.id}/1.png",
    )
    PendingEvent.objects.create(
        story=story, due_world_s=86400, kind="world_tick", payload={"day": 1}
    )
    return story


def _export(private_key: bytes) -> dict:
    return json.loads(sealed.unseal(get_storage().load(STORAGE_KEY), private_key))


def _run(*args: str) -> str:
    out = io.StringIO()
    call_command("export_owner_stories", *args, stdout=out)
    return out.getvalue()


# The sealed file


def test_a_sealed_file_opens_only_with_the_readers_private_key():
    private_key = sealed.new_private_key()
    file = sealed.seal(b"the story so far", sealed.public_key(private_key))

    assert b"the story so far" not in file
    assert sealed.unseal(file, private_key) == b"the story so far"
    with pytest.raises(sealed.SealError):
        sealed.unseal(file, sealed.new_private_key())


def test_a_changed_file_does_not_open():
    private_key = sealed.new_private_key()
    file = bytearray(sealed.seal(b"the story so far", sealed.public_key(private_key)))
    file[-1] ^= 1

    with pytest.raises(sealed.SealError):
        sealed.unseal(bytes(file), private_key)
    with pytest.raises(sealed.SealError):
        sealed.unseal(b"not a sealed file", private_key)


def test_two_seals_of_the_same_content_differ():
    key = sealed.public_key(sealed.new_private_key())

    assert sealed.seal(b"same", key) != sealed.seal(b"same", key)


@pytest.mark.parametrize("text", ["", "short", "A" * 44, "!" * 43, "A" * 42 + "="])
def test_a_key_must_be_43_characters_of_url_safe_base64(text):
    with pytest.raises(sealed.SealError):
        sealed.parse_key(text)


def test_a_key_survives_being_written_and_read():
    key = sealed.public_key(sealed.new_private_key())

    assert sealed.parse_key(f" {sealed.key_text(key)}\n") == key


def test_the_reader_makes_a_key_and_opens_a_file_from_the_command_line(tmp_path, capsys):
    key_file, sealed_file, out_file = (tmp_path / name for name in ("key", "in.bin", "out.json"))

    assert sealed.main(["keygen", str(key_file)]) == 0
    public = capsys.readouterr().out.strip()
    assert key_file.stat().st_mode & 0o777 == 0o600
    assert sealed.main(["keygen", str(key_file)]) == 1, "a key is never written over"

    sealed_file.write_bytes(sealed.seal(b'{"stories":[]}', sealed.parse_key(public)))
    assert sealed.main(["open", str(key_file), str(sealed_file), str(out_file)]) == 0
    assert out_file.read_bytes() == b'{"stories":[]}'
    assert out_file.stat().st_mode & 0o777 == 0o600


# The export


def test_only_the_owners_stories_are_exported_whole(owner, make_user, reader):
    private_key, public = reader
    story = _story(owner, "The Jade Pavilion")
    other = _story(make_user("player@example.com"), "A player's secret")

    out = _run(f"--key={public}")
    export = _export(private_key)

    [exported] = export["stories"]
    assert exported["title"] == "The Jade Pavilion"
    assert exported["state"] == {"world": {"secret": "The elder is the thief."}}
    [scene] = exported["scenes"]
    assert scene["narration"] == NARRATION
    assert scene["player_action"] == "I climb the wall."
    assert scene["time"]["world_end_s"] == 60
    assert scene["image"] == {"kind": None, "status": None}
    [event] = exported["pending_events"]
    assert (event["kind"], event["due_world_s"], event["payload"]) == (
        "world_tick",
        86400,
        {"day": 1},
    )
    # Nothing names an account or a row, in the file or in what the command prints.
    text = json.dumps(export)
    for private in (OWNER, str(owner.id), str(story.id), str(other.id), "A player's secret"):
        assert private not in text
        assert private not in out
    assert NARRATION not in out
    assert "Sealed 1 stories with 1 scenes" in out


def test_the_stored_file_is_sealed_and_the_link_reads_it(owner, reader):
    private_key, public = reader
    _story(owner, "The Jade Pavilion")

    out = _run(f"--key={public}", "--minutes=5")

    stored = get_storage().load(STORAGE_KEY)
    assert stored.startswith(sealed.MAGIC)
    assert NARRATION.encode() not in stored
    assert b"Jade" not in stored
    link = out.strip().splitlines()[-1]
    assert link.startswith(f"/media/{STORAGE_KEY}?expires=")
    assert "works for 5 minutes" in out


def test_a_new_export_replaces_the_last_and_forget_deletes_it(owner, reader):
    private_key, public = reader
    _story(owner, "The Jade Pavilion")
    _run(f"--key={public}")
    _story(owner, "The Second Story")

    _run(f"--key={public}")
    assert [story["title"] for story in _export(private_key)["stories"]] == [
        "The Jade Pavilion",
        "The Second Story",
    ]

    assert "deleted" in _run("--forget")
    assert not get_storage().exists(STORAGE_KEY)
    assert "deleted" in _run("--forget"), "nothing stored is not an error"


def test_the_role_alone_or_the_email_alone_is_not_the_owner(make_user, settings, reader):
    """K7: the role comes only from a verified Google sign-in, and the list can change."""
    _, public = reader
    settings.OWNER_EMAILS = [OWNER]
    _story(make_user(OWNER), "Signed up with the owner's address")
    _story(make_user("former@example.com", role=Role.OWNER), "No longer in the list")

    with pytest.raises(CommandError, match="No account holds the owner role"):
        _run(f"--key={public}")
    assert not get_storage().exists(STORAGE_KEY)


def test_a_missing_or_bad_key_exports_nothing(owner):
    _story(owner, "The Jade Pavilion")

    with pytest.raises(CommandError, match="--key"):
        _run()
    with pytest.raises(CommandError, match="43 characters"):
        _run("--key=not-a-key")
    with pytest.raises(CommandError, match="--minutes"):
        _run(f"--key={sealed.key_text(sealed.public_key(sealed.new_private_key()))}", "--minutes=0")
    assert not get_storage().exists(STORAGE_KEY)
