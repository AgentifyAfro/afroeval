from console.app import _divergence_item_count


def test_counts_items_with_flagged_multilingual_row():
    metrics_by_resp = {
        "r1": [{"metric_name": "multilingual_similarity", "extra": {"judge_divergence": True}},
               {"metric_name": "semantic_similarity", "extra": {}}],
        "r2": [{"metric_name": "multilingual_similarity", "extra": {"judge_divergence": False}}],
    }
    assert _divergence_item_count(metrics_by_resp) == 1
