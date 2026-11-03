"""Makes a story to play in development from one of the example worlds (`engine.samples`), until
starting a draft (`POST /v1/drafts/{id}/start`, WS12) makes them.

It saves the story the way starting a draft does: the world state at turn 0, no scenes, version 1.
The app then plays its opening with `kind: "opening"`.

    uv run python manage.py seed_story player@example.com --world cultivation
"""

from django.core.management.base import BaseCommand, CommandError

from accounts import rules
from accounts.models import User
from engine.context import StorySettings
from engine.samples import cultivation_world, grounded_world
from stories.models import Engine, Rating, Story

# Each world with the premise it was drafted from (G1).
WORLDS = {
    "grounded": (
        grounded_world,
        "I'm the son of a mafia boss in 1970s Naples, and someone inside the family killed my "
        "father.",
    ),
    "cultivation": (
        cultivation_world,
        "I'm reborn as the weakest outer disciple of the Azure Cloud Sect, with my past life's "
        "memories and the power to stop time.",
    ),
}


class Command(BaseCommand):
    help = "Makes a story from an example world for a player, ready for its opening turn."

    def add_arguments(self, parser) -> None:
        parser.add_argument("email", help="The player who owns the story.")
        parser.add_argument("--world", choices=sorted(WORLDS), default="grounded")
        parser.add_argument(
            "--rating",
            choices=[Rating.TEEN, Rating.MATURE],
            help="Defaults to Mature when the account may play it (F8), otherwise Teen.",
        )

    def handle(self, *args, email: str, world: str, rating: str | None, **options) -> None:
        user = User.objects.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError(f"No account with the email {email!r}.")
        if rating is None:
            mature = rules.allows_rating(user.birth_date, Rating.MATURE)
            rating = Rating.MATURE if mature else Rating.TEEN
        elif not rules.allows_rating(user.birth_date, rating):
            raise CommandError(f"This account can't play {rating} stories (F8).")
        build, premise = WORLDS[world]
        state = build()
        story = Story.objects.create(
            owner=user,
            title=state.bible.title or world.title(),
            premise=premise,
            genre=state.bible.genre,
            rating=rating,
            settings=StorySettings().model_dump(mode="json"),
            engine=Engine.GRAPH,
            state=state.model_dump(mode="json"),
            turn=state.turn,
            version=1,
        )
        self.stdout.write(str(story.pk))
