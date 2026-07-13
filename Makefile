.PHONY: demo test check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	python3 -m json.tool config/starter.json >/dev/null
	@for schema in schemas/*.json; do python3 -m json.tool "$$schema" >/dev/null || exit 1; done

install-skill:
	./bin/install-skill
