"""Approved base offer. No payment collection or unapproved usage promise."""

import json
from importlib.resources import files


def base_membership() -> dict:
    return json.loads(files("persy").joinpath("membership.json").read_text())
