import json
import os

script_dir = os.path.dirname(os.path.realpath(__file__))

CARD_DEFINITIONS = json.load(open(os.path.join(script_dir, "card_definitions.json")))


def get_card(record):
    """Looks at a json record and returns the matching card + card_definition"""
    for card, card_def in CARD_DEFINITIONS.items():
        if all(key in record for key in card_def):
            return card, card_def
    return None, None
