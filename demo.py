from datetime import datetime, timedelta, timezone
from pathlib import Path
from workflow import connect, import_csv, draft, simulate, status


def main():
    db = connect()
    try:
        with (Path(__file__).parent / 'examples/contacts.csv').open(encoding='utf-8', newline='') as stream:
            print('Imported:', import_csv(db, stream))
        print('Drafted:', draft(db))
        now = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
        for offset in (0, 30, 90, 180):
            print(simulate(db, now + timedelta(seconds=offset)))
        print('Status:', status(db))
        print('Offline demonstration complete. No message was sent.')
    finally:
        db.close()


if __name__ == '__main__':
    main()
