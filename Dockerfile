FROM python:3.11-slim

WORKDIR /app

# Install git and other dependencies
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY bot.py ./
COPY .env ./

# Create and activate virtual environment, install dependencies
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install --requirement uv.lock

# Run the bot
CMD [".venv/bin/python", "bot.py"]