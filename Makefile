PY ?= python3
VENV = .venv
BIN = $(VENV)/bin
DEMO_DATA = examples/data/battery_s42
DEMO_RUN = examples/battery_s42_agent

.PHONY: setup install data test demo demo-live verify-replay demo-replay check eval publish-check

setup:            ## create the virtual environment and install pinned dependencies
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -r requirements.lock
	$(BIN)/pip install -q --no-deps --force-reinstall .

install:          ## re-copy the project code into .venv after code changes (regular, non-editable install)
	$(BIN)/pip install -q --no-deps --force-reinstall .

data:             ## regenerate synthetic demo scenarios (positive seed 42, zero-effect seed 7)
	$(BIN)/python -m mei_synth.generate --seed 42 --variant positive
	$(BIN)/python -m mei_synth.generate --seed 7 --variant null

test:             ## offline test suite (no API key, no network)
	$(BIN)/python -m pytest

demo:             ## scripted run (no LLM) on the committed demo data
	$(BIN)/mei run --data $(DEMO_DATA) --out runs/demo_scripted --mode scripted

demo-live:        ## live agent run (needs ANTHROPIC_API_KEY in .env); records an LLM cache
	$(BIN)/mei run --data $(DEMO_DATA) --out runs/demo_live --mode live --cache runs/demo_live/llm_cache.jsonl

verify-replay:    ## replay a recorded run and compare every output: make verify-replay RUN=runs/demo_live
	$(BIN)/mei verify-replay --run $(or $(RUN),$(DEMO_RUN))

demo-replay:      ## replay the recorded agent run: no API key, no cost
	$(BIN)/mei run --data $(DEMO_DATA) --out runs/demo_replay --mode replay --cache $(DEMO_RUN)/llm_cache.jsonl
	$(BIN)/mei check --run runs/demo_replay --data $(DEMO_DATA)

check:            ## re-execute every tool result in the recorded example run
	$(BIN)/mei check --run $(DEMO_RUN) --data $(DEMO_DATA)

eval:             ## scripted-policy evaluation: 20 seeds x 5 effect tiers
	$(BIN)/python evaluation/run_eval.py --seeds 20

publish-check:    ## scan for credentials, private data and restricted references before pushing
	$(BIN)/python scripts/check_publishable.py
