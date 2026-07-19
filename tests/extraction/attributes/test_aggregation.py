# tests/extraction/attributes/test_aggregation.py
from backend.extraction.attributes.aggregation import aggregate_character_attributes


def _ev(cid, key, val, eid, conf=0.8, order=0):
    return {"character_id": cid, "key": key, "value_norm": val,
            "evidence_id": eid, "confidence": conf, "narrative_order": order}


def test_two_distinct_values_are_NOT_collapsed():
    # ojos azules en escena 0, verdes en escena 5: DEBEN sobrevivir ambos.
    evs = [_ev("ana", "eye_color", "blue", "s0:ae:x", order=0),
           _ev("ana", "eye_color", "green", "s5:ae:x", order=5)]
    nodes = aggregate_character_attributes(evs)
    values = {(n["key"], n["value_norm"]) for n in nodes}
    assert values == {("eye_color", "blue"), ("eye_color", "green")}


def test_same_value_repeated_collapses_to_one_node_with_count():
    evs = [_ev("ana", "hair", "blonde", "s0:ae:h", conf=0.7, order=0),
           _ev("ana", "hair", "blonde", "s3:ae:h", conf=0.9, order=3)]
    nodes = aggregate_character_attributes(evs)
    assert len(nodes) == 1
    n = nodes[0]
    assert n["evidence_count"] == 2
    assert n["confidence"] == 0.9                 # máxima del grupo
    assert n["first_evidence_id"] == "s0:ae:h"    # primera en orden narrativo


def test_attr_class_is_stamped():
    evs = [_ev("ana", "status", "dead", "s9:ae:s")]
    assert aggregate_character_attributes(evs)[0]["attr_class"] == "stateful"


def test_empty_input():
    assert aggregate_character_attributes([]) == []
