"""Drafting a world and a character from a premise (G1, G2, S1, WS12).

    from graph.drafting import chain, view

    draft = await chain.create(llm, premise, rating="mature", premise_id="naples-vendetta")
    draft = await chain.revise(llm, draft, "world", "add hidden vampires")
    state = draft.state()                     # the opening WorldState, hidden parts included
    view.world_lines(state), view.character_lines(state)   # what the player sees

The model proposes a `schema.DraftProposal`; `assemble` decides the world state in code;
`view` writes what the player sees from its public parts only; `catalog` holds the starter
premises and the rules each genre keeps. Nothing here imports Django (B4).
"""
