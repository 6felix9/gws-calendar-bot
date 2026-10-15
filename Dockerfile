FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm \
    && npm install -g @googleworkspace/cli \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x scripts/entrypoint.sh

ENV USER_TIMEZONE=Asia/Kuala_Lumpur
ENV GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/gws-config/credentials.json
ENV GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file
ENV GOOGLE_WORKSPACE_CLI_CONFIG_DIR=/gws-config

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
