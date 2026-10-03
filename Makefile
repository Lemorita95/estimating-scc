PYTHON ?= python

CASE := cases/glover37.json
POWERWORLD_DATA := data/powerworld/glover37
SE3_DATA := data/se3_2025.csv

RESULTS := results/glover37
STATIC_RESULTS := $(RESULTS)/static
VALIDATION_RESULTS := $(RESULTS)/validation
MECHANISM_RESULTS := $(RESULTS)/mechanism
TEMPORAL_RESULTS := $(RESULTS)/temporal
TEMPORAL_ANALYSIS := $(TEMPORAL_RESULTS)/analysis


.PHONY: \
	help \
	case \
	static \
	static-analysis \
	static-figures \
	validation \
	mechanism \
	temporal \
	temporal-analysis \
	reproduce \
	clean


help:
	@echo "Conference-paper reproducibility workflow"
	@echo
	@echo "  make case               Rebuild the 37-bus case from PowerWorld exports"
	@echo "  make static             Run the controlled static sensitivity scenarios"
	@echo "  make static-analysis    Analyze static changes relative to the baseline"
	@echo "  make static-figures     Generate static spatial figures"
	@echo "  make validation         Reproduce PowerWorld comparison results"
	@echo "  make mechanism          Reproduce structural-change mechanism analysis"
	@echo "  make temporal           Run the 168-hour temporal experiment"
	@echo "  make temporal-analysis  Reproduce temporal-spatial metrics and figures"
	@echo "  make reproduce          Reproduce the complete numerical evidence chain"
	@echo "  make clean              Remove generated results"


case:
	$(PYTHON) tools/pw2json.py \
		$(POWERWORLD_DATA)/base \
		-o $(CASE) \
		--report $(POWERWORLD_DATA)/conversion_report.md


static:
	$(PYTHON) -m experiments.glover37.run_static --all


static-analysis: static
	$(PYTHON) -m experiments.glover37.analyze_static --all


static-figures: static-analysis
	$(PYTHON) -m experiments.glover37.plot_sld --all


validation: static
	$(PYTHON) -m experiments.glover37.validate_powerworld --all


mechanism:
	$(PYTHON) -m experiments.glover37.analyze_mechanism


temporal:
	$(PYTHON) -m experiments.glover37.run_temporal \
		--se3-file $(SE3_DATA) \
		--timestamp-column timestamp \
		--load-column SE3


temporal-analysis: temporal
	$(PYTHON) -m experiments.glover37.analyze_temporal \
		--input-dir $(TEMPORAL_RESULTS) \
		--output-dir $(TEMPORAL_ANALYSIS)


reproduce: \
	case \
	static-analysis \
	validation \
	mechanism \
	temporal-analysis


clean:
	rm -rf $(RESULTS)