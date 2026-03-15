"""
token_generator.py — Step 1: Standalone Token Generator
Generates N unique alphanumeric tokens, hashes them, and seeds a SQLite DB.
Usage: python token_generator.py [count]
"""
import sys
import sqlite3
import hashlib
import secrets
import string


DB_PATH = "election.db"


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT    NOT NULL UNIQUE,
            is_used    BOOLEAN NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS candidates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            total_votes INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (
            id            INTEGER PRIMARY KEY,
            election_name TEXT    NOT NULL DEFAULT 'General Election',
            is_active     BOOLEAN NOT NULL DEFAULT 1
        );
        INSERT OR IGNORE INTO settings (id, election_name, is_active)
        VALUES (1, 'General Election', 1);
    """)
    conn.commit()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> str:
    chars = string.ascii_uppercase + string.digits
    raw = ''.join(secrets.choice(chars) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"  # e.g. A3BK-9ZXQ-W2PR


def generate_tokens(count: int = 10) -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    inserted = []
    attempts = 0
    while len(inserted) < count and attempts < count * 5:
        attempts += 1
        token = generate_token()
        h     = hash_token(token)
        try:
            conn.execute("INSERT INTO tokens (token_hash) VALUES (?)", (h,))
            inserted.append(token)
        except sqlite3.IntegrityError:
            pass  # hash collision — regenerate

    conn.commit()
    conn.close()
    return inserted


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"\n🔐  Generating {count} unique voter tokens...\n")
    tokens = generate_tokens(count)
    print(f"{'Token':<18}  {'SHA-256 Hash (first 16 chars)'}")
    print("─" * 62)
    for t in tokens:
        h = hash_token(t)
        print(f"  {t:<18}  {h[:16]}...")
    print(f"\n✅  {len(tokens)} tokens saved to '{DB_PATH}' (is_used = False by default)\n")
    print("⚠️   DISTRIBUTE THESE TOKENS SECURELY — they are single-use.\n")
