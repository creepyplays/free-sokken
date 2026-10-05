# 🧦 free-sokken

A daily Discord reminder — with an **@everyone ping** — that counts the days of commenting
on TikTok until the socks are free:

> @everyone 🧦 Dag 1 van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok
>
> @everyone 🧦 Dag 2 van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok
>
> @everyone 🧦 Dag 3 van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok

It runs in **GitHub Actions**, so there is no server, no VPS and no PC that has to stay on.
Cost: **€0/month**. The day counter lives in [`state.json`](state.json), which the workflow
commits back to the repository after every successful post.

```
┌────────────────────────┐  tries every hour, posts once  ┌──────────────────────┐
│ GitHub Actions cron    │ ─────────────────────────────► │ main.py              │
│ 17:00-19:00 UTC window │  18:00-21:00 Brussels time     └──────────┬───────────┘
└────────────────────────┘                                          │ POST
                                               ┌────────────────────▼───────────┐
                                               │ Discord webhook → your channel │
                                               │ @everyone 🧦 Dag X             │
                                               └────────────────────────────────┘
```

**When it pings:** GitHub cron cannot follow daylight saving, so the workflow fires at
17:00, 18:00 *and* 19:00 UTC and the first run that gets through posts — the rest of the
window stops immediately without a second ping. That lands the message between **18:00 and
21:00 in Brussels**, in both summer time (CEST) and winter time (CET):

| UTC | summer (CEST) | winter (CET) |
| --- | --- | --- |
| 17:00 | 19:00 | 18:00 |
| 18:00 | 20:00 | 19:00 |
| 19:00 | 21:00 | 20:00 |

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
| `last_posted` | date of the last successful post (`Europe/Brussels`) |
| `last_day` | the number that post used |

The number only goes up once per calendar day, and only **after** Discord accepted the
message. If Discord is down, the counter stands still and the same number is retried the
next hour (and the next day). Running the workflow twice on the same day re-sends the same
number (`Dag 1`, `Dag 1`) instead of skipping a day — but *scheduled* runs don't even do
that: they see `last_posted` is already today and stop, so the @everyone ping happens
exactly once per day. A manual run always posts.

Useful commands:

```bash
python3 main.py --dry-run          # print the message, post nothing, change nothing
python3 main.py                    # post now and advance the counter
python3 main.py --day 100          # post a specific day number, counter untouched
SKIP_IF_POSTED=1 python3 main.py   # do nothing if today's reminder already went out
MENTION=none python3 main.py       # post quietly, without the @everyone ping
```

## Configuration

Everything is optional except `DISCORD_WEBHOOK_URL`:

| setting | where | default | what it does |
| --- | --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | **Secret** | – | where the reminder is posted |
| `MENTION` | *Variable* (or env) | `@everyone` | who gets pinged; `none` = ping nobody |
| `MESSAGE_TEMPLATE` | *Variable* (or env) | see below | message text, `{day}` is the day number |
| `WEBHOOK_USERNAME` | *Variable* (or env) | `Sokken Reminder` | display name of the bot |
| `TIMEZONE` | *Variable* (or env) | `Europe/Brussels` | when a new day starts |
| `SKIP_IF_POSTED` | env | off | `1` = keep quiet when today's reminder is already out |
| `STATE_FILE` | env | `state.json` | where the counter lives |
| cron window | [`.github/workflows/daily.yml`](.github/workflows/daily.yml) | `0 17-19 * * *` | hourly attempts, always UTC |

Variables are set next to the secret: *Settings → Secrets and variables → Actions →
**Variables*** tab. Example: to change the wording, add a variable `MESSAGE_TEMPLATE` with
value `🧦 Dag {day}: sokken of het is niet waar — nws.nws.nws. op TikTok`.

The ping is sent through `allowed_mentions`, so it works the same whether the message comes
from the default template or from a custom `MESSAGE_TEMPLATE`. Add `@everyone` to that
template yourself if you want the ping somewhere other than in front, and set `MENTION` to
`none` if nobody should be pinged at all.

**Changing the time:** GitHub cron is UTC and does not follow daylight saving, so pick the
UTC hours that stay inside the local window all year: `0 17-19 * * *` = 18:00–21:00 Brussels
in winter *and* 19:00–21:00 in summer. Every extra hour in the window is free — scheduled
runs stop immediately once the day's reminder has been posted, so a second attempt never
pings twice. Edit the `cron` line (<https://crontab.guru> helps) and merge the change into
`main`.

## Good to know

- Scheduled runs can be **delayed** or skipped when GitHub is busy — that's why the workflow
  has three hourly attempts instead of one. It is safe against both: the first attempt that
  gets through posts, any later attempt sees the post already happened and does nothing.
- GitHub **disables** scheduled workflows after ~60 days without repository activity. This
  job commits `state.json` every day, which counts as activity, so it keeps itself alive.
  If it ever gets disabled, *Actions → Daily Sock Reminder → Enable workflow*.
- A manual run of the workflow (*Run workflow*) posts immediately. Handy if you forgot a day.
- No ping, but the message does arrive? Discord only lets a webhook @everyone if its channel
  has that permission: *Channel settings → Permissions* → allow **Mention @everyone, @here
  and All Roles** for the webhook's role (or for @everyone in that channel).
- To restart the count at day 1, set `"day": 1, "last_posted": null, "last_day": null` in
  `state.json` and commit.
- Delete the webhook in Discord to stop everything at once.

## Running it locally

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." python3 main.py
python3 -m unittest discover -s tests   # 15 tests, no network needed
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
