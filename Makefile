.PHONY: demo test evals check check-macos install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

evals:
	PYTHONPATH=src python3 -m unittest discover -s evals -v
	PYTHONPATH=src python3 evals/validate_bank.py

check: test evals
	PYTHONPATH=src python3 -m compileall -q src tests evals skills/curate-apple-photos/scripts
	python3 -m json.tool config/starter.json >/dev/null
	python3 -m json.tool config/machine-profile.example.json >/dev/null
	python3 -m json.tool schemas/config.schema.json >/dev/null
	python3 -m json.tool schemas/profile.schema.json >/dev/null
	python3 -m json.tool schemas/catalog-plan.schema.json >/dev/null
	python3 -m json.tool schemas/publication-clearance.schema.json >/dev/null
	python3 -m json.tool evals/evals.json >/dev/null
	python3 -m json.tool evals/iterations/revision-A-hill-climb.json >/dev/null
	python3 -m json.tool evals/iterations/revision-A-agent-comparison.json >/dev/null
	python3 -m json.tool evals/iterations/revision-A-composite-hill-climb.json >/dev/null

check-macos: check
	xcrun swiftc -module-cache-path "$${TMPDIR:-/tmp}/photo-fieldwork-swift-cache" -typecheck integrations/apple-photos-helper/PhotoFieldworkHelper.swift -framework Foundation -framework AppKit -framework Photos -framework Vision

install-skill:
	./bin/install-skill
