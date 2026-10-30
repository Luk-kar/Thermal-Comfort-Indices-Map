import numpy as np
import pytest

from utci_map.source.products.maps.palette import palette_rgb


@pytest.mark.parametrize("colors", [
    ["#000000", "#ffffff"], ("#000000", "#ffffff"),
])
def test_continuous_palette_contains_expected_colours(colors):

    result = palette_rgb(colors)

    assert result.shape == (255, 3)
    assert result.dtype == np.uint8
    np.testing.assert_array_equal(result[0], [0, 0, 0])
    np.testing.assert_array_equal(result[127], [128, 128, 128])
    np.testing.assert_array_equal(result[-1], [255, 255, 255])
    assert np.all(np.diff(result.astype(int), axis=0) >= 0)


def test_discrete_palette_uses_only_supplied_colours():
    """
    Check that a discrete palette preserves the supplied colour steps.

    Use black and white as the input colours and verify that every palette
    entry is one of those colours, with no intermediate shades of grey.
    Expect the first 127 entries to be black and the remaining 128 white.
    """

    result = palette_rgb(["#000000", "#ffffff"], discrete_colors=True)

    np.testing.assert_array_equal(result[:127], np.zeros((127, 3), dtype=np.uint8))
    np.testing.assert_array_equal(result[127:], np.full((128, 3), 255, dtype=np.uint8))


@pytest.mark.parametrize("discrete", [False, True])
def test_single_colour_palette_is_uniform(discrete):

    result = palette_rgb(["#123456"], discrete_colors=discrete)
    np.testing.assert_array_equal(result, np.tile([18, 52, 86], (255, 1)))


@pytest.mark.parametrize("colour", ["red", "#fff", "ffffff", "#gg0000"])
def test_invalid_colour_raises_value_error(colour):

    with pytest.raises(ValueError):
        palette_rgb([colour])
