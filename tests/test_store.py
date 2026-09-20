import unittest
import tempfile
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostkeep.store import MemoryStore


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = MemoryStore(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_add_and_search_memory(self):
        fact = self.store.add_memory(
            content="User prefers Python for data engineering",
            source_agent="terminal-agy",
            source_session_id="session-1",
            confidence=0.95,
            domain="preferences",
            tags=["python"],
        )
        self.assertTrue(fact["id"].startswith("fact_"))
        self.assertEqual(fact["status"], "active")
        self.assertEqual(fact["domain"], "preferences")

        results = self.store.search_memory("Python", domain="preferences")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["id"], fact["id"])

    def test_provenance_tracking(self):
        f1 = self.store.add_memory(
            content="Deploy target is AWS ECS",
            source_agent="devops-agent",
            source_session_id="sess-devops",
        )
        f2 = self.store.add_memory(
            content="CI pipeline deploys Docker images to AWS ECS",
            source_agent="ci-bot",
            source_session_id="sess-ci",
            derived_from=f1["id"],
        )

        prov = self.store.get_provenance(f2["id"])
        self.assertEqual(prov["fact"]["id"], f2["id"])
        self.assertGreaterEqual(len(prov["events"]), 1)
        self.assertEqual(len(prov["derivation_chain"]), 2)
        self.assertEqual(prov["derivation_chain"][1]["id"], f1["id"])

    def test_conflict_detection_and_resolution(self):
        f1 = self.store.add_memory(
            content="Primary database backend is PostgreSQL 16 on AWS",
            source_agent="architect",
            source_session_id="sess-arch",
        )
        f2 = self.store.add_memory(
            content="Primary database backend is MySQL 8 on AWS",
            source_agent="developer",
            source_session_id="sess-dev",
        )

        conflicts = self.store.list_conflicts()
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]

        res = self.store.resolve_conflict(
            conflict_id=conflict["id"],
            resolution="keep_a",
            resolved_by="lead-engineer",
        )
        self.assertTrue(res["conflict"]["resolved"])
        self.assertEqual(len(self.store.list_conflicts()), 0)

        prov = self.store.get_provenance(f2["id"])
        resolved_events = [e for e in prov["events"] if e["event_type"] == "resolved"]
        self.assertEqual(len(resolved_events), 1)


if __name__ == "__main__":
    unittest.main()
