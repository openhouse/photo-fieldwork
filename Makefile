.PHONY: demo test check evals-check check-apple install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test evals-check
	PYTHONPATH=src python3 -m compileall -q src tests
	python3 -m compileall -q skills/curate-apple-photos/scripts
	python3 -m compileall -q skills/curate-apple-photos/evals
	python3 -m json.tool config/starter.json >/dev/null
	python3 -m json.tool schemas/config.schema.json >/dev/null
	python3 -m json.tool schemas/decision.schema.json >/dev/null
	python3 -m json.tool schemas/publication-clearance.schema.json >/dev/null

evals-check:
	python3 skills/curate-apple-photos/evals/validate_response.py --check-suite

check-apple:
	env SWIFT_MODULECACHE_PATH=/private/tmp/photo-fieldwork-swift-cache CLANG_MODULE_CACHE_PATH=/private/tmp/photo-fieldwork-clang-cache swiftc -typecheck integrations/jamie-photo-archive/JamiePhotoArchive.swift

install-skill:
	./bin/install-skill
