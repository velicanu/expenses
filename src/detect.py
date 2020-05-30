import json
import os


def _get_card_definitions(dir_):
    return {
        i.replace(".json", ""): json.load(open(os.path.join(dir_, i)))
        for i in next(os.walk(dir_))[2]
        if i.endswith(".json")
    }


script_dir = os.path.dirname(os.path.realpath(__file__))

CARD_DEFINITIONS = _get_card_definitions(os.path.join(script_dir, "card_definitions"))


def get_card(record):
    """Looks at a json record and returns the matching card + card_definition"""
    for card, card_def in CARD_DEFINITIONS.items():
        if all(key in record for key in card_def):
            return card, card_def
    return None, None
