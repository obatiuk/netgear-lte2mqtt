# Make configuration
MAKEFLAGS += --no-builtin-rules --no-builtin-variables --warn-undefined-variables
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:
SHELL := /bin/bash

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
DOCKER_DIR := $(PROJECT_ROOT)/docker

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
DOCKER_FILE := $(DOCKER_DIR)/Dockerfile

SOURCES := $(wildcard $(PKG_DIR)/*.py)
RUFF_TARGETS := $(SRC_DIR) $(TESTS_DIR)

# Container versioning and registry settings
export PROJECT_NAME := $(notdir $(PROJECT_ROOT))
export BUILD_VERSION ?= $(shell git describe --tags --exact-match 2>/dev/null || echo latest)

BUILD_TAG ?= $(PROJECT_NAME):$(BUILD_VERSION)
MOSQUITTO_CONTAINER := mqtt-broker

REGISTRY ?= localhost
PUBLISH_TAG ?= latest

# Virtual environment and dependency bootstrap
$(VENV_DIR)/bin/activate: $(PYTHON_SYS)
	@$< -m venv $(VENV_DIR)

$(FLAG_FILE): $(VENV_DIR)/bin/activate $(PIP_FILE)
	@$(PIP) install --upgrade pip pipenv
	@$(PIPENV) install --dev
	@touch $@

# Export locked runtime requirements for container builds
.INTERMEDIATE: $(REQ_FILE)
$(REQ_FILE): $(FLAG_FILE)
	@$(PIPENV) requirements > $@

.PHONY: env setup
env setup: $(FLAG_FILE)

# Code formatting, linting, type checking, and security auditing
.PHONY: format
format: env
	@$(PYTHON) -m ruff format $(RUFF_TARGETS)

.PHONY: lint
lint: env
	@$(PYTHON) -m ruff check --fix $(RUFF_TARGETS)
	@$(PYTHON) -m pyright

.PHONY: test
test: env
	@$(PYTHON) -m pytest --cov=$(PKG_DIR) --cov-report=term-missing $(TESTS_DIR)

.PHONY: check
check: env
	@$(PIPENV) audit

.PHONY: fix-audit
fix-audit: env
	@$(PIPENV) run pip-audit --fix
	@$(PIPENV) lock

# Local verification and execution
.PHONY: build
build: format lint check test $(SOURCES)

.PHONY: run
run: $(ENV_FILE) $(PKG_DIR)/main.py env build
	@set -a; if [ -f $< ]; then source $<; fi; set +a; $(PYTHON) -m netgear_lte2mqtt.main

.PHONY: update
update: env
	@$(PIP) install --upgrade pip pipenv
	@$(PIPENV) update

# Container lifecycle and publishing
.PHONY: docker-build
docker-build: build $(REQ_FILE) $(DOCKER_FILE)
	@$(DOCKER) build --format docker --pull -t $(BUILD_TAG) -f $(DOCKER_FILE) .

.PHONY: docker-start
docker-start: $(ENV_FILE) docker-build docker-stop
	@$(DOCKER) run -d --rm --name $(MOSQUITTO_CONTAINER) --network host eclipse-mosquitto:latest \
		sh -c 'printf "listener 1883\nallow_anonymous true\nlog_dest stdout\nlog_type all\n" > /tmp/mosquitto.conf && exec /usr/sbin/mosquitto -c /tmp/mosquitto.conf'
	@trap '$(DOCKER) rm -f $(MOSQUITTO_CONTAINER) >/dev/null 2>&1 || true' EXIT; \
		$(DOCKER) run --rm --name $(PROJECT_NAME) --network host --env-file $(ENV_FILE) $(BUILD_TAG)

.PHONY: docker-stop
docker-stop:
	-@$(DOCKER) rm -f $(PROJECT_NAME) $(MOSQUITTO_CONTAINER) >/dev/null 2>&1

.PHONY: docker-publish
docker-publish: docker-build
	@$(DOCKER) tag $(BUILD_TAG) $(REGISTRY)/$(BUILD_TAG)
	@$(DOCKER) push $(REGISTRY)/$(BUILD_TAG)
	@$(DOCKER) tag $(BUILD_TAG) $(REGISTRY)/$(PROJECT_NAME):$(PUBLISH_TAG)
	@$(DOCKER) push $(REGISTRY)/$(PROJECT_NAME):$(PUBLISH_TAG)

.PHONY: run-docker
run-docker: docker-start

.PHONY: publish
publish: docker-publish

# Cleanup and diagnostics
.PHONY: clean
clean: docker-stop
	-@$(DOCKER) rmi $(BUILD_TAG)
	-@$(PYTHON) -m ruff clean
	-@$(PIPENV) --clear
	-@$(PIPENV) remove
	-@rm -f $(PROJECT_ROOT)/.coverage
	-@rm -rf $(PROJECT_ROOT)/.pytest_cache $(PROJECT_ROOT)/.ruff_cache

.PHONY: print
print: env print-vars
	@echo -e "\n***Project Location:\n" && $(PIPENV) --where
	@echo -e "\n***Virtualenv Path:\n" && $(PIPENV) --venv
	@echo -e "\n***Python Executable:\n" && $(PIPENV) --py
	@echo -e "\n***Environment Vars:\n" && $(PIPENV) --envs
	@echo -e "\n***Scripts Directory:\n" && $(PIPENV) scripts
	@echo -e "\n***Dependency Graph:\n" && $(PIPENV) graph
	@echo -e "\n***Installed Packages:\n" && $(PIP) list

.PHONY: print-vars
print-vars:
	@$(info Makefile variables:)
	@$(foreach v,$(sort $(.VARIABLES)), \
		$(if $(filter-out environment% default automatic, \
			$(origin $v)),$(warning $v=$($v) ($(value $v))))):

.PHONY: all
all: docker-build
