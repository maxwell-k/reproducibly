# build_wheels_test.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import unittest

from build_wheels import override


class TestOverride(unittest.TestCase):
    def test_overridden_with_specific_version(self):
        result = override({"example"}, {"example==1.2.3"})
        self.assertEqual(result, {"example==1.2.3"})

    def test_unchanged(self):
        result = override({"example"}, {"other==1.2.3"})
        self.assertEqual(result, {"example"})


if __name__ == "__main__":
    unittest.main()
