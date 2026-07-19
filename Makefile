.PHONY: demo test check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test
	PYTHONPATH=src python3 -m compileall -q src tests
	python3 -m json.tool config/starter.json >/dev/null
	python3 -m json.tool schemas/config.schema.json >/dev/null
	python3 -m json.tool config/source.example.json >/dev/null
	python3 -m json.tool schemas/source.schema.json >/dev/null
	python3 -m json.tool skills/curate-apple-photos/evals/evals.json >/dev/null
	python3 -m compileall -q skills/curate-apple-photos/scripts

install-skill:
	./bin/install-skill
