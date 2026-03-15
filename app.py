import os
import hashlib
import secrets
import string
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, g

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
import os
DATABASE = os.environ.get('DATABASE_PATH', 'election.db')

# ─── DB Helpers ───────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.executescript('''
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
    ''')
    db.commit()
    db.close()

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

# Initialize DB on startup (needed for gunicorn)
init_db()

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'token_hash' in session:
        return redirect(url_for('ballot'))
    db = get_db()
    settings = db.execute('SELECT * FROM settings WHERE id=1').fetchone()
    return render_template('login.html', settings=settings)


@app.route('/login', methods=['POST'])
def login():
    raw_token = request.form.get('token', '').strip()
    if not raw_token:
        flash('Please enter your voter token.', 'error')
        return redirect(url_for('index'))

    token_hash = hash_token(raw_token)
    db = get_db()
    row = db.execute(
        'SELECT * FROM tokens WHERE token_hash = ?', (token_hash,)
    ).fetchone()

    if row is None:
        flash('Invalid token. Please check and try again.', 'error')
        return redirect(url_for('index'))
    if row['is_used']:
        flash('This token has already been used. Each token allows only one vote.', 'error')
        return redirect(url_for('index'))

    session['token_hash'] = token_hash
    return redirect(url_for('ballot'))


@app.route('/ballot')
def ballot():
    if 'token_hash' not in session:
        flash('Please enter your token to access the ballot.', 'error')
        return redirect(url_for('index'))
    db = get_db()
    settings  = db.execute('SELECT * FROM settings WHERE id=1').fetchone()
    candidates = db.execute('SELECT * FROM candidates ORDER BY name').fetchall()
    if not settings['is_active']:
        flash('This election is currently closed.', 'error')
        return redirect(url_for('index'))
    return render_template('ballot.html', settings=settings, candidates=candidates)


@app.route('/vote', methods=['POST'])
def vote():
    if 'token_hash' not in session:
        flash('Session expired. Please log in again.', 'error')
        return redirect(url_for('index'))

    candidate_id = request.form.get('candidate_id')
    if not candidate_id:
        flash('Please select a candidate before submitting.', 'error')
        return redirect(url_for('ballot'))

    token_hash = session['token_hash']
    db = get_db()

    # Re-verify token (double-check for concurrency safety)
    row = db.execute(
        'SELECT * FROM tokens WHERE token_hash = ? AND is_used = 0', (token_hash,)
    ).fetchone()
    if row is None:
        session.clear()
        flash('Token already used or invalid. Vote not recorded.', 'error')
        return redirect(url_for('index'))

    candidate = db.execute(
        'SELECT * FROM candidates WHERE id = ?', (candidate_id,)
    ).fetchone()
    if candidate is None:
        flash('Invalid candidate selection.', 'error')
        return redirect(url_for('ballot'))

    # Atomic: increment votes + mark token used in one transaction
    db.execute('BEGIN IMMEDIATE')
    db.execute(
        'UPDATE candidates SET total_votes = total_votes + 1 WHERE id = ?',
        (candidate_id,)
    )
    db.execute(
        'UPDATE tokens SET is_used = 1 WHERE token_hash = ?',
        (token_hash,)
    )
    db.commit()

    session.clear()
    return render_template('confirmed.html', candidate_name=candidate['name'])


@app.route('/results')
def results():
    db = get_db()
    settings   = db.execute('SELECT * FROM settings WHERE id=1').fetchone()
    candidates = db.execute(
        'SELECT * FROM candidates ORDER BY total_votes DESC'
    ).fetchall()
    total_votes = sum(c['total_votes'] for c in candidates)
    results_data = []
    for c in candidates:
        pct = round((c['total_votes'] / total_votes * 100), 1) if total_votes else 0
        results_data.append({
            'id': c['id'],
            'name': c['name'],
            'total_votes': c['total_votes'],
            'percentage': pct
        })
    winner = results_data[0] if results_data and total_votes > 0 else None
    tokens_info = db.execute(
        'SELECT COUNT(*) as total, SUM(is_used) as used FROM tokens'
    ).fetchone()
    return render_template(
        'results.html',
        settings=settings,
        results=results_data,
        total_votes=total_votes,
        winner=winner,
        tokens_info=tokens_info
    )


# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_settings':
            name   = request.form.get('election_name', 'General Election').strip()
            active = 1 if request.form.get('is_active') == 'on' else 0
            db.execute(
                'UPDATE settings SET election_name=?, is_active=? WHERE id=1',
                (name, active)
            )
            db.commit()
            flash('Settings updated.', 'success')

        elif action == 'add_candidate':
            name = request.form.get('candidate_name', '').strip()
            if name:
                db.execute('INSERT INTO candidates (name) VALUES (?)', (name,))
                db.commit()
                flash(f'Candidate "{name}" added.', 'success')
            else:
                flash('Candidate name cannot be empty.', 'error')

        elif action == 'remove_candidate':
            cid = request.form.get('candidate_id')
            db.execute('DELETE FROM candidates WHERE id=?', (cid,))
            db.commit()
            flash('Candidate removed.', 'success')

        elif action == 'generate_tokens':
            count = int(request.form.get('token_count', 10))
            count = max(1, min(count, 500))
            chars = string.ascii_uppercase + string.digits
            generated = []
            for _ in range(count):
                token = ''.join(secrets.choice(chars) for _ in range(12))
                formatted = f"{token[:4]}-{token[4:8]}-{token[8:]}"
                h = hash_token(formatted)
                try:
                    db.execute('INSERT INTO tokens (token_hash) VALUES (?)', (h,))
                    generated.append(formatted)
                except sqlite3.IntegrityError:
                    pass  # collision, skip
            db.commit()
            flash(f'{len(generated)} tokens generated.', 'success')
            session['last_tokens'] = generated

        elif action == 'reset_election':
            db.execute('UPDATE candidates SET total_votes = 0')
            db.execute('UPDATE tokens SET is_used = 0')
            db.commit()
            flash('Election data has been reset.', 'success')

        return redirect(url_for('admin'))

    settings   = db.execute('SELECT * FROM settings WHERE id=1').fetchone()
    candidates = db.execute('SELECT * FROM candidates ORDER BY name').fetchall()
    token_stats = db.execute(
        'SELECT COUNT(*) as total, SUM(is_used) as used FROM tokens'
    ).fetchone()
    last_tokens = session.pop('last_tokens', [])
    return render_template(
        'admin.html',
        settings=settings,
        candidates=candidates,
        token_stats=token_stats,
        last_tokens=last_tokens
    )


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
