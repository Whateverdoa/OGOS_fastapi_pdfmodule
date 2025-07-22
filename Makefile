.PHONY: help build up down logs shell test clean dev prod

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
	@echo ""
	@echo "Common:"
	@echo "  make up          - Start services"
	@echo "  make down        - Stop services"
	@echo "  make logs        - View logs"
	@echo "  make shell       - Open shell in container"
	@echo "  make test        - Run tests"
	@echo "  make clean       - Clean up volumes and images"

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