"""Behavior tests for safe, deterministic visual evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from uidetox.visual_evidence import (
    VISUAL_EVIDENCE_SCHEMA_VERSION,
    VisualEvidenceCase,
    VisualEvidenceError,
    VisualEvidenceRequest,
    build_visual_evidence,
)


def _request(
    tmp_path: Path,
    before: Path,
    after: Path,
    **overrides: object,
) -> VisualEvidenceRequest:
    values: dict[str, object] = {
        "comparisons": (
            VisualEvidenceCase(
                case_id="desktop",
                before_path=before,
                after_path=after,
                viewport=(1280, 800),
            ),
        ),
        "output_dir": tmp_path / "evidence",
        "manifest_path": tmp_path / "evidence" / "manifest.json",
    }
    values.update(overrides)
    return VisualEvidenceRequest(**values)  # type: ignore[arg-type]


def test_build_visual_evidence_emits_versioned_manifest_and_exact_metrics(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (2, 1), (0, 0, 0)).save(before)
    changed = Image.new("RGB", (2, 1), (0, 0, 0))
    changed.putpixel((1, 0), (31, 0, 0))
    changed.save(after)

    manifest = build_visual_evidence(_request(tmp_path, before, after))

    assert manifest.schema_version == VISUAL_EVIDENCE_SCHEMA_VERSION
    assert manifest.status == "complete"
    assert len(manifest.comparisons) == 1
    comparison = manifest.comparisons[0]
    assert comparison.case_id == "desktop"
    assert comparison.metrics.pixels_changed == 1
    assert comparison.metrics.total_pixels == 2
    assert comparison.metrics.change_percentage == 50.0
    assert comparison.metrics.changed_ratio == 0.5
    assert comparison.metrics.changed_bounds == (1, 0, 2, 1)
    assert comparison.metrics.changed_bounds_ratio == 0.5
    assert comparison.metrics.exact_match is False
    assert comparison.metrics.extrema == ((0, 31), (0, 0), (0, 0))
    assert comparison.metrics.rms_channel_delta[0] > 0
    assert comparison.metrics.stddev_channel_delta[0] > 0
    assert comparison.before.width == comparison.after.width == 2
    assert comparison.before.height == comparison.after.height == 1
    assert comparison.before.sha256 != comparison.after.sha256
    assert comparison.before.normalized_sha256 != comparison.after.normalized_sha256
    assert comparison.artifacts[0].kind == "amplified_diff"
    assert comparison.artifacts[0].path.is_file()
    assert comparison.artifacts[0].sha256
    assert manifest.freshness.request_sha256
    assert manifest.parameters["algorithm"] == "rgb-sum-v1"
    assert manifest.parameters["pillow_version"]

    payload = json.loads((tmp_path / "evidence" / "manifest.json").read_text())
    assert payload["schema_version"] == VISUAL_EVIDENCE_SCHEMA_VERSION
    assert payload["comparisons"][0]["metrics"]["pixels_changed"] == 1
    assert payload["comparisons"][0]["artifacts"][0]["kind"] == "amplified_diff"
    assert not list((tmp_path / "evidence").glob(".*.tmp"))


def test_threshold_boundary_is_strictly_greater_than_tolerance(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (2, 1), (0, 0, 0)).save(before)
    changed = Image.new("RGB", (2, 1), (0, 0, 0))
    changed.putpixel((0, 0), (30, 0, 0))
    changed.putpixel((1, 0), (31, 0, 0))
    changed.save(after)

    manifest = build_visual_evidence(
        _request(tmp_path, before, after, threshold=30)
    )

    assert manifest.comparisons[0].metrics.pixels_changed == 1


def test_threshold_is_constrained_before_saturating_channel_sum(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (1, 1), (0, 0, 0)).save(before)
    Image.new("RGB", (1, 1), (255, 1, 0)).save(after)

    with pytest.raises(VisualEvidenceError) as error:
        build_visual_evidence(
            _request(tmp_path, before, after, threshold=255)
        )

    assert error.value.code == "invalid_request"
    assert "0 and 254" in str(error.value)


def test_alpha_is_composited_deterministically_before_comparison(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGBA", (1, 1), (255, 0, 0, 0)).save(before)
    Image.new("RGBA", (1, 1), (0, 0, 255, 0)).save(after)

    manifest = build_visual_evidence(_request(tmp_path, before, after))

    comparison = manifest.comparisons[0]
    assert comparison.before.source_mode == "RGBA"
    assert comparison.before.normalized_mode == "RGB"
    assert comparison.metrics.pixels_changed == 0
    assert comparison.metrics.exact_match is True


def test_malformed_alpha_background_is_a_structured_request_error(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGBA", (1, 1), (255, 0, 0, 0)).save(before)
    Image.new("RGBA", (1, 1), (255, 0, 0, 0)).save(after)

    with pytest.raises(VisualEvidenceError) as error:
        build_visual_evidence(
            _request(
                tmp_path,
                before,
                after,
                alpha_background=(255,),  # type: ignore[arg-type]
            )
        )

    assert error.value.code == "invalid_request"
    assert "exactly three integer" in str(error.value)


@pytest.mark.parametrize(
    ("arrange", "code"),
    [
        (
            lambda path: path.write_bytes(b"not an image"),
            "invalid_image",
        ),
        (
            lambda path: Image.new("RGB", (2, 2)).save(path, format="JPEG"),
            "unsupported_format",
        ),
    ],
)
def test_invalid_or_wrong_format_inputs_are_rejected(
    tmp_path: Path,
    arrange: object,
    code: str,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (1, 1)).save(after)
    arrange(before)  # type: ignore[operator]

    with pytest.raises(VisualEvidenceError) as error:
        build_visual_evidence(_request(tmp_path, before, after))

    assert error.value.code == code


def test_pixel_limit_is_checked_before_full_decode(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (2, 2)).save(before)
    Image.new("RGB", (2, 2)).save(after)

    with pytest.raises(VisualEvidenceError) as error:
        build_visual_evidence(
            _request(tmp_path, before, after, max_pixels=3)
        )

    assert error.value.code == "image_too_large"


def test_multiframe_png_is_rejected(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    frames = [
        Image.new("RGBA", (2, 2), (255, 0, 0, 255)),
        Image.new("RGBA", (2, 2), (0, 0, 255, 255)),
    ]
    frames[0].save(
        before,
        format="PNG",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(after)

    with pytest.raises(VisualEvidenceError) as error:
        build_visual_evidence(_request(tmp_path, before, after))

    assert error.value.code == "animated_image"


def test_dimension_mismatch_is_not_resized(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (2, 1)).save(before)
    Image.new("RGB", (1, 2)).save(after)

    with pytest.raises(VisualEvidenceError) as error:
        build_visual_evidence(_request(tmp_path, before, after))

    assert error.value.code == "dimension_mismatch"
    assert "2x1" in str(error.value)
    assert "1x2" in str(error.value)


def test_multiple_viewports_persist_one_atomic_manifest(tmp_path: Path) -> None:
    cases: list[VisualEvidenceCase] = []
    for name, size in (("mobile", (3, 4)), ("desktop", (5, 3))):
        before = tmp_path / f"before_{name}.png"
        after = tmp_path / f"after_{name}.png"
        Image.new("RGB", size, (0, 0, 0)).save(before)
        Image.new("RGB", size, (1, 0, 0)).save(after)
        cases.append(
            VisualEvidenceCase(
                case_id=name,
                before_path=before,
                after_path=after,
                viewport=size,
            )
        )

    manifest = build_visual_evidence(
        VisualEvidenceRequest(
            comparisons=tuple(cases),
            output_dir=tmp_path / "evidence",
            manifest_path=tmp_path / "evidence" / "manifest.json",
        )
    )

    assert [item.case_id for item in manifest.comparisons] == [
        "mobile",
        "desktop",
    ]
    assert (tmp_path / "evidence" / "manifest.json").is_file()
    assert len(list((tmp_path / "evidence").glob("diff_*.png"))) == 2
