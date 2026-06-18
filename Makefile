PYTHON ?= python3

.PHONY: check full-check lint carrier-sync marketplace-sync contracts conflicts drift-probes generated wiki-hygiene test existing-tests py-syntax

check: lint carrier-sync marketplace-sync contracts conflicts drift-probes generated wiki-hygiene test existing-tests

full-check: check

lint:
	@for f in skills/*/SKILL.md; do \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/lint_skill_md.py "$$f"; \
	done

carrier-sync:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_carrier_sync.py

marketplace-sync:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_marketplace_sync.py

contracts:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_skill_contracts.py

conflicts:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_skill_conflicts.py

drift-probes:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_drift_probes.py

generated:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_generated_files.py

wiki-hygiene:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_wiki_hygiene.py

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider tests

existing-tests:
	BRAINER_CHECK_NO_WRITE=1 PYTHONDONTWRITEBYTECODE=1 bash scripts/run_all_tests.sh --quiet

py-syntax:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_python_syntax.py
