from __future__ import annotations

import unittest

from apple_notes_recovery.common import normalize


class NormalizeTests(unittest.TestCase):
    def test_normalize_collapses_whitespace_and_punctuation_variants(self) -> None:
        self.assertEqual(normalize("  Foo　Bar "), "foobar")
        self.assertEqual(normalize("管理/商业散记（出书"), "管理/商业散记(出书")
        self.assertEqual(normalize("A，B：C"), "a,b:c")


if __name__ == "__main__":
    unittest.main()
