#!/bin/bash

# Установка необходимых пакетов
sudo apt-get update
sudo apt-get install -y wget unzip xvfb libxi6 libgconf-2-4

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