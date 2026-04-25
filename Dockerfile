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

ENV USER_TIMEZONE=Asia/Kuala_Lumpur

CMD ["python", "-m", "bot.main"]
