from hinga.embeddings import cosine, local_embed
from hinga.retrieval import OVERLAP_THRESHOLD, rank
from hinga.textutil import detect_themes


class _Item:
    def __init__(self, item_id, text):
        import json

        self.id = item_id
        self.embedding_json = json.dumps(local_embed(text))
        self.embedding_space = "local"


def test_related_notes_outrank_an_unrelated_one():
    desk = local_embed("the train stalled and I ate lunch at my desk")
    again = local_embed("the train was late so lunch was at the desk again")
    baby = local_embed("the baby woke twice and I texted my sister")
    assert cosine(desk, again) > cosine(desk, baby)
    assert cosine(desk, again) >= OVERLAP_THRESHOLD


def test_sleep_words_share_a_theme_even_when_the_word_differs():
    awake = local_embed("awake at 2am thinking about the review")
    slept = local_embed("I slept badly and left the lights on")
    park = local_embed("lunch in the park with a friend")
    assert cosine(awake, slept) > cosine(awake, park)
    assert "sleep" in detect_themes("I was awake until two")


def test_one_shared_everyday_word_is_not_enough_to_cite():
    sample = local_embed(
        "The train stalled again and I ate at my desk. My shoulders stayed up until I walked the long way home."
    )
    baby = local_embed("A small win: the baby napped in the crib and I ate sitting down.")
    train = local_embed(
        "I slept badly, then the train stalled outside the station and I ate lunch at my desk."
    )
    assert cosine(sample, train) >= OVERLAP_THRESHOLD
    assert cosine(sample, baby) < OVERLAP_THRESHOLD
    awake = (
        "Awake at 2am thinking about the review. "
        "I got up for water and still took a while to sleep."
    )
    assert cosine(local_embed("baby"), local_embed(awake)) < OVERLAP_THRESHOLD


def test_rank_drops_weak_matches():
    items = [
        _Item("desk", "lunch happened at the desk after the train stalled"),
        _Item("baby", "the baby woke twice and I counted breaths"),
    ]
    ranked = rank(items, local_embed("ate lunch at my desk because the train stalled"))
    assert ranked
    assert ranked[0].item_id == "desk"
    assert all(item.item_id != "baby" for item in ranked)
