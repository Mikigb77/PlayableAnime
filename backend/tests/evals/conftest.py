"""Fakes for the evals' live mode: every live scenario can run in CI on the offline model and a
judge that passes whatever it is shown, so a broken live script shows up before a nightly run
spends anything on it."""

import re

import pytest

from evals.runner import Models
from graph.llm import FakeBackend, Node, Reply
from graph.llm.fake import offline_reply
from graph.llm.types import Request

CRITERION = re.compile(r"^([MN]\d+): ", re.MULTILINE)


def passing_judge(request: Request) -> Reply:
    """The judge's answer: pass on every criterion the prompt lists."""
    if request.node is not Node.JUDGE:
        return offline_reply(request)
    text = "\n".join(m.text for m in request.prompt.messages)
    answers = [
        {"id": cid, "verdict": "pass", "quote": "", "reason": "Fake judge."}
        for cid in CRITERION.findall(text)
    ]
    return Reply(json={"answers": answers})


@pytest.fixture
def offline_models() -> Models:
    return Models(
        backend=FakeBackend(default=offline_reply, keep_requests=False),
        judge_backend=FakeBackend(default=passing_judge, keep_requests=False),
    )
