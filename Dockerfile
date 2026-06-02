FROM python:3.11-slim

# 安装 Playwright 及 Chromium 所需系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 自带的 Chromium 及系统依赖（关键！）
RUN playwright install --with-deps chromium

COPY . .

# Railway 注入 PORT 环境变量
ENV PORT=5000

CMD ["python", "main.py"]
