from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bible_tui.paths import BUNDLED_BIBLES_DIR
from bible_tui.store import BibleStore
from bible_tui.versions import VersionError, discover_versions, find_version, inspect_database

from tests.helpers import ASV_PATH, KJV_PATH, make_bible


class InspectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_reads_metadata(self) -> None:
        version = inspect_database(make_bible(self.tmp / "x.sqlite", "WEB", "World English Bible"))
        self.assertEqual((version.abbreviation, version.name), ("WEB", "World English Bible"))
        self.assertEqual(version.label, "WEB · World English Bible")

    def test_falls_back_to_filename_without_metadata(self) -> None:
        version = inspect_database(make_bible(self.tmp / "bible_web.sqlite", None, None))
        self.assertEqual((version.abbreviation, version.name, version.label), ("WEB", "WEB", "WEB"))

    def test_rejects_unusable_files(self) -> None:
        junk = self.tmp / "junk.sqlite"
        junk.write_text("not a database", encoding="utf-8")
        with self.assertRaises(VersionError):
            inspect_database(junk)
        empty = make_bible(self.tmp / "empty.sqlite", verses={})
        with self.assertRaisesRegex(VersionError, "no verses"):
            inspect_database(empty)

    def test_does_not_modify_the_database(self) -> None:
        path = make_bible(self.tmp / "x.sqlite")
        before = path.stat().st_mtime_ns
        inspect_database(path)
        BibleStore(path).close()
        self.assertEqual(path.stat().st_mtime_ns, before)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["x.sqlite"])


class DiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_bundled_versions(self) -> None:
        discovery = discover_versions([BUNDLED_BIBLES_DIR])
        self.assertEqual([v.abbreviation for v in discovery.versions], ["ASV", "KJV"])
        self.assertEqual(discovery.skipped, ())

    def test_earlier_directory_shadows_later_one(self) -> None:
        user_dir = self.tmp / "user"
        mine = make_bible(user_dir / "my-kjv.sqlite", "KJV", "My KJV")
        make_bible(user_dir / "web.sqlite", "WEB", "World English Bible")
        (user_dir / "notes.txt").write_text("ignored", encoding="utf-8")
        discovery = discover_versions([user_dir, self.tmp / "missing", BUNDLED_BIBLES_DIR])
        self.assertEqual([v.abbreviation for v in discovery.versions], ["ASV", "KJV", "WEB"])
        self.assertEqual(find_version(discovery.versions, "kjv").path, mine)
        self.assertEqual([path for path, _ in discovery.skipped], [KJV_PATH])

    def test_broken_files_are_reported_not_fatal(self) -> None:
        (self.tmp / "broken.sqlite").write_text("nope", encoding="utf-8")
        discovery = discover_versions([self.tmp, BUNDLED_BIBLES_DIR])
        self.assertEqual(len(discovery.versions), 2)
        self.assertEqual(discovery.skipped[0][0].name, "broken.sqlite")

    def test_find_version_by_name_or_filename(self) -> None:
        versions = discover_versions([BUNDLED_BIBLES_DIR]).versions
        self.assertEqual(find_version(versions, "bible_asv").path, ASV_PATH)
        self.assertEqual(find_version(versions, "bible_asv.sqlite").path, ASV_PATH)
        self.assertIsNone(find_version(versions, "XYZ"))


class BundledDataTest(unittest.TestCase):
    def test_bundled_versions_are_complete(self) -> None:
        for path, verse_count in ((KJV_PATH, 31102), (ASV_PATH, 31086)):
            with self.subTest(path=path.name):
                store = BibleStore(path)
                try:
                    books = store.books(False)
                    self.assertEqual(len(books), 66)
                    self.assertEqual(sum(len(store.chapters(book.id)) for book in books), 1189)
                    self.assertEqual(len(store.all_verses()), verse_count)
                finally:
                    store.close()


if __name__ == "__main__":
    unittest.main()
