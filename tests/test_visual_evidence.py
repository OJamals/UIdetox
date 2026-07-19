"""Behavior tests for safe, deterministic visual evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageCms

from uidetox.visual_evidence import (
    VISUAL_EVIDENCE_SCHEMA_VERSION,
    VisualEvidenceCase,
    VisualEvidenceError,
    VisualEvidenceRequest,
    VisualRegion,
    build_visual_evidence,
    inspect_visual_evidence,
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


def test_visual_evidence_rejects_url_sources_without_fetching(
    tmp_path: Path,
) -> None:
    request = _request(
        tmp_path,
        Path("https://example.com/before.png"),
        tmp_path / "after.png",
    )

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence(request)

    assert captured.value.code == "invalid_request"
    assert "local files only" in str(captured.value)


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

    manifest = build_visual_evidence(_request(tmp_path, before, after, threshold=30))

    assert manifest.comparisons[0].metrics.pixels_changed == 1


def test_threshold_is_constrained_before_saturating_channel_sum(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (1, 1), (0, 0, 0)).save(before)
    Image.new("RGB", (1, 1), (255, 1, 0)).save(after)

    with pytest.raises(VisualEvidenceError) as error:
        build_visual_evidence(_request(tmp_path, before, after, threshold=255))

    assert error.value.code == "invalid_request"
    assert "0 and 254" in str(error.value)


def test_alpha_is_composited_deterministically_before_comparison(
    tmp_path: Path,
) -> None:
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
        build_visual_evidence(_request(tmp_path, before, after, max_pixels=3))

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


def test_semantic_and_explicit_ignore_regions_are_measured_with_provenance(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (4, 2), (0, 0, 0)).save(before)
    Image.new("RGB", (4, 2), (31, 0, 0)).save(after)
    case = VisualEvidenceCase(
        case_id="desktop",
        before_path=before,
        after_path=after,
        semantic_regions=(
            VisualRegion(
                region_id="navigation",
                bounds=(0, 0, 2, 2),
                kind="semantic",
                provenance="runtime:nav",
                source_targets=("frontend/src/components/Sidebar.tsx",),
                intent_fields=("primary_job",),
                preserve_contracts=("Route remains reachable: /projects",),
            ),
            VisualRegion(
                region_id="content",
                bounds=(2, 0, 2, 2),
                kind="semantic",
                provenance="runtime:main",
            ),
        ),
        ignore_regions=(
            VisualRegion(
                region_id="animated-content",
                bounds=(2, 0, 2, 2),
                kind="ignore",
                reason="fixture animation",
                provenance="config:visual_evidence.ignore_regions[0]",
            ),
        ),
    )

    manifest = build_visual_evidence(
        VisualEvidenceRequest(
            comparisons=(case,),
            output_dir=tmp_path / "evidence",
            manifest_path=tmp_path / "evidence" / "manifest.json",
        )
    )

    comparison = manifest.comparisons[0]
    assert comparison.metrics.raw_pixels_changed == 8
    assert comparison.metrics.ignored_changed_pixels == 4
    assert comparison.metrics.pixels_changed == 4
    assert comparison.metrics.ignored_ratio == 0.5
    assert comparison.regions[0].region_id == "navigation"
    assert comparison.regions[0].pixels_changed == 4
    assert comparison.regions[0].changed_ratio == 1.0
    assert comparison.regions[0].source_targets == (
        "frontend/src/components/Sidebar.tsx",
    )
    assert comparison.regions[1].pixels_changed == 0
    assert comparison.ignored_regions[0].reason == "fixture animation"
    assert comparison.ignored_regions[0].provenance.startswith("config:")
    payload = json.loads((tmp_path / "evidence" / "manifest.json").read_text())
    assert payload["comparisons"][0]["ignored_regions"][0]["reason"] == (
        "fixture animation"
    )


def test_region_bounds_are_clipped_and_invalid_rectangles_rejected(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (3, 3), (0, 0, 0)).save(before)
    Image.new("RGB", (3, 3), (31, 0, 0)).save(after)
    clipped = VisualRegion(
        region_id="clipped",
        bounds=(-2.0, -1.0, 4.0, 3.0),
        kind="semantic",
        provenance="runtime:test",
    )

    manifest = build_visual_evidence(
        VisualEvidenceRequest(
            comparisons=(
                VisualEvidenceCase(
                    case_id="desktop",
                    before_path=before,
                    after_path=after,
                    semantic_regions=(clipped,),
                ),
            ),
            output_dir=tmp_path / "evidence",
        )
    )

    assert manifest.comparisons[0].regions[0].bounds == (0, 0, 2, 2)
    assert manifest.comparisons[0].regions[0].pixels_changed == 4

    with pytest.raises(VisualEvidenceError) as error:
        build_visual_evidence(
            VisualEvidenceRequest(
                comparisons=(
                    VisualEvidenceCase(
                        case_id="bad",
                        before_path=before,
                        after_path=after,
                        semantic_regions=(
                            VisualRegion(
                                region_id="bad",
                                bounds=(0, 0, 0, 1),
                                kind="semantic",
                                provenance="test",
                            ),
                        ),
                    ),
                ),
                output_dir=tmp_path / "bad-evidence",
            )
        )
    assert error.value.code == "invalid_region"


def test_manifest_freshness_detects_source_context_and_tampering(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    manifest_path = tmp_path / "evidence" / "manifest.json"
    Image.new("RGB", (2, 2), (0, 0, 0)).save(before)
    Image.new("RGB", (2, 2), (31, 0, 0)).save(after)
    build_visual_evidence(
        VisualEvidenceRequest(
            comparisons=(
                VisualEvidenceCase(
                    case_id="desktop",
                    before_path=before,
                    after_path=after,
                    semantic_regions=(
                        VisualRegion(
                            region_id="primary",
                            bounds=(0.0, 0.0, 2.0, 2.0),
                            kind="semantic",
                            provenance="runtime:desktop",
                            source_targets=("src/App.tsx",),
                            intent_fields=("primary_job",),
                            preserve_contracts=("Keep navigation",),
                        ),
                    ),
                ),
            ),
            output_dir=manifest_path.parent,
            manifest_path=manifest_path,
            context_sha256s={"frontend_map": "map-v1"},
        )
    )

    fresh = inspect_visual_evidence(
        manifest_path,
        required=True,
        expected_context_sha256s={"frontend_map": "map-v1"},
    )
    assert fresh.state == "fresh"
    assert fresh.ready is True
    assert fresh.comparisons == 1

    context_stale = inspect_visual_evidence(
        manifest_path,
        required=True,
        expected_context_sha256s={"frontend_map": "map-v2"},
    )
    assert context_stale.state == "stale"
    assert any("frontend_map" in reason for reason in context_stale.reasons)

    context_missing = inspect_visual_evidence(
        manifest_path,
        required=True,
        expected_context_sha256s={},
    )
    assert context_missing.state == "stale"
    assert any("no longer available" in reason for reason in context_missing.reasons)

    original_payload = json.loads(manifest_path.read_text())
    region_tampered_payload = json.loads(manifest_path.read_text())
    region_tampered_payload["comparisons"][0]["regions"][0]["provenance"] = (
        "runtime:tampered"
    )
    manifest_path.write_text(json.dumps(region_tampered_payload))
    region_tampered = inspect_visual_evidence(manifest_path, required=True)
    assert region_tampered.state == "blocked"
    assert any("request hash" in reason for reason in region_tampered.reasons)
    manifest_path.write_text(json.dumps(original_payload))

    Image.new("RGB", (2, 2), (32, 0, 0)).save(after)
    source_stale = inspect_visual_evidence(manifest_path, required=True)
    assert source_stale.state == "stale"
    assert any("source hash changed" in reason for reason in source_stale.reasons)

    payload = json.loads(manifest_path.read_text())
    payload["parameters"]["threshold"] = 12
    manifest_path.write_text(json.dumps(payload))
    tampered = inspect_visual_evidence(manifest_path, required=True)
    assert tampered.state == "blocked"
    assert any("request hash" in reason for reason in tampered.reasons)


def test_missing_visual_evidence_is_optional_or_a_failed_gate(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    optional = inspect_visual_evidence(path, required=False)
    required = inspect_visual_evidence(path, required=True)

    assert optional.state == required.state == "missing"
    assert optional.ready is True
    assert required.ready is False


def test_reviewer_artifacts_are_deterministic_and_localized(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (100, 60), "black").save(before)
    changed = Image.new("RGB", (100, 60), "black")
    changed.paste("white", (20, 10, 40, 30))
    changed.save(after)
    request = _request(
        tmp_path,
        before,
        after,
        reviewer_artifacts=True,
        crop_padding=5,
        expected_viewports=("desktop",),
        comparisons=(
            VisualEvidenceCase(
                case_id="desktop",
                before_path=before,
                after_path=after,
                viewport=(100, 60),
                semantic_regions=(
                    VisualRegion(
                        region_id="alpha-region",
                        bounds=(20, 10, 20, 20),
                        kind="semantic",
                        provenance="runtime:alpha",
                    ),
                    VisualRegion(
                        region_id="changed-panel",
                        bounds=(20, 10, 20, 20),
                        kind="semantic",
                        provenance="runtime:panel",
                    ),
                ),
            ),
        ),
    )

    first = build_visual_evidence(request)
    comparison_artifacts = {
        artifact.kind: artifact for artifact in first.comparisons[0].artifacts
    }
    assert set(comparison_artifacts) == {
        "amplified_diff",
        "heat_overlay",
        "changed_crop",
        "before_after_blend",
    }
    assert comparison_artifacts["heat_overlay"].status == "generated"
    assert comparison_artifacts["heat_overlay"].path is not None
    assert comparison_artifacts["changed_crop"].width == 30
    assert comparison_artifacts["changed_crop"].height == 30
    assert first.artifacts[0].kind == "contact_sheet"
    assert first.incomplete_viewports == ()
    first_hashes = {
        artifact.kind: artifact.sha256
        for artifact in (*first.comparisons[0].artifacts, *first.artifacts)
    }

    second = build_visual_evidence(request)
    second_hashes = {
        artifact.kind: artifact.sha256
        for artifact in (*second.comparisons[0].artifacts, *second.artifacts)
    }
    assert second_hashes == first_hashes
    status = inspect_visual_evidence(request.manifest_path, required=True)
    assert status.incomplete_viewports == ()
    assert any(
        artifact["kind"] == "contact_sheet" for artifact in status.reviewer_artifacts
    )
    assert [region["region_id"] for region in status.top_changed_regions[:2]] == [
        "alpha-region",
        "changed-panel",
    ]


def test_empty_diff_records_reviewer_artifact_omissions(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (20, 20), "black").save(before)
    Image.new("RGB", (20, 20), "white").save(after)
    request = _request(
        tmp_path,
        before,
        after,
        reviewer_artifacts=True,
    )
    changed_manifest = build_visual_evidence(request)
    changed_artifacts = {
        artifact.kind: artifact
        for artifact in changed_manifest.comparisons[0].artifacts
    }
    old_heat = changed_artifacts["heat_overlay"].path
    old_crop = changed_artifacts["changed_crop"].path
    assert old_heat is not None and old_heat.is_file()
    assert old_crop is not None and old_crop.is_file()
    Image.new("RGB", (20, 20), "black").save(after)

    manifest = build_visual_evidence(request)
    artifacts = {
        artifact.kind: artifact for artifact in manifest.comparisons[0].artifacts
    }

    assert artifacts["heat_overlay"].status == "omitted"
    assert artifacts["heat_overlay"].path is None
    assert artifacts["changed_crop"].status == "omitted"
    assert "no changed pixels" in artifacts["changed_crop"].reason
    assert artifacts["before_after_blend"].status == "generated"
    assert not old_heat.exists()
    assert not old_crop.exists()


def test_expected_viewports_and_srgb_fallback_warnings_are_explicit(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (10, 10), "black").save(before)
    Image.new("RGB", (10, 10), "white").save(after)

    manifest = build_visual_evidence(
        _request(
            tmp_path,
            before,
            after,
            color_policy="srgb",
            expected_viewports=("mobile", "desktop"),
        )
    )

    assert manifest.incomplete_viewports == ("mobile",)
    assert any("no embedded ICC profile" in item for item in manifest.warnings)
    assert manifest.comparisons[0].before.color_conversion == "assumed_srgb"


def test_invalid_icc_profile_warns_and_falls_back_to_native_pixels(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (10, 10), "black").save(
        before,
        icc_profile=b"not-a-valid-icc-profile",
    )
    Image.new("RGB", (10, 10), "white").save(after)

    manifest = build_visual_evidence(
        _request(tmp_path, before, after, color_policy="srgb")
    )

    assert any("invalid ICC profile" in item for item in manifest.warnings)
    assert manifest.comparisons[0].before.color_conversion == ("native_fallback")


def test_valid_icc_profile_converts_to_srgb_without_warning(
    tmp_path: Path,
) -> None:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (10, 10), (10, 20, 30)).save(
        before,
        icc_profile=profile,
    )
    Image.new("RGB", (10, 10), (30, 20, 10)).save(
        after,
        icc_profile=profile,
    )

    manifest = build_visual_evidence(
        _request(tmp_path, before, after, color_policy="srgb")
    )

    assert manifest.warnings == ()
    assert manifest.comparisons[0].before.color_conversion == "icc_to_srgb"
    assert manifest.comparisons[0].after.color_conversion == "icc_to_srgb"


def test_png_archival_controls_do_not_change_comparison_pixels(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (30, 30), "black").save(before)
    Image.new("RGB", (30, 30), "white").save(after)
    fast_dir = tmp_path / "fast"
    archive_dir = tmp_path / "archive"

    fast = build_visual_evidence(
        _request(
            tmp_path,
            before,
            after,
            output_dir=fast_dir,
            manifest_path=fast_dir / "manifest.json",
            png_compress_level=0,
        )
    )
    archival = build_visual_evidence(
        _request(
            tmp_path,
            before,
            after,
            output_dir=archive_dir,
            manifest_path=archive_dir / "manifest.json",
            png_compress_level=9,
            png_optimize=True,
        )
    )

    assert fast.comparisons[0].metrics == archival.comparisons[0].metrics
    fast_path = fast.comparisons[0].artifacts[0].path
    archive_path = archival.comparisons[0].artifacts[0].path
    assert fast_path is not None
    assert archive_path is not None
    with Image.open(fast_path) as fast_image, Image.open(archive_path) as archive_image:
        assert fast_image.tobytes() == archive_image.tobytes()
