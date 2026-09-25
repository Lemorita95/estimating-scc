PYTHON ?= python

POWERWORLD_GLOVER37 := data/powerworld/glover37
GLOVER37_CASE := cases/glover37.json
GLOVER37_REPORT := $(POWERWORLD_GLOVER37)/conversion_report.md


.PHONY: \
	build-glover37-case \
	run \
	run-all \
	analyze \
	analyze-all \
	plot \
	plot-all \
	clean-results


# ------------------------------------------------------------
# Build solver-ready case from PowerWorld baseline exports
# ------------------------------------------------------------

build-glover37-case:
	$(PYTHON) tools/pw2json.py \
		$(POWERWORLD_GLOVER37)/base \
		-o $(GLOVER37_CASE) \
		--report $(GLOVER37_REPORT)


# ------------------------------------------------------------
# Experiment shortcuts
#
# Examples:
#
#   make run SCENARIO=A1
#   make analyze SCENARIO=A1
#
# ------------------------------------------------------------

run:
ifndef SCENARIO
	$(error Usage: make run SCENARIO=A1)
endif
	$(PYTHON) -m experiments.glover37.run \
		--scenario $(SCENARIO)


run-all:
	$(PYTHON) -m experiments.glover37.run --all


analyze:
ifndef SCENARIO
	$(error Usage: make analyze SCENARIO=A1)
endif
	$(PYTHON) -m experiments.glover37.analysis \
		--scenario $(SCENARIO)


analyze-all:
	$(PYTHON) -m experiments.glover37.analysis --all


plot:
ifndef SCENARIO
	$(error Usage: make plot SCENARIO=A1)
endif
	$(PYTHON) -m experiments.glover37.plot_sld \
		--scenario $(SCENARIO)


plot-all:
	$(PYTHON) -m experiments.glover37.plot_sld --all


clean-results:
	rm -rf results/glover37