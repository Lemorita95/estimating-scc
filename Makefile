PYTHON ?= python

POWERWORLD_ROOT := data/powerworld
CONVERTER := tools/pw2json.py

.DEFAULT_GOAL := noop

.PHONY: noop
noop:
	@:


# Usage:
#   make glover37
#
# Reads:
#   data/powerworld/glover37/base/
#
# Writes:
#   cases/glover37.json
#   data/powerworld/glover37/conversion_report.md
%:
	@if [ ! -d "$(POWERWORLD_ROOT)/$@/base" ]; then \
		echo "Error: PowerWorld case '$@' not found."; \
		echo "Expected directory: $(POWERWORLD_ROOT)/$@/base"; \
		exit 1; \
	fi
	@mkdir -p cases
	$(PYTHON) $(CONVERTER) \
		$(POWERWORLD_ROOT)/$@/base \
		-o cases/$@.json \
		--report $(POWERWORLD_ROOT)/$@/conversion_report.md