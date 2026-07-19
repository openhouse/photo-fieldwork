.PHONY: demo test evals check integration-check privacy-check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

evals:
	PYTHONPATH=src python3 scripts/run_evals.py \
		--suite evals/system-evals.json \
		--max-depth 16 \
		--output build/evals/composite-D.json

privacy-check:
	python3 scripts/check_public_repo.py

integration-check:
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	@for file in schemas/*.json config/*.json; do python3 -m json.tool "$$file" >/dev/null; done
	@if command -v xcrun >/dev/null 2>&1 && xcrun --find swiftc >/dev/null 2>&1; then \
		xcrun swiftc -module-cache-path build/swift-module-cache -typecheck integrations/jamie-photo-archive/JamiePhotoArchive.swift; \
	fi

check: test evals integration-check privacy-check

install-skill:
	./bin/install-skill
