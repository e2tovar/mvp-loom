from eval.attributes.metrics import attribute_metrics


def test_perfect_match_f1_is_one():
    gold = [{"character": "ana", "key": "eye_color", "value_norm": "green", "class": "static"},
            {"character": "ana", "key": "eye_color", "value_norm": "blue", "class": "static"}]
    pred = [{"character_id": "cid_ana", "key": "eye_color", "value_norm": "green", "attr_class": "static"},
            {"character_id": "cid_ana", "key": "eye_color", "value_norm": "blue", "attr_class": "static"}]
    m = attribute_metrics(gold, pred, {"ana": "cid_ana"})
    assert m["triple_detection"]["all"]["f1"] == 1.0
    assert m["triple_detection"]["static"]["recall"] == 1.0


def test_missing_one_value_lowers_recall():
    gold = [{"character": "ana", "key": "eye_color", "value_norm": "green", "class": "static"},
            {"character": "ana", "key": "eye_color", "value_norm": "blue", "class": "static"}]
    pred = [{"character_id": "cid_ana", "key": "eye_color", "value_norm": "green", "attr_class": "static"}]
    m = attribute_metrics(gold, pred, {"ana": "cid_ana"})
    assert m["triple_detection"]["all"]["recall"] == 0.5
    assert m["triple_detection"]["all"]["precision"] == 1.0


def test_stateful_bucket_split():
    gold = [{"character": "d", "key": "status", "value_norm": "dead", "class": "stateful"}]
    pred = [{"character_id": "cid_d", "key": "status", "value_norm": "dead", "attr_class": "stateful"}]
    m = attribute_metrics(gold, pred, {"d": "cid_d"})
    assert m["triple_detection"]["stateful"]["f1"] == 1.0
    # bucket sin gold NI pred = 1.0 trivial (misma convención que M2 relation_metrics);
    # el gate usa el bucket "all", no los splits por clase.
    assert m["triple_detection"]["static"]["f1"] == 1.0
