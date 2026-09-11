.PHONY: install demo test serve up down clean

install:        ## Install Python dependencies
	pip install -r requirements.txt

demo:           ## Run the end-to-end scripted walkthrough (no infra needed)
	python demo.py

test:           ## Run the test suite
	python -m pytest tests/ -q

serve:          ## Start the API + Swagger UI on http://localhost:8000/docs
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

up:             ## Start MongoDB + API + Mongo Express via Docker
	docker compose up --build

down:           ## Stop the Docker stack
	docker compose down

clean:          ## Remove local storage artifacts
	rm -rf data stages/* .pytest_cache __pycache__ app/__pycache__ app/**/__pycache__
