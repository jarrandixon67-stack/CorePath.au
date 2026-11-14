"""Canonical founder-agreed principles, shared with the older service prompts."""

import json
from importlib.resources import files


def principles() -> dict:
    return json.loads(files("corepath_bots").joinpath("principles.json").read_text())


def render_principles() -> str:
    policy = principles()
    return policy["version"] + "\n" + "\n\n".join(
        item["id"].upper() + "\n" + item["instruction"] for item in policy["principles"])
