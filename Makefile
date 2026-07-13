.PHONY: demo test check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	for file in config/*.json schemas/*.json; do python3 -m json.tool "$$file" >/dev/null; done

install-skill:
	./bin/install-skill
