"""S4: a scene's ending is shown, never told: what code reads as the narrator telling the player
their move, what it leaves out of a told scene, and what it holds back while one streams."""

import pytest

from graph.turn.last_lines import showable, shown, tells

# The endings the real narrator wrote in the plays of 2026-11-14, each after what it had shown.
SPY = (
    "Minister Gong leans back against the silk cushions, already drowsy with wine. His token "
    "hangs loose at his belt, and downstairs his carriage holds the palace guard schedules."
)
SPY_TOLD = (
    "You must decide whether to slip your sleeping powder into his wine to slip away to the "
    "carriages, or keep him charmed here while you devise a cleaner escape."
)
FARM = "The first winter storm is only weeks away, and your firewood stack is low."
FARM_TOLD = (
    "You must decide whether to secure your high home for the long freeze or walk down the "
    "winding mountain path to the village below."
)
MEMOIRS = "The finished memoirs lie open on your desk, the ink glinting in the firelight."
MEMOIRS_TOLD = "It is time to rest, or perhaps to share what you have done."
COURTYARD = "Downstairs, his carriage remains unguarded in the dark courtyard of the pavilion."
COURTYARD_TOLD = "The time has come to slip away and secure the schedules."
# The first check on the real models after code held the line: the move is told in the
# sentence's second clause.
BRIDGE = "They are stepping closer, their knives catching the cold morning light."
BRIDGE_TOLD = (
    "If you are to survive this ambush and reach the ranking tournament, you must act before "
    "they pin you between them."
)


@pytest.mark.parametrize(
    "sentence",
    [
        SPY_TOLD,
        FARM_TOLD,
        MEMOIRS_TOLD,
        COURTYARD_TOLD,
        BRIDGE_TOLD,
        # In a clause after the sentence's first.
        "The gate stands open, and the choice is yours.",
        "With the guards asleep, it is time to slip away.",
        "One thing is clear: you must choose.",
        "The thugs close in, so now you have to decide.",
        "The bridge sways under you — what will you do?",
        "Whichever way the wind turns, you must act now.",
        "Con el sol ya alto, es hora de partir.",
        "El puente cruje y, pase lo que pase, tú decides.",
        "Amb la porta oberta, ara has de decidir.",
        "La boira s'aixeca i, ara sí, la decisió és teva.",
        "Now you must choose.",
        "But you will have to decide soon.",
        "You need to act quickly.",
        "*You have to make a choice.*",
        "Choose wisely.",
        "Whatever you decide, the night will not wait.",
        "It's time to leave the valley behind.",
        "Now is the moment to strike.",
        "You can either wake him or fetch the bailiff.",
        "You have only two options: fight or flee.",
        "The choice is yours.",
        "The next move is yours.",
        "It is up to you now.",
        "What happens next is up to you.",
        "What will you do?",
        "What do you do next?",
        "How will you respond?",
        "What is your next move?",
        "What now?",
        "Which path will you take?",
        "Will you wake him, or fetch the bailiff?",
        "Do you fight or do you run?",
        "Debes decidir si despertarlo o avisar al alguacil.",
        "Ahora tienes que elegir.",
        "Te toca decidir.",
        "Ha llegado el momento de partir.",
        "Es hora de volver a casa.",
        "Puedes elegir entre la espada y la huida.",
        "Tienes dos opciones: luchar o huir.",
        "La decisión es tuya.",
        "Tú decides.",
        "Todo depende de ti.",
        "¿Qué harás?",
        "¿Qué vas a hacer ahora?",
        "¿Cómo respondes?",
        "¿Cuál será tu próximo movimiento?",
        "¿Y ahora qué?",
        "Has de decidir si el despertes o avises el batlle.",
        "Ara et toca triar.",
        "Cal que decideixis aviat.",
        "Hauràs d'escollir aviat.",
        "Has d'actuar ara.",
        "Ha arribat l'hora de marxar.",
        "Ja és hora d'anar-se'n.",
        "És hora de tornar a casa.",
        "Pots triar entre l'espasa i la fugida.",
        "Tens dues opcions: lluitar o fugir.",
        "La decisió és teva.",
        "Tu decideixes.",
        "Tot depèn de tu.",
        "Què faràs?",
        "Com respons?",
        "Quin serà el teu proper moviment?",
        "I ara què?",
    ],
)
def test_a_sentence_that_tells_the_player_their_move_is_read_as_one(sentence):
    assert tells(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        # How the real narrator ended the scenes it ended well.
        "Lord Oswald looks up, his stern eyes settling on you, waiting to hear how you intend "
        "to secure the border road.",
        "He watches you with a hard, suspicious squint, waiting to see how you respond.",
        "Screams echo from the damp streets as black smoke begins to rise into the cold sky.",
        "It is clear that she carries some difficult news she is hesitant to voice.",
        "Outside, the bare branches of the maples sway in the dusk.",
        "Your long story is done, and your peace is made.",
        "Però no pots deixar-la morir així.",
        "La por que porta a sobre és tan espessa com la boira del Cap de Creus.",
        # Near misses: time that passes, a decision someone else has, a question nobody asks.
        "It is time for the harvest, and the whole village is in the fields.",
        "You should have known better than to trust him.",
        "You must have dozed off, because the fire is out.",
        "You can hear the river from here.",
        "The decision is the council's, and the council is in no hurry.",
        "Decide marcharse sin mirar atrás.",
        "Will you ever see the valley again.",
        "What do you make of a man like that.",
        "Es la hora en que cierran las puertas.",
        # Words that also tell a game, a thing in hand or what the character does.
        "Your move.",
        "It's your turn at the board, and the whole hall is watching.",
        "Está en tus manos, frío y pesado, el medallón de tu madre.",
        "És a les teves mans, fred i feixuc, el medalló de la teva mare.",
        "Tú decides quedarte un rato más junto al fuego.",
        "Tu decideixes quedar-te una estona més vora el foc.",
        "És l'hora que tanquen les portes.",
        # What the character does, a part to play, a thing to pick up: no call to choose.
        "You weigh it for a breath, decide, and go.",
        "You must act the part of a servant until the feast is over.",
        "Like every disciple before you, you must pick up the broom at dawn.",
        "Debes actuar como un criado hasta que acabe el banquete.",
        "Has d'actuar com un criat fins que s'acabi el banquet.",
        "The envoy smiles, certain of what you will choose, and pours the wine.",
    ],
)
def test_a_sentence_that_shows_is_left_alone(sentence):
    assert not tells(sentence)


@pytest.mark.parametrize(
    ("scene", "told"),
    [
        (SPY, SPY_TOLD),
        (FARM, FARM_TOLD),
        (MEMOIRS, MEMOIRS_TOLD),
        (COURTYARD, COURTYARD_TOLD),
        (BRIDGE, BRIDGE_TOLD),
    ],
)
def test_the_real_endings_are_left_out_and_the_scene_ends_on_what_it_showed(scene, told):
    assert shown(f"{scene} {told}") == scene
    assert shown(f"{scene}\n\n{told}\n") == scene


def test_a_scene_that_shows_comes_back_as_it_came():
    scene = f"{SPY}\n\n{COURTYARD} "

    assert shown(scene) is scene


def test_every_closing_sentence_that_tells_goes_and_one_before_them_stays():
    assert shown(f"{FARM} The choice is yours. What will you do?") == FARM
    # One that tells further up is the scene's own business: only its close is held.
    inside = f"You must decide whether to stay. {FARM}"
    assert shown(inside) is inside


def test_what_someone_in_the_scene_says_is_theirs_to_say():
    envoy = (
        'The commander plants his spear. "Will you answer the call, or must I draft every '
        'able-bodied youth from the village?"'
    )
    single = "Elena sets down her basket. 'You must decide whether to carry it or not.'"
    tagged = "She studies you. 'It is time to go,' she says, and turns for the door."
    # A speech of several sentences, closed after the scene's last one or never closed at all.
    long = 'He does not look up. "I have waited long enough. You must choose. Choose now."'
    unclosed = 'He does not look up. "I have waited long enough. You must choose.'
    curly = "Ella no levanta la vista. “He esperado bastante. Debes decidir ya."
    angled = "No aixeca la vista. «He esperat prou. Has de decidir ara."

    for scene in (envoy, single, tagged, long, unclosed, curly, angled):
        assert shown(scene) is scene


def test_an_apostrophe_is_no_quotation_mark():
    told = "It's time to see what's behind the miller's door."

    assert shown(f"{FARM} {told}") == FARM
    assert shown("L'aigua t'arriba als genolls. Ha arribat l'hora d'anar-se'n.") == (
        "L'aigua t'arriba als genolls."
    )


def test_the_last_sentence_a_scene_has_is_never_taken():
    assert shown(FARM_TOLD) is FARM_TOLD
    assert shown(f"{FARM_TOLD} What will you do?") == FARM_TOLD
    # The action is told in a part of its own (R1): the narration keeps a sentence of its own.
    assert shown(FARM_TOLD, after="You bar the door.") is FARM_TOLD


def test_a_speech_the_action_left_open_is_still_someones_speech():
    action = 'You lean in. "I have thought about it all night.'

    assert shown(f"The fire cracks. {COURTYARD_TOLD}", after=action) == (
        f"The fire cracks. {COURTYARD_TOLD}"
    )
    assert shown(f"The fire cracks. {COURTYARD_TOLD}", after="You lean in.") == "The fire cracks."


def test_a_pause_inside_a_sentence_does_not_end_it():
    scene = f"{FARM} And then... you must decide for yourself, the old man used to say."

    assert shown(scene) is scene


def streaming(scene: str, size: int) -> str:
    """What a player has read of a scene that came in pieces of `size`, while it is still being
    written."""
    sent = 0
    for upto in range(size, len(scene) + size, size):
        sent = max(sent, showable(scene[:upto]))
    return scene[:sent]


def streamed(scene: str, size: int) -> str:
    """What a player has read of it once its text is whole: what waited and stays goes out
    then (`TextEnded`, in `graph.turn.nodes`)."""
    read = streaming(scene, size)
    return scene[: max(len(read), len(shown(scene)))]


@pytest.mark.parametrize("size", [1, 7, 40, 500])
@pytest.mark.parametrize(
    ("scene", "told"),
    [
        (SPY, SPY_TOLD),
        (FARM, FARM_TOLD),
        (MEMOIRS, MEMOIRS_TOLD),
        (COURTYARD, COURTYARD_TOLD),
        (BRIDGE, BRIDGE_TOLD),
    ],
)
def test_a_scene_that_ends_on_the_players_move_never_shows_it_while_it_streams(scene, told, size):
    whole = f"The fire has burned low. {scene} {told}"

    assert streamed(whole, size) == f"The fire has burned low. {scene}"
    # Not a word of it at any point, wherever in the sentence the move is told.
    for upto in range(1, len(whole) + 1):
        assert showable(whole[:upto]) <= len(whole) - len(told) - 1


@pytest.mark.parametrize("size", [1, 7, 40])
def test_closing_sentences_that_all_tell_wait_together(size):
    assert streamed(f"{FARM} The choice is yours. What will you do?", size) == FARM


@pytest.mark.parametrize("size", [1, 7, 40])
def test_a_sentence_that_tells_goes_out_once_the_scene_goes_on(size):
    scene = (
        f"{FARM} {FARM_TOLD} Then the dog barks in the yard, and someone knocks three times at "
        "the door below, hard. You set the hoe down."
    )

    # While the last sentence is still being written, all before it has gone out.
    assert streaming(scene, size).rstrip() == scene.removesuffix(" You set the hoe down.")
    assert streamed(scene, size) == scene


def test_the_last_sentence_waits_for_the_scene_to_end():
    """Nothing says a sentence won't tell in a later clause until it is whole and the scene
    goes on, so the last one goes out when the text ends (`TextEnded`, in `graph.turn.nodes`),
    with whatever waited before it."""
    scene = f"{FARM} {FARM_TOLD} Then the dog barks."

    assert streaming(scene, 7) == FARM
    assert streamed(scene, 7) == scene and shown(scene) is scene


def test_the_scenes_first_sentence_never_waits():
    """S3: the first words reach the player as soon as they are written. A scene keeps its
    first sentence whatever it says, so there is nothing to wait for."""
    for upto in range(1, len(FARM_TOLD) + 1):
        assert showable(FARM_TOLD[:upto]) == len(FARM_TOLD[:upto].rstrip())
    # A space goes out with what follows it, so the text read never ends on one the scene
    # may not keep.
    assert showable(f"{FARM_TOLD} ") == len(FARM_TOLD)


def test_a_sentence_goes_out_once_it_is_whole_and_the_scene_goes_on():
    growing = "The first winter storm is only weeks away, and your firewood stack is low, as low as"

    # A sentence still being written waits, however long: its next clause may tell.
    assert showable(f"{MEMOIRS} {growing}") == len(MEMOIRS)
    assert showable(f"{MEMOIRS} {FARM} Then") == len(f"{MEMOIRS} {FARM}")
    # Speech goes out at once: it is never held back.
    assert showable('She turns. "You') == len('She turns. "You')
    assert showable("She turns. Then she says, 'You") == len("She turns. Then she says, 'You")
