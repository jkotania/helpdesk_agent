# Solution

## Running it

Python 3.11+.

```
python -m venv .venv
.venv/Scripts/activate      # or source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # add your key

python -m helpdesk "How much is an e-bike for a whole day?"
python -m helpdesk          # chat mode, empty line quits
pytest
python -m eval.run_eval     # writes eval/results.md
```

`LOG_LEVEL=INFO` prints every tool call.

## Model

`openai/gpt-oss-120b` on Groq, free tier. I call it through the `openai` SDK, since Groq, Gemini and
Ollama all have an OpenAI compatible endpoint, so switching is a matter of `.env`.

I started with Gemini. 2.5 Flash is gone for new accounts, 3.8 Flash didn't respond, 3.5 Flash has a
20 requests per day limit (one eval run is about 35) and 3.5 Flash-Lite kept answering English
questions in German, French or Vietnamese after a tool call, no matter how I worded the prompt.
gpt-oss-120b was the first one that was available, reasonably fast (around 7 s per question) and gave
the same results run after run.

## How it works

`helpdesk/agent.py` has the loop. It sends the history and the tool schemas to the model; if the model
asks for tools, it runs them, appends the results and asks again, until the model answers with text.
It gives up after 6 rounds. Tool errors go back to the model as `{"error": ...}` instead of crashing.
History is kept between questions, which is enough for follow-ups like "and if I cancel on Friday?".

The model is behind a small `Model` interface so the tests can use a fake one. No framework: the loop
is short and I wanted to see every step.

Tools in `helpdesk/tools.py`:

- `search_policies` splits the Markdown files at `##` headings and ranks sections by shared words.
  Plain keyword matching, which is enough for three short files.
- `get_booking` returns the booking or `found: false`.
- `calculate_refund` applies the cancellation rules in code: 100% of the rental at 48 h or more before
  the start, 50% from 24 h, 0% below that, fee never refunded, deposit always refunded, vouchers come
  back as vouchers, only `confirmed` bookings can be cancelled. "Now" is fixed at 2026-06-10 09:00
  +02:00, the date given with the task data. An optional `cancel_at` answers "what if I cancel tomorrow".

Two calls the rules don't make for me: exactly 48 h counts as 100% and exactly 24 h as 50%, and
cancelling after the start is sent to the staff.

The system prompt tells the model to answer only from tool results, use `calculate_refund` for every
amount, never claim it cancelled anything, answer in the customer's language and send anything else to
the staff.

## Evaluation

16 questions in `eval/questions.json` (6 refunds, 3 that should be refused, one in Polish, the rest
policies and bookings). Each one lists the tool that should be called, text the answer must or must
not contain, or that it must point to the staff. Last run: **15 of 16**, details in `eval/results.md`.

The failing one is "Can my 14-year-old rent an e-bike?". The model starts with "Yes" and then explains
the rules, mixing up "e-bikes from 16" with "under 18 needs a parent". I left it failing rather than
adding a prompt line for one question.

The first version of the eval passed everything and was wrong about it: one answer was in German and
another said "your booking has been cancelled", but both contained the right amount. I made the checks
stricter, saw them fail, then fixed the prompt. Later I had the opposite problem with gpt-oss: two
correct answers failed because the check expected one specific tool and the exact words "not found".
Results also change a bit between runs even at temperature 0, so I run it more than once.

## AI assistants

I used Claude Code as a pair programmer. It wrote first versions of the tools, the loop, the tests and
the eval runner; I read every change, ran the tests and the eval, and asked for fixes when something
looked off. Design decisions (no framework, OpenAI compatible API, keyword search, how to treat the
48 and 24 hour boundaries) I made myself or made after comparing the options it gave me.

Places where its output was wrong or needed changes:

- The first eval checks were too loose. The run reported 15 of 15, but when I read the answers one
  English question was answered in German and another said "Your booking has been cancelled". The
  checks only looked for the amount. I had it add must_not_contain rules and confirmed they fail on
  those answers before changing the prompt.
- One expected value in the eval was wrong: a question about cancelling CW-1001 on 12 June at 12:00
  expected a 50% refund, but that is 22 hours before the start, so 0%. I caught it by working out the
  hours by hand and moved the date to 11 June.
- It picked gemini-2.5-flash as the default model from its own knowledge. The API returned 404 because
  the model is no longer available to new users, so I listed the models the API actually offers and
  tested them one by one.

## Limitations

Keyword search doesn't know synonyms. The time zone is a fixed +02:00, fine for June data only. The
eval only checks substrings and runs each question once. Memory lasts one chat session. The agent
can't actually cancel anything.

## With more time

Run each eval question a few times and report a pass rate, check refund amounts against the tool
results instead of the answer text, and use `zoneinfo` for the time zone.
