.PHONY: help build up down logs shell test clean dev prod analyze process process-json check-overprint batch-analyze batch-process prod-local

# Default target
help:
	@echo "Docker commands for PDF Dieline Processor"
	@echo ""
	@echo "Development:"
	@echo "  make dev         - Start development environment"
	@echo "  make build-dev   - Build development image"
	@echo ""
	@echo "Production:"
	@echo "  make prod        - Start production environment"
	@echo "  make build       - Build production image"
	@echo "  make prod-local  - Run production image locally (Dockerfile.prod)"
	@echo ""
	@echo "Common:"
	@echo "  make up          - Start services"
	@echo "  make down        - Stop services"
	@echo "  make logs        - View logs"
	@echo "  make shell       - Open shell in container"
	@echo "  make test        - Run tests"
	@echo "  make clean       - Clean up volumes and images"
	@echo ""
	@echo "API helpers:"
	@echo "  make analyze PDF=path [API_BASE=url]" \
		"- Analyze a PDF and print JSON"
	@echo "  make process PDF=path JOB_JSON='{"reference":"ref","shape":"circle","width":45,"height":45}' OUT=out.pdf [API_BASE=url]" \
		"- Process with inline JSON"
	@echo "  make process-json PDF=path JSON_FILE=path OUT=out.pdf [API_BASE=url]" \
		"- Process with JSON file"
	@echo "  make check-overprint PDF=path" \
		"- Verify overprint ExtGState in a PDF"
	@echo "  make batch-analyze [DIR=examplecode] [API_BASE=url]" \
		"- Analyze all PDFs under DIR"
	@echo "  make batch-process [DIR=examplecode] [OUTDIR=batch_outputs] [API_BASE=url] [FONTS=embed|outline] [REMOVE_MARKS=1]" \
		"- Process all (PDF+JSON) under DIR"

# Development commands
dev:
	docker-compose -f docker-compose.dev.yml up -d
	@echo "Development server running at http://localhost:8001"
	@echo "Swagger UI: http://localhost:8001/docs"

build-dev:
	docker-compose -f docker-compose.dev.yml build

# Production commands
prod:
	docker-compose up -d
	@echo "Production server running at http://localhost:8000"

build:
	docker-compose build

# Run the production image locally using Dockerfile.prod
prod-local:
	docker compose -f docker-compose.prod.yml up --build

# Common commands
up:
	docker-compose up -d

down:
	docker-compose down
	docker-compose -f docker-compose.dev.yml down

logs:
	docker-compose logs -f

shell:
	docker exec -it ogos_pdf_processor /bin/bash

shell-dev:
	docker exec -it ogos_pdf_processor_dev /bin/bash

# Testing
test:
	docker exec ogos_pdf_processor python -m pytest

# Cleanup
clean:
	docker-compose down -v
	docker-compose -f docker-compose.dev.yml down -v
	docker system prune -f

# Docker management
restart:
	docker-compose restart

ps:
	docker-compose ps

# Volume management
backup-volumes:
	docker run --rm -v ogos_fastapi_pdfmodule_pdf_uploads:/data -v $(PWD):/backup alpine tar czf /backup/uploads-backup.tar.gz -C /data .
	docker run --rm -v ogos_fastapi_pdfmodule_pdf_outputs:/data -v $(PWD):/backup alpine tar czf /backup/outputs-backup.tar.gz -C /data .

restore-volumes:
	docker run --rm -v ogos_fastapi_pdfmodule_pdf_uploads:/data -v $(PWD):/backup alpine tar xzf /backup/uploads-backup.tar.gz -C /data
	docker run --rm -v ogos_fastapi_pdfmodule_pdf_outputs:/data -v $(PWD):/backup alpine tar xzf /backup/outputs-backup.tar.gz -C /data

# =========
# API helpers
# =========

# Analyze a PDF via the running API
analyze:
	@if [ -z "$(PDF)" ]; then \
		echo "Usage: make analyze PDF=path [API_BASE=url]"; exit 1; \
	fi
	@bash -lc 'args=""; if [ -n "$(API_BASE)" ]; then args="--base-url $(API_BASE)"; fi; \
		bash scripts/send_pdf.sh analyze "$(PDF)" $$args'

# Process with inline JSON
process:
	@if [ -z "$(PDF)" ] || [ -z "$(JOB_JSON)" ]; then \
		echo "Usage: make process PDF=path JOB_JSON=\"{...}\" OUT=out.pdf [API_BASE=url]"; exit 1; \
	fi
	@bash -lc 'args=""; if [ -n "$(API_BASE)" ]; then args="--base-url $(API_BASE)"; fi; \
		bash scripts/send_pdf.sh process "$(PDF)" --job-json '"'"$(JOB_JSON)'"'" --out "$(OUT)" $$args'

# Process with a JSON file
process-json:
	@if [ -z "$(PDF)" ] || [ -z "$(JSON_FILE)" ]; then \
		echo "Usage: make process-json PDF=path JSON_FILE=path OUT=out.pdf [API_BASE=url]"; exit 1; \
	fi
	@bash -lc 'args=""; if [ -n "$(API_BASE)" ]; then args="--base-url $(API_BASE)"; fi; \
		bash scripts/send_pdf.sh process-json "$(PDF)" --json-file "$(JSON_FILE)" --out "$(OUT)" $$args'

# Check overprint for a local PDF
check-overprint:
	@if [ -z "$(PDF)" ]; then \
		echo "Usage: make check-overprint PDF=path"; exit 1; \
	fi
	@bash -lc 'PY=$$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 ); $$PY scripts/check_overprint.py "$(PDF)"'

# Batch helpers
batch-analyze:
	@bash -lc 'DIR="$(DIR)"; [ -z "$$DIR" ] && DIR="examplecode"; \
		API_BASE="$(API_BASE)"; [ -z "$$API_BASE" ] && API_BASE="http://localhost:8000"; \
		chmod +x scripts/batch_process.sh; scripts/batch_process.sh --dir "$$DIR" --base-url "$$API_BASE" --analyze-only'

batch-process:
	@bash -lc 'DIR="$(DIR)"; [ -z "$$DIR" ] && DIR="examplecode"; \
		OUTDIR="$(OUTDIR)"; [ -z "$$OUTDIR" ] && OUTDIR="batch_outputs"; \
		API_BASE="$(API_BASE)"; [ -z "$$API_BASE" ] && API_BASE="http://localhost:8000"; \
		FONTS_ARG=""; [ -n "$(FONTS)" ] && FONTS_ARG="--fonts $(FONTS)"; \
		RM_ARG=""; [ "$(REMOVE_MARKS)" = "1" ] && RM_ARG="--remove-marks"; \
		chmod +x scripts/batch_process.sh; scripts/batch_process.sh --dir "$$DIR" --out "$$OUTDIR" --base-url "$$API_BASE" $$FONTS_ARG $$RM_ARG'

# Process with inline JSON, forcing fonts=outline via query param
process-outline:
	@if [ -z "$(PDF)" ] || [ -z "$(JOB_JSON)" ]; then \
		echo "Usage: make process-outline PDF=path JOB_JSON=\"{...}\" OUT=out.pdf [API_BASE=url]"; exit 1; \
	fi
	@bash -lc 'args="--fonts outline"; if [ -n "$(API_BASE)" ]; then args="$$args --base-url $(API_BASE)"; fi; \
		bash scripts/send_pdf.sh process "$(PDF)" --job-json '\''$(JOB_JSON)'\'' --out "$(OUT)" $$args'

# Process with JSON file, forcing fonts=outline via query param
process-json-outline:
	@if [ -z "$(PDF)" ] || [ -z "$(JSON_FILE)" ]; then \
		echo "Usage: make process-json-outline PDF=path JSON_FILE=path OUT=out.pdf [API_BASE=url]"; exit 1; \
	fi
	@bash -lc 'args="--fonts outline"; if [ -n "$(API_BASE)" ]; then args="$$args --base-url $(API_BASE)"; fi; \
		bash scripts/send_pdf.sh process-json "$(PDF)" --json-file "$(JSON_FILE)" --out "$(OUT)" $$args'
