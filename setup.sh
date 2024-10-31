#!/bin/bash

# Установка русской локали
sudo apt-get update
sudo apt-get install -y language-pack-ru
sudo locale-gen ru_RU.UTF-8
sudo update-locale LANG=ru_RU.UTF-8 LC_ALL=ru_RU.UTF-8

export LANG=ru_RU.UTF-8
export LC_ALL=ru_RU.UTF-8

# Установка необходимых системных библиотек
sudo apt-get update
sudo apt-get install -y wget unzip xvfb libxi6 libgconf-2-4 \
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

# Установка Chrome
wget https://storage.googleapis.com/chrome-for-testing-public/130.0.6723.91/linux64/chrome-linux64.zip
unzip chrome-linux64.zip
sudo mv chrome-linux64 /usr/local/bin/chrome
sudo chmod +x /usr/local/bin/chrome/chrome

# Установка ChromeDriver
wget https://storage.googleapis.com/chrome-for-testing-public/130.0.6723.91/linux64/chromedriver-linux64.zip
unzip chromedriver-linux64.zip
sudo mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver
sudo chmod +x /usr/local/bin/chromedriver

# Установка Python зависимостей
pip install -r requirements.txt 