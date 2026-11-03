from unittest.mock import Mock, call

import pytest

from thermal_dataset_download import (
    build_request,
    build_target,
    download_regions,
    get_download_regions,
)


class SampleBounds:
    MAINLAND = (-11.0, 34.5, 46.0, 71.5)
    ICELAND = (-26.0, 62.0, -12.0, 67.8)
    SVALBARD = (9.5, 73.9, 34.5, 81.0)

    REGIONS = (MAINLAND, ICELAND, SVALBARD)
    ENVELOPE = (-26.0, 34.5, 46.0, 81.0)

def test_build_request():
    
    assert build_request(
        SampleBounds.MAINLAND,
        ["2024", "2025"],
    ) == {
        "variable": [
            "universal_thermal_climate_index_yearly_statistics"
        ],
        "version": "1_1",
        "product_type": "consolidated_dataset",
        "year": ["2024", "2025"],
        "area": [71.5, -11.0, 34.5, 46.0],
    }


def test_build_target(tmp_path):
    
    assert build_target(tmp_path, "CANARY_WEST", 2016, 2025) == (
        tmp_path / "utci_canary_west_2016_2025.zip"
    )


def test_download_regions(tmp_path):
    
    client = Mock()
    log = Mock()
    output_dir = tmp_path / "downloads"
    regions = [
        ("MAINLAND", SampleBounds.MAINLAND),
        ("SVALBARD", SampleBounds.SVALBARD),
    ]

    targets = download_regions(
        client=client,
        dataset="derived-utci-historical",
        regions=regions,
        output_dir=output_dir,
        start_year=2024,
        end_year=2025,
        log=log,
    )

    expected_targets = [
        output_dir / "utci_mainland_2024_2025.zip",
        output_dir / "utci_svalbard_2024_2025.zip",
    ]

    assert output_dir.is_dir()
    assert targets == expected_targets
    assert client.retrieve.call_args_list == [
        call(
            "derived-utci-historical",
            build_request(bounds, ["2024", "2025"]),
            str(target),
        )
        for (_, bounds), target in zip(regions, expected_targets)
    ]

    assert log.call_args_list == [
        call(
            f"Downloading MAINLAND (1/2): "
            f"bounds={SampleBounds.MAINLAND} -> {expected_targets[0]}",
            flush=True,
        ),
        call(f"Downloaded MAINLAND -> {expected_targets[0]}", flush=True),
        call(
            f"Downloading SVALBARD (2/2): "
            f"bounds={SampleBounds.SVALBARD} -> {expected_targets[1]}",
            flush=True,
        ),
        call(f"Downloaded SVALBARD -> {expected_targets[1]}", flush=True),
    ]


def test_download_failure_propagates_without_logging_success(tmp_path):
    
    client = Mock()
    client.retrieve.side_effect = RuntimeError("Download failed")
    log = Mock()

    with pytest.raises(RuntimeError, match="Download failed"):
        download_regions(
            client=client,
            dataset="derived-utci-historical",
            regions=[("MAINLAND", SampleBounds.MAINLAND)],
            output_dir=tmp_path,
            start_year=2024,
            end_year=2025,
            log=log,
        )

    client.retrieve.assert_called_once()
    log.assert_called_once()  # Only the "Downloading" message.