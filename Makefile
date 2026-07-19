.PHONY: demo test evals check install-skill

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

evals:
	PYTHONPATH=src ./bin/photo-fieldwork --format json evals-check --evals skills/curate-apple-photos/evals/evals.json --contract skills/curate-apple-photos/evals/eval-contract.json

check: test evals
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	for file in config/*.json schemas/*.json skills/curate-apple-photos/evals/*.json; do python3 -m json.tool "$$file" >/dev/null; done

install-skill:
	./bin/install-skill
