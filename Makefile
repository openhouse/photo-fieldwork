.PHONY: demo test check install-skill

UNAME_S := $(shell uname -s)

demo:
	./bin/photo-fieldwork demo --workspace runs/practice

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check: test
	PYTHONPATH=src python3 -m compileall -q src tests skills/curate-apple-photos/scripts
	python3 -m json.tool config/starter.json >/dev/null
	python3 -m json.tool schemas/config.schema.json >/dev/null
	python3 -m json.tool schemas/retrieval.schema.json >/dev/null
	python3 -m json.tool schemas/source-profile.schema.json >/dev/null
	python3 -m json.tool skills/curate-apple-photos/references/machine-profile.example.json >/dev/null

ifeq ($(UNAME_S),Darwin)
	xcrun swiftc -typecheck -framework AppKit -framework Photos -framework Vision integrations/jamie-photo-archive/JamiePhotoArchive.swift
else
	@printf 'skipping macOS-only Swift helper type-check on %s\n' "$(UNAME_S)"
endif

install-skill:
	./bin/install-skill
