from pathlib import Path


def test_bundled_provider_assets_match_canonical_sources(
    packaged_asset_pairs: tuple[tuple[Path, Path], ...],
) -> None:
    assert packaged_asset_pairs
    for canonical, bundled in packaged_asset_pairs:
        assert bundled.read_bytes() == canonical.read_bytes(), canonical
