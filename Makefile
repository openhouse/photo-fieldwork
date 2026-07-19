.PHONY: demo evals test check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

evals:
	PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*eval*.py' -v
	python3 skills/curate-apple-photos/evals/validate_evals.py

check: test
	PYTHONPATH=src python3 -m compileall -q src tests
	python3 -m compileall -q skills/curate-apple-photos/scripts
	python3 -m compileall -q skills/curate-apple-photos/evals
	python3 -m json.tool config/starter.json >/dev/null
	python3 -m json.tool schemas/config.schema.json >/dev/null
	python3 -m json.tool skills/curate-apple-photos/evals/evals.json >/dev/null
	python3 skills/curate-apple-photos/evals/validate_evals.py
	PYTHONPATH=src python3 -m photo_fieldwork audit-public --root .

install-skill:
	./bin/install-skill
