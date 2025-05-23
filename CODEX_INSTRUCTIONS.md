# Setup and Run HydroBot in a Testing Environment

These steps summarize how to start HydroBot in a sandbox configuration using Docker and Visual Studio Code. They are adapted from prior instructions.

## 1. Prepare the Repository

1. Clone this repository locally.
1. Copy `.env.example` to `.env` and fill in **test** credentials. Example keys are in `.env.example` lines 1-15.
1. Ensure your secrets are stored in `secrets.yaml` with sandbox values.

## 2. Configure Sandbox Mode

Edit `config.yaml` so the exchange section looks like:

```yaml
exchange:
  name: "binanceus"
  is_sandbox: true  # !! START WITH SANDBOX/TESTNET !!
```

These options appear around lines 24-30 of `config.yaml`.

## 3. Build and Run with Docker

Use the provided compose file:

```yaml
version: '3.9'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  hydrobot:
    build: .
    command: python main.py
    env_file:
      - .env
    depends_on:
      - redis

volumes:
  redis_data:
```

(lines 1-19 of `docker-compose.yml`)

From a terminal in the project folder, run:

```bash
docker-compose up --build
```

## 4. Run Tests (Optional)

Execute the test suite inside Docker:

```bash
docker-compose -f docker-compose.tests.yml up --build
```

This uses the compose file lines 1-7.

## 5. Working in Visual Studio Code

1. Install the **Docker** and **Python** extensions.
1. Use the integrated terminal to run the commands above.
1. Optionally, configure a `.devcontainer` if you want VS Code to open a container automatically (not provided by default).

## 6. Going Live

When comfortable with sandbox results, replace credentials with real keys in `secrets.yaml` and set `is_sandbox` to `false`.
Adjust risk settings carefully before live trading.
