.PHONY: demo test check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test
	PYTHONPATH=src python3 -m compileall -q src tests
	python3 -m json.tool config/starter.json >/dev/null
	python3 -m json.tool schemas/config.schema.json >/dev/null

install-skill:
	./bin/install-skill
