.PHONY: demo test check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	@for file in config/*.json schemas/*.json evals/*.json; do python3 -m json.tool "$$file" >/dev/null; done
	@if command -v swiftc >/dev/null 2>&1 && [ "$$(uname -s)" = "Darwin" ]; then \
		CLANG_MODULE_CACHE_PATH=/tmp/photo-fieldwork-clang-module-cache \
			swiftc -typecheck integrations/jamie-photo-archive/JamiePhotoArchive.swift; \
	else \
		echo "Swift typecheck skipped (requires macOS and swiftc)"; \
	fi

install-skill:
	./bin/install-skill
