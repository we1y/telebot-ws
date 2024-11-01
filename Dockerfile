FROM python:3.8

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y locales && \
    sed -i -e 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=ru_RU.UTF-8

ENV LANG ru_RU.UTF-8
ENV LANGUAGE ru_RU:ru
ENV LC_ALL ru_RU.UTF-8

RUN apt-get update && apt-get install -y \
    python3-pip \
    xvfb \
    x11vnc \
    xorg \
    curl \
    gnupg \
    supervisor \
    novnc \
    fluxbox \
    wget \
    unzip \
    libxi6 \
    libgconf-2-4 \
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
    libgbm1 \
    fonts-liberation \
    fonts-liberation2 \
    nginx \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://storage.googleapis.com/chrome-for-testing-public/130.0.6723.91/linux64/chrome-linux64.zip \
    && unzip chrome-linux64.zip \
    && mv chrome-linux64 /usr/local/bin/chrome \
    && chmod +x /usr/local/bin/chrome/chrome \
    && rm chrome-linux64.zip

RUN wget https://storage.googleapis.com/chrome-for-testing-public/130.0.6723.91/linux64/chromedriver-linux64.zip \
    && unzip chromedriver-linux64.zip \
    && mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm chromedriver-linux64.zip

WORKDIR /app

COPY requirements.txt .
COPY main.py .
COPY supervisord.conf .
COPY confgi.json .

RUN pip3 install -r requirements.txt

RUN mkdir -p /root/.vnc

RUN x11vnc -storepasswd password /root/.vnc/passwd

EXPOSE 6080 5900

CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
