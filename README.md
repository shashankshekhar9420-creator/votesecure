# VoteSecure — Token-Based Online Voting System

A lightweight, privacy-first election platform for schools, clubs, and organizations.

## Quick Start

```bash
# 1. Install dependency
pip install flask

# 2. (Optional) Pre-seed tokens via CLI
python token_generator.py 10

# 3. Run the app
python app.py
# → Open http://localhost:5000
```

## Pages

| URL | Purpose |
|-----|---------|
| `/` | Voter login — enter token here |
| `/ballot` | Cast vote (requires valid token session) |
| `/results` | Live FPTP results dashboard |
| `/admin` | Manage candidates, tokens, settings |

## Admin Workflow

1. Go to `/admin`
2. Set the **Election Name** and ensure election is **Active**
3. Add **Candidates**
4. Generate **Voter Tokens** — distribute them securely (one per voter)
5. Monitor results at `/results`

## Security Model

- Tokens are **hashed (SHA-256)** before storage — plaintext never persists
- Vote and token update happen in a **single atomic transaction** with `BEGIN IMMEDIATE`
- No link between token identity and candidate choice — **full anonymity**
- Sessions are cleared immediately after voting

## Architecture

```
Tokens     → id | token_hash (SHA-256) | is_used
Candidates → id | name | total_votes
Settings   → id | election_name | is_active
```

Winner = candidate with highest `total_votes` (First-Past-the-Post)
Percentage = (candidate_votes / total_votes) × 100
