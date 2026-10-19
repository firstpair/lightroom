from fractions import Fraction
import unittest

from scripts.preview_pipeline.monitor_geometry import (
    ORIENTATIONS, SWAPPED_ORIENTATIONS, standard_5k_fit,
)


class MonitorGeometryTests(unittest.TestCase):
    def test_independent_rational_target_and_bruteforce_minimal_edge(self):
        for width, height in ((37, 23), (7200, 4801), (8000, 4501),
                              (4501, 8000), (8191, 255), (3200, 3200)):
            for orientation in ORIENTATIONS:
                with self.subTest(size=(width, height), orientation=orientation):
                    swapped = orientation in SWAPPED_ORIENTATIONS
                    pw, ph = (height, width) if swapped else (width, height)
                    ratio = min(Fraction(1), Fraction(5120, pw), Fraction(2880, ph))
                    def ceil(value):
                        return -(-value.numerator // value.denominator)
                    target = (ceil(pw * ratio), ceil(ph * ratio))
                    def dimensions(edge):
                        if width >= height:
                            encoded = (edge, edge * height // width)
                        else:
                            encoded = (edge * width // height, edge)
                        return encoded[::-1] if swapped else encoded
                    # Search independently instead of using the implementation's
                    # inversion formula or its private helpers.
                    minimal = next(edge for edge in range(1, max(width, height) + 1)
                                   if all(a >= b for a, b in zip(dimensions(edge), target)))
                    result = standard_5k_fit(width, height, orientation)
                    self.assertEqual(result['preferredSize'], minimal)
                    self.assertEqual((result['requiredPresentedWidth'],
                                      result['requiredPresentedHeight']), target)
                    self.assertLessEqual(result['expectedEncodedWidth'], width)
                    self.assertLessEqual(result['expectedEncodedHeight'], height)

    def test_small_and_thin_inputs_never_upscale_or_round_to_zero(self):
        for size in ((1, 1), (65535, 1), (1, 65535), (1600, 900)):
            for orientation in ORIENTATIONS:
                result = standard_5k_fit(*size, orientation)
                self.assertEqual(result['preferredSize'], max(size))
                self.assertEqual((result['expectedEncodedWidth'],
                                  result['expectedEncodedHeight']), size)

    def test_sentinels_and_unqualified_dimensions_refuse(self):
        for bad in ('uncropped', None, True, 1.0, 0, -1, 65536):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                standard_5k_fit(bad, 1000, 'AB')
        with self.assertRaises(ValueError):
            standard_5k_fit(16000, 16000, 'AB')
        with self.assertRaises(ValueError):
            standard_5k_fit(1000, 1000, 'unknown')

    def test_result_is_intent_not_native_or_publication_authority(self):
        result = standard_5k_fit(4800, 3200, 'AB')
        self.assertTrue(result['actualReturnedGeometryRequired'])
        for key in ('nativePyramidSelectionSimulated', 'productionPublicationReleased',
                    'fullRunReleased', 'actualLibraryViewportObserved'):
            self.assertFalse(result[key])
        result['preferredSize'] = 1
        self.assertNotEqual(standard_5k_fit(4800, 3200, 'AB')['preferredSize'], 1)
