.PHONY: demo test check integration-check privacy-check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

privacy-check:
	python3 scripts/check_public_repo.py

integration-check:
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	@for file in schemas/*.json config/*.json; do python3 -m json.tool "$$file" >/dev/null; done
	@if command -v xcrun >/dev/null 2>&1 && xcrun --find swiftc >/dev/null 2>&1; then \
		xcrun swiftc -module-cache-path build/swift-module-cache -typecheck integrations/jamie-photo-archive/JamiePhotoArchive.swift; \
	fi

check: test integration-check privacy-check

install-skill:
	./bin/install-skill
