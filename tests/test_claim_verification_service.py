from __future__ import annotations

from product_agent.services.claim_verification_service import (
    extract_full_text_claim_candidates,
    summarize_full_text_verification,
    verify_claim_against_full_text,
)


def test_full_text_claim_verification_returns_page_and_section_evidence() -> None:
    full_text = """
[Page 1]
Abstract
This paper studies robot vision under missing-modality conditions.

[Page 2]
Method
We propose a lightweight multimodal fusion architecture that aligns camera and language features for robot vision.

[Page 3]
Experiments
Experiments evaluate missing-modality robustness and improve retrieval stability.
"""

    result = verify_claim_against_full_text(
        claim_type="method",
        claim="The paper proposes a lightweight multimodal fusion architecture for robot vision.",
        full_text=full_text,
        title="Lightweight Multimodal Fusion for Robot Vision",
        category="Robot Vision Fusion",
    )

    assert result is not None
    assert result.source_level == "full_text"
    assert result.status == "verified"
    assert "Method" in result.section
    assert "p.2" in result.section
    assert "aligns camera and language features" in result.evidence
    assert "全文片段级核查" in result.caveat


def test_full_text_summary_reports_pages_and_sections() -> None:
    summary = summarize_full_text_verification(
        """
[Page 1]
Abstract
This paper studies retrieval.
[Page 2]
Conclusion
Future work studies robustness.
"""
    )

    assert "2 页" in summary
    assert "abstract" in summary
    assert "conclusion" in summary


def test_extract_full_text_claim_candidates_uses_section_specific_passages() -> None:
    full_text = """
[Page 1]
Abstract
This paper introduces a multimodal retrieval framework for robot vision.

[Page 2]
Method
We propose a compact fusion architecture that aligns visual and language features before retrieval.

[Page 3]
Experiments
Experiments show that the architecture improves retrieval robustness under missing modalities.

[Page 4]
Limitations
The current method is limited by synthetic missing-modality settings and needs real robot validation.

[Page 5]
References
[1] A noisy citation entry should not be treated as a paper claim.
"""

    candidates = extract_full_text_claim_candidates(full_text)
    by_type = {candidate.claim_type: candidate for candidate in candidates}

    assert "method_claim" in by_type
    assert "evaluation_claim" in by_type
    assert "limitation_claim" in by_type
    assert by_type["method_claim"].page == 2
    assert "aligns visual and language features" in by_type["method_claim"].claim
    assert by_type["evaluation_claim"].page == 3
    assert by_type["limitation_claim"].page == 4
    assert all("citation entry" not in candidate.claim for candidate in candidates)
