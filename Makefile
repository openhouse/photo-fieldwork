.PHONY: demo test check check-macos install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	python3 -m json.tool config/starter.json >/dev/null
	python3 -m json.tool config/machine-profile.example.json >/dev/null
	python3 -m json.tool schemas/config.schema.json >/dev/null
	python3 -m json.tool schemas/profile.schema.json >/dev/null

check-macos: check
	xcrun swiftc -module-cache-path "$${TMPDIR:-/tmp}/photo-fieldwork-swift-cache" -typecheck integrations/apple-photos-helper/PhotoFieldworkHelper.swift -framework Foundation -framework AppKit -framework Photos -framework Vision

install-skill:
	./bin/install-skill
