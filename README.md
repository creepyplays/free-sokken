# 🧦 free-sokken

A daily Discord reminder that counts the days of commenting on TikTok until the socks are free:

> 🧦 Dag 1 van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok
>
> 🧦 Dag 2 van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok
>
> 🧦 Dag 3 van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok

It runs in **GitHub Actions**, so there is no server, no VPS and no PC that has to stay on.
Cost: **€0/month**. The day counter lives in [`state.json`](state.json), which the workflow
commits back to the repository after every successful post.

```
┌──────────────────────┐   every day at 18:00 UTC   ┌──────────────────────┐
│ GitHub Actions cron  │ ─────────────────────────► │ main.py              │
└──────────────────────┘                            └──────────┬───────────┘
                                                               │ POST
                                          ┌────────────────────▼───────────┐
                                          │ Discord webhook → your channel │
                                          └────────────────────────────────┘
```

## Setup (5 minutes)

1. **Create the Discord webhook** — in Discord: *Server Settings → Integrations →
   Webhooks → New Webhook*, pick the channel, then **Copy Webhook URL**.
2. **Add it as a repository secret** — this repo → *Settings → Secrets and variables →
   Actions → New repository secret*:
   - Name: `DISCORD_WEBHOOK_URL`
   - Value: the webhook URL you just copied

   Never put the URL in a file in this repo: anyone who has it can post to your channel.
3. **Merge this branch into `main`.** This matters: GitHub only runs `schedule`
   triggers from the repository's **default branch** (`main`). Until it is merged,
   the daily reminder will not fire.
4. **Test it** — *Actions → Daily Sock Reminder → Run workflow*. Tick `dry_run` first
   if you want to see the message in the log without pinging Discord. Then run it again
   without `dry_run` to receive the real "Dag 1" message in Discord.

That's it. From then on it posts automatically, every day, forever.

## Day counter

[`state.json`](state.json) looks like this:

```json
{ "day": 1, "last_posted": null, "last_day": null }
```

| field | meaning |
| --- | --- |
| `day` | the number that the **next** reminder will use |
| `last_posted` | date of the last successful post (`Europe/Amsterdam`) |
| `last_day` | the number that post used |

The number only goes up once per calendar day, and only **after** Discord accepted the
message. Running the workflow twice on the same day re-sends the same number (`Dag 1`,
`Dag 1`) instead of skipping a day. If Discord is down, the counter stands still and the
same number is retried the next day.

Useful commands:

```bash
python3 main.py --dry-run          # print the message, post nothing, change nothing
python3 main.py                    # post now and advance the counter
python3 main.py --day 100          # post a specific day number, counter untouched
```

## Configuration

Everything is optional except `DISCORD_WEBHOOK_URL`:

| setting | where | default | what it does |
| --- | --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | **Secret** | – | where the reminder is posted |
| `MESSAGE_TEMPLATE` | *Variable* (or env) | see below | message text, `{day}` is the day number |
| `WEBHOOK_USERNAME` | *Variable* (or env) | `Sokken Reminder` | display name of the bot |
| `TIMEZONE` | *Variable* (or env) | `Europe/Amsterdam` | when a new day starts |
| `STATE_FILE` | env | `state.json` | where the counter lives |
| cron time | [`.github/workflows/daily.yml`](.github/workflows/daily.yml) | `0 18 * * *` | when it runs (always UTC) |

Variables are set next to the secret: *Settings → Secrets and variables → Actions →
**Variables*** tab. Example: to change the wording, add a variable `MESSAGE_TEMPLATE` with
value `🧦 Dag {day}: sokken of het is niet waar — nws.nws.nws. op TikTok`.

**Changing the time:** GitHub cron is UTC and does not follow daylight saving, so
`0 18 * * *` = 20:00 Dutch time in summer, 19:00 in winter. Edit the `cron` line
(<https://crontab.guru> helps) and merge the change into `main`.

## Good to know

- Scheduled runs can be **delayed** — usually minutes, occasionally longer when GitHub is
  busy. The workflow is safe against that: it can't post the same day number twice.
- GitHub **disables** scheduled workflows after ~60 days without repository activity. This
  job commits `state.json` every day, which counts as activity, so it keeps itself alive.
  If it ever gets disabled, *Actions → Daily Sock Reminder → Enable workflow*.
- A manual run of the workflow (*Run workflow*) posts immediately. Handy if you forgot a day.
- To restart the count at day 1, set `"day": 1, "last_posted": null, "last_day": null` in
  `state.json` and commit.
- Delete the webhook in Discord to stop everything at once.

## Running it locally

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." python3 main.py
python3 -m unittest discover -s tests   # 10 tests, no network needed
```

Only the Python standard library is used — no `pip install` needed.

## Other hosts (if you'd rather not use GitHub Actions)

- **[cron-job.org](https://cron-job.org)** (free) can trigger the workflow via the API
  (`POST /repos/creepyplays/free-sokken/actions/workflows/daily.yml/dispatches` with a
  fine-grained token) — useful as a backup alarm if GitHub's scheduler ever stalls.
- **Cloudflare Workers** cron triggers (free tier, no credit card) running the same
  ~40 lines of Python-turned-JavaScript.
- **Render / Railway / Fly.io** free background workers — overkill for one message a day.
- PythonAnywhere is *not* an option for new free accounts: scheduled tasks are gone.

## Security

The webhook URL is the only secret and it lives in an Actions secret, never in the code.
If it ever leaks (pasted somewhere, committed by accident, screenshot), open the webhook in
Discord and hit **Delete**, create a new one and update the secret — that instantly
invalidates the old URL.
