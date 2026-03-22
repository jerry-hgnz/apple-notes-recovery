from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from apple_notes_recovery.fuse import run


class FuseTests(unittest.TestCase):
    def test_fuse_separates_direct_residual_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live_titles = root / "live.tsv"
            folder_names = root / "folders.tsv"
            mac = root / "mac.tsv"
            run_dir = root / "video_run"
            out_dir = root / "out"
            run_dir.mkdir()

            live_titles.write_text(
                "note_id\ttitle\tmodification_date\n"
                "x-coredata://a/ICNote/p1\tAlpha\t2026-01-01\n"
                "x-coredata://a/ICNote/p2\tBeta\t2026-01-01\n"
                "x-coredata://a/ICNote/p3\tGamma\t2026-01-01\n",
                encoding="utf-8",
            )
            folder_names.write_text(
                "folder_name\nProjects\nArchive\nReview\n",
                encoding="utf-8",
            )
            mac.write_text(
                "note_rowid\tidentifier\tcurrent_title\tcurrent_folder_pk\tcurrent_folder_name\trecovered_folder_pk\trecovered_folder_name\trecovered_title\ttitle_matches\tconfidence\tcandidate_count\tdistinct_folder_count\tpage_no\tstart_offset\tidentifier_offset\tmodification_date\tcreation_date\n"
                "1\tid1\tAlpha\t0\tDeleted\t100\tProjects\tAlpha\tyes\thigh\t1\t1\t1\t1\t1\t2026-01-01\t2026-01-01\n",
                encoding="utf-8",
            )
            (run_dir / "video_live_exact_unique.tsv").write_text(
                "folder_norm\ttitle_norm\tnote_id\tlive_title\tmodification_date\n"
                "projects\talpha\tx-coredata://a/ICNote/p1\tAlpha\t2026-01-01\n"
                "review\tbeta\tx-coredata://a/ICNote/p2\tBeta\t2026-01-01\n",
                encoding="utf-8",
            )
            (run_dir / "video_live_fuzzy_unique.tsv").write_text(
                "folder_norm\tobserved_title_norm\tmatched_live_title_norm\tnote_id\tlive_title\tmodification_date\tsimilarity\tsecond_best_similarity\n",
                encoding="utf-8",
            )
            (run_dir / "video_live_exact_ambiguous_live.tsv").write_text(
                "folder_norm\ttitle_norm\tlive_candidate_count\tnote_ids\n",
                encoding="utf-8",
            )
            (run_dir / "video_live_exact_ambiguous_video.tsv").write_text(
                "folder_norm\ttitle_norm\tvideo_folder_candidates\tlive_candidate_count\n",
                encoding="utf-8",
            )
            (run_dir / "video_live_unmatched_pairs.tsv").write_text(
                "folder_norm\ttitle_norm\nreview\tbeta\n",
                encoding="utf-8",
            )

            args = SimpleNamespace(
                live_titles=str(live_titles),
                folder_names=str(folder_names),
                video_run_dir=[str(run_dir)],
                mac_mappings=str(mac),
                residual_folder="Archive",
                expected_residual_count=None,
                out_dir=str(out_dir),
            )
            rc = run(args)
            self.assertEqual(rc, 0)

            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["direct_evidence_assignments"], 2)
            self.assertEqual(summary["residual_bucket_inference_count"], 1)
            self.assertEqual(summary["review_needed_count"], 0)


if __name__ == "__main__":
    unittest.main()
