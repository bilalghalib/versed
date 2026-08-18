import pytest

from versed.alignment.embeddings import _context_waypoints, _position_cost
from versed.alignment.profiles import AlignmentCapabilities, recommend_alignment_profile


def test_context_waypoints_are_mutual_monotone_and_create_a_smooth_prior():
    numpy = pytest.importorskip("numpy")
    matrix = numpy.array(
        [
            [0.91, 0.20, 0.10],
            [0.10, 0.93, 0.20],
            [0.20, 0.10, 0.92],
        ]
    )

    waypoints = _context_waypoints(matrix, threshold=0.62, margin=0.025)

    assert waypoints == ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0))
    assert _position_cost(1.5, 1.5, waypoints) == 0
    assert _position_cost(1.5, 3.0, waypoints) == 1.5


def test_hardware_fit_alone_does_not_recommend_an_uncalibrated_judge():
    capabilities = AlignmentCapabilities(
        system="Darwin",
        machine="arm64",
        memory_gib=16,
        semantic_runtime_installed=True,
        ollama_available=True,
        ollama_models=("gemma2:2b",),
    )

    recommendation = recommend_alignment_profile(capabilities)

    assert recommendation.profile == "thorough"
    assert recommendation.ollama_judge is None
    assert "without calibration gold" in recommendation.notes[-1]
