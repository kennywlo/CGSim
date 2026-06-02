# CGSim → AskPanDA SFT datagen pipeline
#
# Targets:
#   make scenarios              Generate scenario config files from baseline topology
#   make datagen-local          Run one scenario locally (no Slurm)
#   make datagen-submit         Submit all scenarios as individual sbatch jobs
#   make merge                  Concatenate all scenario JSONL into one training file
#   make clean-scenarios        Remove generated scenario configs
#   make clean-outputs          Remove output DBs and JSONL from OUTPUTS_DIR

# ---- Paths (override on the command line) ----

HERE         := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
CLIENTS_DIR  := $(HERE)clients
RUBIN_DIR    := $(HERE)../rubin-data
SCENARIOS_DIR := $(RUBIN_DIR)/scenarios
MANIFEST     := $(SCENARIOS_DIR)/manifest.json

CGSIM_BIN    ?= $(HOME)/llm-apps/app/CGSim/build/cg-sim
PYTHON       ?= $(HOME)/.conda/envs/wf-seminar/bin/python3.10
ACCOUNT      ?= m2616
OUTPUTS_DIR  ?= $(PSCRATCH)/cgsim-outputs
EXAMPLES_PER_SCENARIO ?= 100

# ---- Slurm job settings ----
# Rubin topology (568 nodes) runs comfortably in ~5 min on a shared node.
# CGSimDataGenerator makes API calls so it needs outbound HTTPS (Perlmutter allows this).
SLURM_TIME       ?= 00:45:00
SLURM_NTASKS     ?= 1
SLURM_CPUS       ?= 4
SLURM_MEM_PER_CPU ?= 1900
SLURM_QOS        ?= shared
SLURM_CONSTRAINT ?= cpu

# ---- Default target ----

.PHONY: help
help:
	@echo ""
	@echo "CGSim → AskPanDA SFT datagen pipeline"
	@echo ""
	@echo "  make scenarios                    Generate scenario config files"
	@echo "  make datagen-local SCENARIO=name  Run one scenario locally"
	@echo "  make datagen-submit               Submit all scenarios via sbatch"
	@echo "  make merge                        Merge all JSONL into one file"
	@echo "  make clean-scenarios              Delete generated scenario configs"
	@echo ""
	@echo "Key variables (override on command line):"
	@echo "  ACCOUNT=$(ACCOUNT)"
	@echo "  OUTPUTS_DIR=$(OUTPUTS_DIR)"
	@echo "  EXAMPLES_PER_SCENARIO=$(EXAMPLES_PER_SCENARIO)"
	@echo "  CGSIM_BIN=$(CGSIM_BIN)"
	@echo ""

# ---- Generate scenario configs ----

.PHONY: scenarios
scenarios:
	$(PYTHON) $(CLIENTS_DIR)/ScenarioConfigGenerator.py \
	    --output-dir $(SCENARIOS_DIR)

$(MANIFEST): scenarios

# ---- Run one scenario locally (no Slurm) ----

SCENARIO ?= baseline

.PHONY: datagen-local
datagen-local: $(MANIFEST)
	$(PYTHON) $(HERE)datagen_local.py \
	    --manifest    $(MANIFEST) \
	    --outputs-dir $(OUTPUTS_DIR) \
	    --python      $(PYTHON) \
	    --clients-dir $(CLIENTS_DIR) \
	    --cgsim-bin   $(CGSIM_BIN) \
	    --n           $(EXAMPLES_PER_SCENARIO) \
	    --scenarios   $(SCENARIO)

# ---- Run all scenarios locally (login node, SLAC tunnel must be up) ----

.PHONY: datagen-all-local
datagen-all-local: $(MANIFEST)
	$(PYTHON) $(HERE)datagen_local.py \
	    --manifest    $(MANIFEST) \
	    --outputs-dir $(OUTPUTS_DIR) \
	    --python      $(PYTHON) \
	    --clients-dir $(CLIENTS_DIR) \
	    --cgsim-bin   $(CGSIM_BIN) \
	    --n           $(EXAMPLES_PER_SCENARIO)

# ---- Submit all scenarios via sbatch ----

.PHONY: datagen-submit
datagen-submit: $(MANIFEST)
	$(PYTHON) $(HERE)datagen_submit.py \
	    --manifest    $(MANIFEST) \
	    --outputs-dir $(OUTPUTS_DIR) \
	    --cgsim-bin   $(CGSIM_BIN) \
	    --python      $(PYTHON) \
	    --clients-dir $(CLIENTS_DIR) \
	    --run-script  $(HERE)datagen_run.sh \
	    --account      $(ACCOUNT) \
	    --qos          $(SLURM_QOS) \
	    --constraint   $(SLURM_CONSTRAINT) \
	    --time         $(SLURM_TIME) \
	    --cpus         $(SLURM_CPUS) \
	    --mem-per-cpu  $(SLURM_MEM_PER_CPU) \
	    --n           $(EXAMPLES_PER_SCENARIO)

# ---- Merge all JSONL into one training file ----

MERGE_OUT ?= $(OUTPUTS_DIR)/askpanda_sft_cgsim_all.jsonl

.PHONY: merge
merge:
	@echo "Merging JSONL files from $(OUTPUTS_DIR) → $(MERGE_OUT)"
	@cat $(OUTPUTS_DIR)/sft_*.jsonl > $(MERGE_OUT)
	@echo "Total examples: $$(wc -l < $(MERGE_OUT))"

# ---- Cleanup ----

.PHONY: clean-scenarios
clean-scenarios:
	rm -rf $(SCENARIOS_DIR)

.PHONY: clean-outputs
clean-outputs:
	@echo "This will delete $(OUTPUTS_DIR)/*.jsonl and *.db — are you sure? (ctrl-C to abort)"
	@sleep 3
	rm -f $(OUTPUTS_DIR)/sft_*.jsonl $(OUTPUTS_DIR)/rubin_*.db
