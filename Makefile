MAKEFLAGS += --no-builtin-rules --no-builtin-variables --warn-undefined-variables
.DELETE_ON_ERROR:
.SUFFIXES:
.DEFAULT_GOAL := help
SHELL := /bin/bash

########################################################################################################################
# Configuration
########################################################################################################################

# Pipenv environment settings
export PIPENV_VENV_IN_PROJECT := 1
export PIPENV_IGNORE_VIRTUALENVS := 1

# Project directory layout
MKFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
PROJECT_ROOT := $(abspath $(dir $(MKFILE_PATH)))

VENV_DIR := $(PROJECT_ROOT)/.venv
SRC_DIR := $(PROJECT_ROOT)/src
PKG_DIR := $(SRC_DIR)/netgear_lte2mqtt
TESTS_DIR := $(PROJECT_ROOT)/tests
DEPLOY_DIR := $(PROJECT_ROOT)/deploy

export PYTHONPATH := $(SRC_DIR)

# Executables
PYTHON_SYS := $(shell which python3 || which python)
PYTHON := $(VENV_DIR)/bin/python
PIP := $(PYTHON) -m pip
PIPENV := $(PYTHON) -m pipenv
DOCKER ?= /usr/bin/podman

# Files and targets
ENV_FILE ?= $(PROJECT_ROOT)/.env
REQ_FILE := $(PROJECT_ROOT)/requirements.txt
FLAG_FILE := $(VENV_DIR)/.installed
PIP_FILE := $(PROJECT_ROOT)/Pipfile
DOCKER_FILE := $(DEPLOY_DIR)/Dockerfile

SOURCES := $(wildcard $(PKG_DIR)/*.py)
RUFF_TARGETS := $(SRC_DIR) $(TESTS_DIR)

# Container versioning and registry settings
export PROJECT_NAME := $(notdir $(PROJECT_ROOT))
export BUILD_VERSION ?= $(shell git describe --tags --exact-match 2>/dev/null || echo latest)

BUILD_TAG ?= $(PROJECT_NAME):$(BUILD_VERSION)
MOSQUITTO_IMAGE := eclipse-mosquitto:2.1
MOSQUITTO_CONTAINER := mqtt-broker
OCI_SOURCE_LABEL := org.opencontainers.image.source=https://github.com/obatiuk/$(PROJECT_NAME)

REGISTRY ?= localhost
PUBLISH_TAG ?= latest

########################################################################################################################
# Helpers
########################################################################################################################

$(VENV_DIR)/bin/activate: $(PYTHON_SYS)
	@$< -m venv $(VENV_DIR)

$(FLAG_FILE): $(PIP_FILE) | $(VENV_DIR)/bin/activate
	@$(PIP) install --upgrade pip pipenv
	@$(PIPENV) install --dev
	@touch $@

# Export locked runtime requirements for container builds
.INTERMEDIATE: $(REQ_FILE)
$(REQ_FILE): $(PIP_FILE) | $(FLAG_FILE)
	@$(PIPENV) requirements > $@

.PHONY: env run-docker docker-publish all
env: setup
run-docker: docker-start
docker-publish: publish
all: docker-build

##@ General

.PHONY: help
help: ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\033[36m\033[0m\n"} \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 } \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' \
	$(MAKEFILE_LIST)

.PHONY: setup
setup: $(FLAG_FILE) ## Set up virtual environment and install dependencies

.PHONY: update
update: | $(FLAG_FILE) ## Upgrade pip, pipenv, and locked dependencies
	@$(PIP) install --upgrade pip pipenv
	@$(PIPENV) update

.PHONY: run
run: build ## Run the service locally using ENV_FILE
	@set -a; if [ -f "$(ENV_FILE)" ]; then source "$(ENV_FILE)"; fi; set +a; $(PYTHON) -m netgear_lte2mqtt.main

.PHONY: clean
clean: docker-stop ## Stop local containers and remove images, caches, and virtualenv
	-@$(DOCKER) image prune -a -f --build-cache --filter "label=$(OCI_SOURCE_LABEL)" 2>/dev/null \
		|| { $(DOCKER) image prune -a -f --filter "label=$(OCI_SOURCE_LABEL)"; \
		$(DOCKER) builder prune -f >/dev/null 2>&1; }
	-@if [ -x "$(PYTHON)" ]; then \
		$(PYTHON) -m ruff clean; \
		$(PIPENV) --clear; \
		$(PIPENV) remove; \
	fi
	-@rm -f $(PROJECT_ROOT)/.coverage $(REQ_FILE)
	-@rm -rf $(PROJECT_ROOT)/.pytest_cache $(PROJECT_ROOT)/.ruff_cache $(VENV_DIR)

.PHONY: print
print: print-vars | $(FLAG_FILE) ## Display Pipenv environment and dependency diagnostics
	@echo -e "\n***Project Location:\n" && $(PIPENV) --where
	@echo -e "\n***Virtualenv Path:\n" && $(PIPENV) --venv
	@echo -e "\n***Python Executable:\n" && $(PIPENV) --py
	@echo -e "\n***Environment Vars:\n" && $(PIPENV) --envs
	@echo -e "\n***Scripts Directory:\n" && $(PIPENV) scripts
	@echo -e "\n***Dependency Graph:\n" && $(PIPENV) graph
	@echo -e "\n***Installed Packages:\n" && $(PIP) list

.PHONY: print-vars
print-vars: ## Display Makefile variables
	@$(info Makefile variables:)
	@$(foreach v,$(sort $(.VARIABLES)), \
		$(if $(filter-out environment% default automatic, \
			$(origin $(v))),$(warning $(v)=$($(v)) ($(value $(v)))))):

##@ Quality

.PHONY: format
format: | $(FLAG_FILE) ## Format Python code with Ruff
	@$(PYTHON) -m ruff format $(RUFF_TARGETS)

.PHONY: lint
lint: | $(FLAG_FILE) ## Run Ruff linter and Pyright type checker
	@$(PYTHON) -m ruff check --fix $(RUFF_TARGETS)
	@$(PYTHON) -m pyright

.PHONY: audit
audit: | $(FLAG_FILE) ## Audit Python dependencies for vulnerabilities
	@$(PIPENV) audit

.PHONY: check
check: | $(FLAG_FILE) ## Run non-mutating format, lint, type, audit, and test checks
	@$(PYTHON) -m ruff format --check $(RUFF_TARGETS)
	@$(PYTHON) -m ruff check $(RUFF_TARGETS)
	@$(PYTHON) -m pyright
	@$(PIPENV) audit
	@$(PYTHON) -m pytest $(TESTS_DIR)

.PHONY: fix-audit
fix-audit: | $(FLAG_FILE) ## Auto-fix vulnerable dependencies and relock
	@$(PIPENV) run pip-audit --fix
	@$(PIPENV) lock

.PHONY: test
test: | $(FLAG_FILE) ## Run unit tests with coverage report
	@$(PYTHON) -m pytest --cov=$(PKG_DIR) --cov-report=term-missing $(TESTS_DIR)

##@ Build

.PHONY: build
build: format lint audit test $(SOURCES) ## Run format, lint, dependency audit, and unit tests

.PHONY: docker-build
docker-build: build $(REQ_FILE) $(DOCKER_FILE) ## Build container image locally
	@trap 'rm -f $(REQ_FILE)' EXIT; \
		$(DOCKER) build --format docker --pull -t $(BUILD_TAG) -f $(DOCKER_FILE) .

.PHONY: docker-start
docker-start: $(ENV_FILE) docker-build docker-stop ## Run local Mosquitto broker and service container
	@$(DOCKER) run -d --rm --name $(MOSQUITTO_CONTAINER) --network host $(MOSQUITTO_IMAGE) \
		sh -c 'printf "%s\n" "listener 1883" "allow_anonymous true" "log_dest stdout" "log_type all" \
		>/tmp/mosquitto.conf && exec /usr/sbin/mosquitto -c /tmp/mosquitto.conf'
	@trap '$(DOCKER) rm -f $(MOSQUITTO_CONTAINER) >/dev/null 2>&1 || true' EXIT; \
		$(DOCKER) run --rm --name $(PROJECT_NAME) --network host --env-file $(ENV_FILE) $(BUILD_TAG)

.PHONY: docker-stop
docker-stop: ## Stop local Mosquitto broker and service containers
	-@$(DOCKER) rm -f $(PROJECT_NAME) $(MOSQUITTO_CONTAINER) >/dev/null 2>&1

.PHONY: publish
publish: docker-build ## Build, tag, and push container image to REGISTRY
	@$(DOCKER) tag $(BUILD_TAG) $(REGISTRY)/$(BUILD_TAG)
	@$(DOCKER) push $(REGISTRY)/$(BUILD_TAG)
	@if [ "$(BUILD_VERSION)" != "$(PUBLISH_TAG)" ]; then \
		$(DOCKER) tag $(BUILD_TAG) $(REGISTRY)/$(PROJECT_NAME):$(PUBLISH_TAG); \
		$(DOCKER) push $(REGISTRY)/$(PROJECT_NAME):$(PUBLISH_TAG); \
	fi
