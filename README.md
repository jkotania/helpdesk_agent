# CityWheels help desk agent

A command line AI agent that answers customer questions for CityWheels, a made-up bike rental shop.
It uses an LLM with tool calling and answers only from the shop's policies (`policies/`) and bookings (`bookings.json`).

```
python -m venv .venv
.venv/Scripts/activate        # Windows; on Linux or macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # then put your API key in .env

python -m helpdesk "I want to cancel booking CW-1002. How much will I get back?"
python -m helpdesk            # chat mode with follow up questions
pytest                        # unit tests, no network or key needed
python -m eval.run_eval       # evaluation, writes eval/results.md
```

See [SOLUTION.md](SOLUTION.md) for how it works, the evaluation results and the limitations.
