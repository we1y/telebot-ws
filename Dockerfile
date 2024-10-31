FROM python:3.9-slim

RUN apt-get update && apt-get install -y wget unzip xvfb libxi6 libgconf-2-4 \
    libnss3 \
    libnss3-tools \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxtst6 \
    libpango1.0-0 \
    libgbm1

RUN wget https://storage.googleapis.com/chrome-for-testing-public/130.0.6723.91/linux64/chrome-linux64.zip
    unzip chrome-linux64.zip
    sudo mv chrome-linux64 /usr/local/bin/chrome
    sudo chmod +x /usr/local/bin/chrome/chrome

RUN wget https://storage.googleapis.com/chrome-for-testing-public/130.0.6723.91/linux64/chromedriver-linux64.zip
    unzip chromedriver-linux64.zip
    sudo mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver
    sudo chmod +x /usr/local/bin/chromedriver

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
