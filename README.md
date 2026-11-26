# Mindfulness, Journaling & Habits Assistant

A private journaling desk. Every note goes through a LangGraph path that starts with a safety check. If the note is clear, a shared memory node loads that person's profile and earlier pages, and one branch answers: a short mindfulness script, a journal reflection, a habit note, or a weekly observation.

This is a personal portfolio build by Charlene Cordero. It follows the public problem statement from the Code Without Barriers (CWB) Hackathon with id8nxt: an AI assistant for mindfulness, journaling, and habit tracking. It is a portfolio implementation of that statement. It was not entered as a submission.

**This assistant is not a medical service and not a crisis service.** It does not diagnose, treat, assess risk, or connect you to a responder. If a note matches the crisis phrase list, the app stops and returns one fixed message. That message contains the token `<HELPLINE_PLACEHOLDER>`. The token is not a phone number. Replace it with a real Philippines helpline, checked against that organization's own listing, before any public demo. Do not leave the placeholder in a demo other people can open.

## Architecture

```mermaid
flowchart TD
  UI[Web UI] --> API[FastAPI]
  API --> G[LangGraph]
  G --> S[safety_guard]
  S -->|crisis phrase| Fixed["Fixed response with HELPLINE_PLACEHOLDER"]
  S -->|clear| M[memory]
  M --> R{router}
  R --> Mind[mindfulness]
  R --> Jour[journal]
  R --> Hab[habit]
  R --> Ins[insights]
  M --> Profile[Profile: values, goals, tone]
  M --> Recall[Embeddings over this person's notes]
  Jour --> Schema[EntryAnalysis schema]
  Schema -->|invalid twice| Unanalyzed[Store the note as unanalyzed]
  API --> SQL[(SQL)]
  SQL --> Seal[Fernet on journal text]
  SQL --> Scope[Per-person scope and Postgres RLS]
```

`safety_guard` is deterministic and runs first. It does not call a model, so it still works when the model is down. The four branches share the memory node. The model, when one is configured, may write sentences. It does not own the mood, the habit counts, the citations, or the crisis response.

## What works in this slice

- Two fictional people, Maya Ellison and Jonah Reyes, each with a profile and 60 days of notes and habit marks.
- A graph: `safety_guard` → `memory` → one of `mindfulness`, `journal`, `habit`, `insights`.
- Mindfulness scripts in the repo (box breathing, 5-4-3-2-1 grounding, body scan), 1–5 minutes, chosen from the mood.
- Journal reflections that can cite an earlier page, plus a typed `EntryAnalysis` (`mood` 1–5, `sentiment`, `themes` from a fixed list). If the model output fails the schema, it is repaired once and then the note is stored as `unanalyzed`. The text is not dropped.
- Habits tied to a value. Streaks are counted in Python. A miss gets a guilt-free line. Four misses in the last six days shrink the wording.
- A weekly observation that compares this week's marks with the week before.
- Journal text and the profile sealed with Fernet. Search still works from a local hashing vector stored beside the ciphertext.
- Export of the signed-in desk, and delete-my-data that removes that person's notes, habits, and profile only.
- SQLite for the local demo. `db/postgres_rls.sql` forces row-level security for a non-superuser role. pgvector is not turned on.

## Run it

One command, from this directory:

```bash
./run.sh
```

That creates a virtualenv, installs the package, and serves the desk at [http://127.0.0.1:8741](http://127.0.0.1:8741).

No API key is required. The default is the offline path. OpenAPI is at [http://127.0.0.1:8741/docs](http://127.0.0.1:8741/docs).

Tests:

```bash
./run.sh test
```

## Demo script

About four minutes. Leave the provider on `mock`.

1. Open the desk. Read the banner. You are Maya Ellison. The values line is her profile. The card on the right is a reflection of a note already on her desk.
2. Open **Recall** and search `desk lunch`. You should see Maya's train and desk notes.
3. Switch to **Jonah Reyes** and search `baby`. His notes are a different desk. Maya's pages are not in his results.
4. Switch back to Maya. On **Today**, leave the route on **Journal**, choose **Low**, click **Use a sample note**, then **Save and reflect**. The new card cites an earlier page and mentions her values.
5. Choose **Breath** and **Low**, then save. The card is the 5-4-3-2-1 script, a few minutes, from a file in the repo.
6. Open **Habits**. Lights out by 11 is smaller after several misses, and yesterday's miss is worded as a miss, not a verdict. Morning walk still has a streak.
7. Choose **Week**. The note compares this week with the week before and does not name a cause.
8. Click **Preview the crisis screen**. Nothing is saved. The response is the fixed text, including `<HELPLINE_PLACEHOLDER>`.
9. **Export** downloads Maya's decrypted notes. **Delete my data** wipes Maya only. Jonah's 60 days stay. Do this last.

From a shell:

```bash
curl -s -c /tmp/fn.ck -X POST localhost:8741/api/session \
  -H 'content-type: application/json' -d '{"user_id":"maya"}' >/dev/null
curl -s -b /tmp/fn.ck 'localhost:8741/api/search?q=desk%20lunch'
curl -s localhost:8741/api/health
```

## How the pieces fit

**Graph.** `hinga/graph.py` compiles the six nodes. A crisis phrase ends at `safety_guard`. Everything else loads memory and then the branch the desk asked for.

**Memory.** Profile fields are values, goals, and tone, sealed at rest. Retrieval ranks earlier notes for this person only. The offline embedder is a hashing bag of words plus a small theme list. It is not a neural model. Vectors are not compared across embedding spaces.

**Journal.** `EntryAnalysis` is the typed output. Mood is the check-in, not a guess. Themes have to be in the fixed list. A live model gets one repair. After that the row is `unanalyzed` and the ciphertext remains.

**Habits.** Counts and streaks are Python. The shrink rule is four misses in the six days before today. The reframe does not scold.

**Privacy.** Fernet seals the journal body, the reflection, the analysis, and the profile. The demo key is `HINGA_FERNET_KEY` or `data/fernet.key`, which is gitignored. That is not a production key manager. The embedding can still hint at topic. Export and delete apply to the signed-in persona. Postgres policies are in `db/postgres_rls.sql` and bind only for a role that does not bypass row-level security.

The cookie is a demo switcher, not an account system.

## Configuration

Copy `.env.example` to `.env`. `.env` is gitignored. Real environment variables win over the file.

| Variable | Default | What it does |
| --- | --- | --- |
| `LLM_PROVIDER` | `mock` | `mock` stays offline. `openai` means any OpenAI-compatible chat API. |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Also works for Groq, OpenRouter, Ollama (`http://127.0.0.1:11434/v1`), or other compatible gateways. |
| `LLM_API_KEY` | empty | Required before live mode turns on. For Ollama, set any non-empty placeholder such as `ollama`. An empty key stays offline. |
| `LLM_MODEL` | `gpt-4o-mini` | Chat model name. |
| `EMBEDDING_PROVIDER` | `local` | `local` or `openai` (same base URL and key). |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Used only for the embeddings API. |
| `DATABASE_URL` | `sqlite:///data/hinga.db` | `postgresql+psycopg://hinga_app:...@host:5432/postgres?sslmode=require` for Supabase or any Postgres. |
| `SESSION_SECRET` | a dev placeholder | Signs the persona cookie. |
| `HINGA_FERNET_KEY` | empty, then `data/fernet.key` | Seals journal text. Losing the key makes the ciphertext unreadable. |
| `HINGA_PORT` | `8741` | `PORT` is used if this is unset, so a host can assign the port. |

If the live model is down or returns a schema that fails twice, that note is stored as `unanalyzed`. Journal text is not written to the log.

## Free-tier deploy

You can show this without a paid model.

**Demo that can forget its notes.** Build the `Dockerfile` and run it on [Render](https://render.com) or [Fly.io](https://fly.io) on their free allowance. Leave `LLM_PROVIDER=mock`. The container uses SQLite on its own disk. On Render's free web service that disk is ephemeral: a redeploy starts again from the sample notes. Set the health check path to `/api/health`. The image listens on `PORT`. Set `HINGA_FERNET_KEY` and `SESSION_SECRET` as env vars so a restart can still open the ciphertext if the disk survives.

**Notes that survive, still without a paid model.**

1. Create a free [Supabase](https://supabase.com) project.
2. Open `db/postgres_rls.sql`, replace the password `replace-me`, and run the script in the SQL editor. Do not enable pgvector unless you also change the app to write a vector column. This slice does not.
3. Set `DATABASE_URL` to the `hinga_app` role, not the `postgres` superuser. Supabase's `postgres` role bypasses row-level security. Use port 5432 and `?sslmode=require`.
4. Deploy the same image with `LLM_PROVIDER=mock`, a real `SESSION_SECRET`, and a real `HINGA_FERNET_KEY`.

**A live model on a free key.** Set `LLM_PROVIDER=openai`, `LLM_BASE_URL` to a host with a free tier (Groq and OpenRouter both have one; Ollama is free on your own machine), and `LLM_API_KEY`. Leave embeddings on `local` unless you also want that host's embeddings API. Old notes stay in the space they were written in.

Do not put real people's journals on the demo cookie.

## Out of scope

The desk you can click through is the slice. These are not in this repo:

- A real helpline wired in place of `<HELPLINE_PLACEHOLDER>`.
- A pgvector index. Retrieval uses local vectors stored as JSON. The SQL file mentions the extension and does not create it.
- Account signup, passwords, or email. The switcher is two fictional people.
- A key manager, rotation, or encryption of the embedding itself.
- Adding or renaming a habit in the UI. Each desk has three seeded habits. Shrink is automatic.
- Reminders, push, email, SMS, Telegram, or any scheduler.
- Voice, charts, or a phone app.
- A caregiver-specific or diagnosis-specific product.
- A neural embedding model on the default path, and re-embedding old notes if the provider changes.
- Multi-turn chat beyond the profile and the retrieved pages.

## CV description

Mindfulness, Journaling & Habits Assistant is a LangGraph journaling desk I built in Python. Every note hits a deterministic safety check before any model call; crisis language gets one fixed response with a helpline placeholder and is never diagnosed or analyzed. Clear notes pass through a shared memory node, a short profile plus retrieval over that person's own entries, and then one branch: a timed mindfulness script, a schema-checked journal reflection, habit streaks with a guilt-free miss line and smaller wording after repeated misses, or a weekly observation. If a model reply fails the schema twice, the note is kept and marked unanalyzed. Journal text is sealed with Fernet, isolated per person, and can be exported or deleted. It runs with no API key. The offline embedder is lexical, sign-in is a demo cookie for two fictional people, and the helpline token has to be replaced before a public demo.

## Status / limitations

- The sign-in is a signed cookie that picks Maya or Jonah.
- The offline embedder follows shared words and a short theme list. A one-word query can collide. The cutoff drops weak overlaps. It is still not meaning.
- Offline reflections quote and classify. Live mode may write the sentences, inside the schema, and invented citation ids are dropped.
- The sleep line on the habit card is a count of missed days whose note hit one theme. The weekly line compares average check-in marks. Neither is a cause, and the copy says so.
- The crisis check is a phrase list of the cases in the test gate. It misses other wording. It does not classify risk.
- Dates follow the server clock.
- Postgres policies do nothing for a superuser connection. Use `hinga_app`.
- Delete removes that persona's rows. It does not shred backups or the embedding's topic hint.

## Project layout

```
hinga/graph.py              safety_guard, memory, four branches
hinga/mindfulness/          box breathing, grounding, body scan
hinga/crypto.py             Fernet seal and unseal
db/postgres_rls.sql              tables, non-superuser role, forced RLS
tests/                           crisis gate, streaks, shrink, encryption, delete, isolation
run.sh                           ./run.sh  or  ./run.sh test
```
