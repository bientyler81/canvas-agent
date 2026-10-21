# Canvas Text Agent

A texting assistant for your Canvas classes. It runs on Vercel's free plan, so no computer of yours needs to stay on.

- **Every morning** it texts you what's due today, this week (next 7 days), and this month (next 30 days).
- **Any time**, you can text it a question, such as "what do I have for bio?", "when is the calc problem set due?", "what's my grade in English?", or "any announcements in history?". It looks up the answer in Canvas and texts you back.

## How it works

```
 Vercel Cron (daily) --> /api/digest --> Canvas API --> OpenRouter --> Inkbox --> your phone
 your phone --> Inkbox --> /api/inbound --> OpenRouter agent <--> Canvas API --> Inkbox --> your phone
```

- **Canvas API**: courses, assignments, grades, announcements (read-only).
- **OpenRouter**: the AI model. For questions it works as an agent, calling Canvas "tools" until it has the answer.
- **Inkbox**: sends and receives the bot's iMessages through Inkbox's free shared iMessage service.
- **Vercel**: free hosting. It runs the daily schedule and wakes up only when a text arrives.

The bot only answers `MY_PHONE_NUMBER` and ignores texts from anyone else. Incoming requests must carry a valid Inkbox signature.

```
api/index.py               web endpoints (digest, inbound texts, one-time setup)
canvas_digest/canvas.py    Canvas API client
canvas_digest/agent.py     OpenRouter agent + Canvas tools, digest wording
canvas_digest/digest.py    today / week / month grouping
canvas_digest/texting.py   Inkbox send / conversation history
canvas_digest/jobs.py      the morning-digest and reply-to-text jobs
canvas_digest/inkbox_setup.py  enables iMessage on the bot and creates its webhook
vercel.json                daily schedule + routing
```

## Setup (about 20 minutes, all in the browser)

1. **Canvas token**: open `https://<your-school>.instructure.com/profile/settings`, click **+ New Access Token**, and copy it.
2. **OpenRouter key**: open https://openrouter.ai/keys, create a key, and add a few dollars of credit at https://openrouter.ai/credits. A small model like Claude Haiku costs pennies a month for this.
3. **Inkbox key**: sign up at https://inkbox.ai, open the console, and create an **API key**.
4. **GitHub**: put this code in a GitHub repo.
5. **Vercel**: go to https://vercel.com/new, sign in with GitHub, and **Import** the repo. Before clicking Deploy, open **Environment Variables** and add:

   | Name | Value |
   |---|---|
   | `CANVAS_BASE_URL` | e.g. `https://yourschool.instructure.com` |
   | `CANVAS_API_TOKEN` | from step 1 |
   | `OPENROUTER_API_KEY` | from step 2 |
   | `INKBOX_API_KEY` | from step 3 |
   | `MY_PHONE_NUMBER` | your cell, like `+15551234567` |
   | `CRON_SECRET` | make up a long random password |
   | `TIMEZONE` | e.g. `America/New_York`, `America/Chicago`, `America/Los_Angeles` |

   Click **Deploy** and note your app's address, e.g. `https://canvas-agent-abc.vercel.app`.
6. **Connect Inkbox**: open `https://<your-app>.vercel.app/api/setup?key=<your CRON_SECRET>`. The page shows an `INKBOX_SIGNING_KEY` and a `connect @...` command with the router number to text it to.
7. Add `INKBOX_SIGNING_KEY` in Vercel (**Settings → Environment Variables**), then **Deployments → ⋯ → Redeploy**.
8. From your iPhone, text the `connect @...` command to the router number. Then text the bot "hi" once. Until you reply, Inkbox only lets it send short messages. The daily digest keeps the connection active; Inkbox disconnects shared connections after 14 days with no messages.
9. **Test it**: open `https://<your-app>.vercel.app/api/digest?key=<your CRON_SECRET>` to get the digest texted now, then text the bot a question.

## Schedule

`vercel.json` runs the digest at `0 12 * * *` UTC, which is 8 AM Eastern in summer and 7 AM in winter. The free Hobby plan may fire any time within that hour. To change the time, edit the schedule (in UTC) and push.

## Local testing (optional)

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in; DRY_RUN=true prints instead of texting
set -a; source .env; set +a
python3 -m canvas_digest digest
python3 -m canvas_digest ask "what's due in bio this week?"
python3 -m pytest tests
```
