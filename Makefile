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
	validate-pw \
	validate-pw-state \
	validate-pw-scenario \
	validate-pw-a1-a2 \
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
# Experiment execution
#
# Examples:
#
#   make run SCENARIO=A1
#   make analyze SCENARIO=A1
#   make plot SCENARIO=A1
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


# ------------------------------------------------------------
# PowerWorld validation
#
# Full Gate-6 validation:
#
#   make validate-pw
#
# Individual checks:
#
#   make validate-pw-state STATE=base
#   make validate-pw-scenario SCENARIO=A2
#   make validate-pw-a1-a2
#
# ------------------------------------------------------------

validate-pw:
	$(PYTHON) -m experiments.glover37.validate_powerworld \
		--all


validate-pw-state:
ifndef STATE
	$(error Usage: make validate-pw-state STATE=base)
endif
	$(PYTHON) -m experiments.glover37.validate_powerworld \
		--state $(STATE)


validate-pw-scenario:
ifndef SCENARIO
	$(error Usage: make validate-pw-scenario SCENARIO=A1)
endif
	$(PYTHON) -m experiments.glover37.validate_powerworld \
		--scenario $(SCENARIO)


validate-pw-a1-a2:
	$(PYTHON) -m experiments.glover37.validate_powerworld \
		--a1-a2


# ------------------------------------------------------------
# Cleanup
# ------------------------------------------------------------

clean-results:
	rm -rf results/glover37