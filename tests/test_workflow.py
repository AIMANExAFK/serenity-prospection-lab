from datetime import datetime, timedelta, timezone
import io
import tempfile
from pathlib import Path
import unittest
from workflow import connect, import_csv, draft, simulate, suppress, status


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.addCleanup(self.db.close)
        self.now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)

    def seed(self):
        import_csv(self.db, io.StringIO('email,company\na@one.example.invalid,One\nb@two.example.invalid,Two\nc@two.example.invalid,Two again\n'))
        draft(self.db)

    def test_import_is_normalized_and_deduplicated(self):
        text = 'email,company\nA@one.example.invalid,One\na@one.example.invalid,Again\n'
        self.assertEqual(import_csv(self.db, io.StringIO(text)), 1)
        self.assertEqual(status(self.db), {'pending': 1})

    def test_real_addresses_are_rejected_atomically(self):
        with self.assertRaises(ValueError):
            import_csv(self.db, io.StringIO('email,company\na@one.example.invalid,Demo\ncontact@example.com,Not allowed\n'))
        self.assertEqual(status(self.db), {})

    def test_missing_columns_are_rejected(self):
        with self.assertRaises(ValueError):
            import_csv(self.db, io.StringIO('email\na@one.example.invalid\n'))

    def test_draft_runs_only_once(self):
        self.seed()
        self.assertEqual(draft(self.db), 0)
        self.assertEqual(status(self.db), {'drafted': 3})

    def test_opposition_survives_reimport(self):
        self.seed()
        suppress(self.db, 'a@one.example.invalid')
        import_csv(self.db, io.StringIO('email,company\na@one.example.invalid,New label\n'))
        self.assertEqual(status(self.db)['opted_out'], 1)

    def test_no_contact_after_reply_or_opposition(self):
        self.seed()
        for email, state in [('a@one.example.invalid', 'replied'), ('b@two.example.invalid', 'opted_out'), ('c@two.example.invalid', 'opted_out')]:
            suppress(self.db, email, state)
        self.assertEqual(simulate(self.db, self.now)['simulated'], 0)

    def test_simulation_spacing_and_daily_limit(self):
        self.seed()
        self.assertEqual(simulate(self.db, self.now)['simulated'], 1)
        self.assertEqual(simulate(self.db, self.now + timedelta(seconds=30))['reason'], 'spacing')
        self.assertEqual(simulate(self.db, self.now + timedelta(seconds=90))['simulated'], 1)
        self.assertEqual(simulate(self.db, self.now + timedelta(seconds=180))['reason'], 'daily-limit')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 2)

    def test_domain_cooldown_applies_across_days(self):
        self.seed()
        simulate(self.db, self.now)
        simulate(self.db, self.now + timedelta(seconds=90))
        self.assertEqual(simulate(self.db, self.now + timedelta(days=1))['simulated'], 0)
        self.assertEqual(simulate(self.db, self.now + timedelta(days=7, seconds=90))['simulated'], 1)

    def test_window_and_timezone_are_explicit(self):
        self.seed()
        for value in [self.now.replace(hour=8), self.now.replace(hour=17), self.now + timedelta(days=2)]:
            self.assertEqual(simulate(self.db, value)['reason'], 'outside-window')
        with self.assertRaises(ValueError):
            simulate(self.db, self.now.replace(tzinfo=None))

    def test_persistence_prevents_duplicate_initial_action(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.db'
            db = connect(path)
            import_csv(db, io.StringIO('email,company\na@one.example.invalid,One\n'))
            draft(db)
            simulate(db, self.now)
            db.close()
            db = connect(path)
            try:
                self.assertEqual(simulate(db, self.now + timedelta(days=1))['simulated'], 0)
            finally:
                db.close()

    def test_sql_characters_remain_data(self):
        import_csv(self.db, io.StringIO('email,company\na@one.example.invalid,Demo; DROP TABLE contacts;\n'))
        self.assertEqual(draft(self.db), 1)
        self.assertEqual(status(self.db), {'drafted': 1})


if __name__ == '__main__':
    unittest.main()
