from product_agent.services.text_cleaning import clean_internal_context_text


def test_clean_internal_context_text_hides_opaque_paper_ids():
    text = (
        "Zero-shot Video Moment Retrieval via Off-the-shelf Multimodal Large "
        "Language Models (facd46944e9506d6d5252bac80fd6e28dce7b183)"
    )

    assert clean_internal_context_text(text) == (
        "Zero-shot Video Moment Retrieval via Off-the-shelf Multimodal Large Language Models"
    )


def test_clean_internal_context_text_drops_internal_relevance_signals():
    assert clean_internal_context_text("focus: multimodal: title: multimodal") == ""
