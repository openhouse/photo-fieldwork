.PHONY: demo test check evals composite-evals install-skill

UNAME_S := $(shell uname -s)

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	python3 skills/curate-apple-photos/scripts/check_evals.py
	PYTHONPATH=src python3 skills/curate-apple-photos/scripts/check_composite_evals.py
	python3 -m json.tool config/starter.json >/dev/null
	python3 -m json.tool schemas/config.schema.json >/dev/null
	python3 -m json.tool schemas/retrieval.schema.json >/dev/null
	python3 -m json.tool schemas/source-profile.schema.json >/dev/null
	python3 -m json.tool skills/curate-apple-photos/references/machine-profile.example.json >/dev/null
	python3 -m json.tool skills/curate-apple-photos/evals/evals.json >/dev/null
	python3 -m json.tool skills/curate-apple-photos/evals/composite-evals.json >/dev/null
	python3 -m json.tool skills/curate-apple-photos/evals/eval-contract.json >/dev/null

ifeq ($(UNAME_S),Darwin)
	xcrun swiftc -typecheck -framework AppKit -framework Photos -framework Vision integrations/jamie-photo-archive/JamiePhotoArchive.swift
else
	@printf 'skipping macOS-only Swift helper type-check on %s\n' "$(UNAME_S)"
endif

evals:
	python3 skills/curate-apple-photos/scripts/check_evals.py --run-executable
	$(MAKE) composite-evals

composite-evals:
	PYTHONPATH=src python3 skills/curate-apple-photos/scripts/check_composite_evals.py
	PYTHONPATH=src python3 -m unittest -v tests.test_composite_evals tests.test_holdout tests.test_publication tests.test_review

install-skill:
	./bin/install-skill
