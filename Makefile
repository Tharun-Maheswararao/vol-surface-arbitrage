PY ?= .venv/bin/python
# The snapshot REPORT.md is built from; `run` alone uses the newest raw snapshot.
BASELINE = $(shell $(PY) -c "from volsurf.pipeline import BASELINE_SNAPSHOT; print(BASELINE_SNAPSHOT)")
SNAPSHOT ?=

.PHONY: install collect run figures test lint app notebook all

install:
	uv venv .venv && uv pip install --python $(PY) -e ".[dev,app]"

collect:
	$(PY) -m volsurf collect

run:
	$(PY) -m volsurf run $(SNAPSHOT)

figures:
	$(PY) -m volsurf figures

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests app

app:
	$(PY) -m streamlit run app/streamlit_app.py

notebook:
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb

all: SNAPSHOT = data/raw/$(BASELINE)
all: run figures notebook
