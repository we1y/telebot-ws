import hashlib
import uuid
from selenium import webdriver
from selenium.common import TimeoutException, StaleElementReferenceException
from selenium.webdriver import Keys, ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
import os
import json
import sqlite3
import shutil
import requests
import asyncio
from datetime import datetime, date, timedelta
import sys

def adapt_date(date_value: date) -> str:
    return date_value.isoformat()

def convert_date(date_str: bytes) -> date:
    return datetime.strptime(date_str.decode(), '%Y-%m-%d').date()

sqlite3.register_adapter(date, adapt_date)
sqlite3.register_converter("DATE", convert_date)

def get_base_path():
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return base_path

def get_db_path():
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
    return os.path.join(exe_dir, 'users.db')

def get_default_db_path():
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, 'users.db')

def ensure_db_exists():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        default_db = get_default_db_path()
        if os.path.exists(default_db):
            shutil.copy2(default_db, db_path)
    return db_path

conn = sqlite3.connect(ensure_db_exists(), detect_types=sqlite3.PARSE_DECLTYPES)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, 
    subscribed INTEGER DEFAULT 0,
    subscription_end DATE
)''')
conn.commit()

async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    context.user_data['user_id'] = user_id
    cursor.execute('''SELECT id FROM users WHERE id = ?''', (user_id,))

    if cursor.fetchone():
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Доброго времени суток {user_id}')
    else:
        await save_user(user_id)
        await update.message.reply_text(f'Пользователь успешно создан с ID: {user_id}')

async def save_user(user_id: int) -> None:
    cursor.execute('''INSERT INTO users (id) VALUES (?)''', (user_id,))
    conn.commit()
    print(user_id)

async def mark_as_subscribed(update: Update, context: CallbackContext) -> None:
    user_id = context.user_data['user_id']
    subscription_end = (datetime.now() + timedelta(days=30)).date()
    try:
        cursor.execute(
            'UPDATE users SET subscribed = ?, subscription_end = ? WHERE id = ?',
            (1, subscription_end, user_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Ошибка обработки статуса подписки: {e}'
        )
        conn.rollback()

async def is_subscriber(user_id: int) -> bool:
    cursor.execute(
        'SELECT subscribed, subscription_end FROM users WHERE id = ?',
        (user_id,)
    )

    row = cursor.fetchone()
    if row and row[0] == 1:
        subscription_end = row[1]
        if isinstance(subscription_end, str):
            subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d').date()
        return subscription_end >= datetime.now().date()
    return False

async def check_subscription(update: Update, context: CallbackContext) -> None:
    try:
        user_id = context.user_data['user_id']
        cursor.execute('''SELECT subscription_end FROM users WHERE id = ? AND subscribed = 1''', (user_id,))
        row = cursor.fetchone()

        if row:
            subscription_end = row[0]
            days_left = (subscription_end - datetime.now().date()).days

            if days_left > 0:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Ваша подписка активна\nОсталось дней: {days_left}\nДата окончания: {subscription_end}"
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Ваша подписка истекла. Используйте /pay для продления"
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="У ваc нет активной подписки. Используйте /pay для приобретения"
            )
    except KeyError:
        await update.message.reply_text('Перед тем как начать работу, запустите сессию')

async def on_payment_success(update: Update, context: CallbackContext) -> None:
    await mark_as_subscribed(update, context)

async def payment(update: Update, context: CallbackContext) -> None:
    try:
        user_id = context.user_data['user_id']
        context.user_data['payment_cancelled'] = False

        cursor.execute('''SELECT subscription_end FROM users WHERE id = ? AND subscribed = 1''', (user_id,))
        row = cursor.fetchone()

        if row:
            subscription_end = row[0] if isinstance(row[0], date) else datetime.strptime(row[0], '%Y-%m-%d').date()
            if subscription_end >= datetime.now().date():
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text=f"У вас уже есть активная подписка до {subscription_end}")
                return
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text="Ваша подписка истекла. Вы можете продлить ее")

        url = "https://api.cryptocloud.plus/v2/invoice/create"
        headers = {
            "Authorization": config['cryptocloud_api_token'],
            "Content-Type": "application/json",
        }

        data = {
            "amount": config['price'],
            "shop_id": config['shop_id'],
            "currency": config['currency'],
        }

        params = {
            "time_to_pay": {
                "hours": 0,
                "minutes": 15,
            },
        }

        response = requests.post(url, headers=headers, json=data, params=params)

        if response.status_code == 200:
            invoice_data = response.json()
            payment_link = invoice_data["result"]["link"]
            payment_id = invoice_data["result"]["uuid"]

            context.user_data.pop('payment_message_id', None)
            context.user_data.pop('payment_id', None)

            keyboard = [[InlineKeyboardButton("Отменить оплату", callback_data=f"cancel_payment_{payment_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ссылка на оплату: {payment_link}\nЦена: {data['amount']} {data['currency']}\nID платежа: {payment_id}\n---------------------\nУ вас есть 15 минут на оплату",
                reply_markup=reply_markup
            )
            context.user_data['payment_message_id'] = message.message_id
            context.user_data['payment_id'] = payment_id

            asyncio.create_task(check_payment_status(payment_id, update, context))
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Не удалось создать счет для оплаты")
    except KeyError:
        await update.message.reply_text('Перед тем как начать работу, запустите сессию')

async def payment_cancelled(update: Update, context: CallbackContext, payment_id) -> None:
    url = "https://api.cryptocloud.plus/v2/invoice/merchant/canceled"
    headers = {
        "Authorization": config['cryptocloud_api_token'],
    }
    data = {
        "uuid": payment_id,
    }
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Платёж отменён. Используйте /pay для создания нового платежа"
        )
    else:
        print("Fail:", response.status_code, response.text)

async def check_payment_status(payment_id: str, update: Update, context: CallbackContext):
    user_id = context.user_data['user_id']

    url = "https://api.cryptocloud.plus/v1/invoice/info"

    params = {
        "uuid": payment_id,
    }

    headers = {
        "Authorization": config['cryptocloud_api_token'],
    }

    time = 180

    for attempt in range(time):
        if context.user_data.get('payment_cancelled'):
            print(f"Payment {payment_id} was cancelled")
            return
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            status_data = response.json()
            payment_status = status_data.get("status_invoice")
            if payment_status == "paid":
                payment_message_id = context.user_data.get('payment_message_id')
                if payment_message_id:
                    try:
                        await context.bot.edit_message_reply_markup(
                            chat_id=update.effective_chat.id,
                            message_id=payment_message_id,
                            reply_markup=None
                        )
                    except Exception as e:
                        print(f"Error removing payment button: {e}")

                await on_payment_success(update, context)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f'Подписка успешно приобретена для пользователя: {user_id}'
                )
                break
            else:
                if attempt < time - 1:
                    await asyncio.sleep(5)
                    continue
                else:
                    payment_message_id = context.user_data.get('payment_message_id')
                    if payment_message_id:
                        try:
                            await context.bot.edit_message_reply_markup(
                                chat_id=update.effective_chat.id,
                                message_id=payment_message_id,
                                reply_markup=None
                            )
                        except Exception as e:
                            print(f"Error removing payment button: {e}")
                    await payment_cancelled(update, context, payment_id)
                    break

        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
            break
        except requests.exceptions.RequestException as req_err:
            print(f"Request error occurred: {req_err}")
            break
        except ValueError as json_err:
            print(f"JSON decode error: {json_err}")
            break

async def ws_auto(update: Update, context: CallbackContext) -> int:
    try:
        user_id = context.user_data['user_id']
        if await is_subscriber(user_id):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Введите текст сообщения, которое хотите отправить. Вы также можете добавить файлы")
            return 1
        else:
            await update.message.reply_text('К сожалению, мы не нашли подписку на вашем аккаунте')
    except KeyError:
        await update.message.reply_text('Перед тем как начать работу, запустите сессию')

async def get_message(update: Update, context: CallbackContext) -> int:
    user_id = context.user_data['user_id']
    message = update.message.text

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Подождите немного")
    asyncio.create_task(run_selenium(message, context, update, user_id))
    return ConversationHandler.END

async def auth(update: Update, context: CallbackContext) -> None:
    try:
        user_id = context.user_data['user_id']
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Подождите немного, сейчас мы пришлем вам QR-code для авторизации")
        await asyncio.sleep(2)
        asyncio.create_task(run_auth_selenium(update, context, user_id))
    except KeyError:
        await update.message.reply_text('Перед тем как начать работу, запустите сессию')

def setup_driver(user_id, headless=True):
    profile_path = os.path.join(get_working_dir(), "users", str(user_id))
    if not os.path.exists(profile_path):
        os.makedirs(profile_path)
    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={profile_path}")

    if headless:
        options.add_argument('--headless=new')
    
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--start-maximized')

    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--ignore-certificate-errors')

    options.add_argument('--lang=ru')
    options.add_argument('--accept-language=ru')
    options.add_experimental_option("prefs", {
        'intl.accept_languages': 'ru, ru-RU',
        'profile.default_content_setting_values.notifications': 2
    })

    options.binary_location = "/usr/local/bin/chrome/chrome"

    service = Service(executable_path="/usr/local/bin/chromedriver")

    driver = webdriver.Chrome(service=service, options=options)
    return driver

def is_user_auth(driver):
    try:
        WebDriverWait(driver, 10).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, 'div[role="listitem"]'))
        )
        return True
    except TimeoutException:
        return False

async def run_auth_selenium(update, context, user_id) -> None:
    driver = setup_driver(user_id)

    url = "https://web.whatsapp.com/"
    driver.get(url)

    photos_folder = os.path.join(get_working_dir(), "photos", str(user_id))
    if not os.path.exists(photos_folder):
        os.makedirs(photos_folder)

    if is_user_auth(driver):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы уже авторизованы")
        driver.quit()
        return

    qr_scanned = False
    attempts = 0

    while not qr_scanned and attempts < 3:
        try:
            qr = WebDriverWait(driver, 30).until(
                ec.presence_of_element_located((By.XPATH, "//div[@data-ref]"))
            )
            qr_screenshot = qr.screenshot_as_png

            qr_code_path = os.path.join(photos_folder, f"qr_code_{user_id}.png")
            with open(qr_code_path, 'wb') as f:
                f.write(qr_screenshot)
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open(qr_code_path, 'rb'))
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Пожалуйста, отсканируйте QR-code")
        except TimeoutException:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="QR-code не был отсканирован, продолжаем проверку")
        try:
            WebDriverWait(driver, 30).until(
                ec.presence_of_element_located((By.CSS_SELECTOR, 'div[role="listitem"]'))
            )
            qr_scanned = True
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы успешно вошли в аккаунт")
            driver.quit()
            cleanup_photos(photos_folder)
        except TimeoutException:
            attempts += 1
            if attempts < 3:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="Осталось {} попытки(а)".format(3 - attempts))
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id , text="Вы не успели войти в аккаунт. Пожалуйста, попробуйте еще раз")
                driver.quit()
                cleanup_photos(photos_folder)
                delete_user_data_after_nologging(user_id)
                return

async def run_selenium(user_message, context, update, user_id):
    driver = setup_driver(user_id)
    context.user_data['driver'] = driver

    url = "https://web.whatsapp.com/"
    driver.get(url)

    photos_folder = os.path.join(get_working_dir(), "photos", str(user_id))
    if not os.path.exists(photos_folder):
        os.makedirs(photos_folder)

    if is_user_auth(driver):
        translate_y = 0
        chat_titles = []

        while True:
            chats = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')

            if not chats:
                break

            new_chats_found = False

            try:
                chats = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')
                for i, chat in enumerate(chats):
                    WebDriverWait(driver, 5).until(ec.visibility_of(chat))

                    chat_style = chat.get_attribute("style")

                    if f'transform: translateY({translate_y}px);' in chat_style:
                        grid_element = chat.find_element(By.CSS_SELECTOR, 'div[role="gridcell"]')
                        title_element = grid_element.find_element(By.TAG_NAME, 'span')
                        chat_photo_path = os.path.join(photos_folder, f"chat_{i}_{user_id}.png")
                        title_element.screenshot(chat_photo_path)
                        title_text = title_element.text
                        if title_text not in chat_titles:
                            chat_titles.append(title_text)
                            print("Фотография чата сохранена: {}".format(title_text))
                            new_chats_found = True
                        translate_y += 72
            except StaleElementReferenceException:
                continue

            if not new_chats_found:
                break

        if chat_titles:
            full_titles = ", ".join(chat_titles)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Список чатов:")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=full_titles)

            keyboard = [
                [InlineKeyboardButton("Отправить выбранным", callback_data="send_to_selected")],
                [InlineKeyboardButton("Отправить всем", callback_data="send_to_all")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Выберите метод отправки:",
                reply_markup=reply_markup
            )
            context.user_data['selenium_message_id'] = message.message_id

            context.user_data['chat_titles'] = chat_titles
            context.user_data['user_message'] = user_message
            context.user_data['waiting_for_input'] = True

            cleanup_photos(photos_folder)

    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала войдите в аккаунт WhatsApp")
        driver.quit()
        delete_user_data_after_nologging(user_id)

async def send_to_selected_chats(update, context) -> None:
    user_message = context.user_data['user_message']
    media_paths = context.user_data.get('media_paths', [])
    driver = context.user_data.get('driver')

    while context.user_data.get('waiting_for_input', False):
        await asyncio.sleep(1)

    selected_chats = update.message.text.split(',')

    for chat_title in selected_chats:
        chat_title = chat_title.strip()
        try:
            search_box = driver.find_element(By.CSS_SELECTOR, 'div[role="textbox"]')
            search_box.clear()
            search_box.click()
            search_box.send_keys(chat_title)
            WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.CSS_SELECTOR, 'div[role="listitem"]')))
            actions = ActionChains(driver)
            actions.send_keys(Keys.ENTER)
            actions.perform()
            for media_path in media_paths:
                if os.path.exists(media_path[1]):
                    p_button = WebDriverWait(driver, 30).until(
                        ec.element_to_be_clickable((By.XPATH, '//span[@data-icon="plus"]'))
                    )
                    p_button.click()
                    WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"][accept="image/*,video/mp4,video/3gpp,video/quicktime"]')))
                    upload_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"][accept="image/*,video/mp4,video/3gpp,video/quicktime"]')
                    upload_input.send_keys(media_path[1])
                    await asyncio.sleep(3)
                    WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.XPATH, '//span[@data-icon="send"]')))
                    send_button = WebDriverWait(driver, 30).until(
                        ec.element_to_be_clickable((By.XPATH, '//span[@data-icon="send"]'))
                    )
                    await asyncio.sleep(5)
                    send_button.click()
            WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.XPATH, '//div[@role="textbox" and @aria-placeholder="Введите сообщение"]')))
            needed_textbox = driver.find_element(By.XPATH,'//div[@role="textbox" and @aria-placeholder="Введите сообщение"]')
            message_box = needed_textbox
            await asyncio.sleep(3)
            actions = ActionChains(driver)
            actions.click(message_box)
            actions.send_keys(user_message)
            actions.send_keys(Keys.ENTER)
            actions.perform()
            await asyncio.sleep(3)
            await context.bot.send_message(chat_id=update.effective_chat.id,text="Сообщение отправлено в чат: {}".format(chat_title))
        except Exception as e:
            print(e)
            await context.bot.send_message(chat_id=update.effective_chat.id,text="У вас нет доступа к чату: {}".format(chat_title))
            driver.execute_script("location.reload();")
            try:
                WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.CSS_SELECTOR, 'div[role="textbox"]')))
            except Exception as wait_exception:
                print(f"Ошибка ожидания загрузки страницы: {wait_exception}")
            continue

    driver.quit()
    media_paths.clear()

    await cleanup_temp_directory(context.user_data['user_id'], 'temp')
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Успешно выполнено!")

async def send_to_all_chats(update: Update, context: CallbackContext) -> None:
    user_message = context.user_data['user_message']
    media_paths = context.user_data.get('media_paths', [])
    driver = context.user_data.get('driver')

    chat_titles = context.user_data.get('chat_titles', [])

    for chat_title in chat_titles:
        try:
            search_box = driver.find_element(By.CSS_SELECTOR, 'div[role="textbox"]')
            search_box.clear()
            search_box.click()
            search_box.send_keys(chat_title)
            WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.CSS_SELECTOR, 'div[role="listitem"]')))
            actions = ActionChains(driver)
            actions.send_keys(Keys.ENTER)
            actions.perform()
            for media_path in media_paths:
                if os.path.exists(media_path[1]):
                    p_button = WebDriverWait(driver, 30).until(
                        ec.element_to_be_clickable((By.XPATH, '//span[@data-icon="plus"]'))
                    )
                    p_button.click()
                    WebDriverWait(driver, 10).until(ec.presence_of_element_located(
                        (By.CSS_SELECTOR, 'input[type="file"][accept="image/*,video/mp4,video/3gpp,video/quicktime"]')))
                    upload_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"][accept="image/*,video/mp4,video/3gpp,video/quicktime"]')
                    upload_input.send_keys(media_path[1])
                    await asyncio.sleep(3)
                    WebDriverWait(driver, 10).until(
                        ec.presence_of_element_located((By.XPATH, '//span[@data-icon="send"]')))
                    send_button = WebDriverWait(driver, 30).until(
                        ec.element_to_be_clickable((By.XPATH, '//span[@data-icon="send"]'))
                    )
                    await asyncio.sleep(5)
                    send_button.click()
            WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.XPATH, '//div[@role="textbox" and @aria-placeholder="Введите сообщение"]')))
            needed_textbox = driver.find_element(By.XPATH,'//div[@role="textbox" and @aria-placeholder="Введите сообщение"]')
            message_box = needed_textbox
            await asyncio.sleep(3)
            actions = ActionChains(driver)
            actions.click(message_box)
            actions.send_keys(user_message)
            actions.send_keys(Keys.ENTER)
            actions.perform()
            print(chat_title)
            await asyncio.sleep(3)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Сообщение отправлено в чат: {}".format(chat_title))
        except Exception:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="У вас нет доступа к чату: {}".format(chat_title))
            driver.execute_script("location.reload();")
            try:
                WebDriverWait(driver, 10).until(ec.presence_of_element_located((By.CSS_SELECTOR, 'div[role="textbox"]')))
            except Exception as wait_exception:
                print(f"Ошибка ожидания загрузки страницы: {wait_exception}")
            continue

    context.user_data['waiting_for_input'] = False
    driver.quit()

    await cleanup_temp_directory(context.user_data['user_id'], 'temp')
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Успешно выполнено!")

async def handle_user_input(update, context) -> None:
    if context.user_data.get('waiting_for_input', False):
        context.user_data['waiting_for_input'] = False
        await send_to_selected_chats(update, context)

async def handle_payment_callbacks(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    print(f"Payment callback received: {query.data}")
    try:
        await query.answer()
        if query.data.startswith("cancel_payment_"):
            payment_id = query.data.split("_")[-1]
            if payment_id == context.user_data.get('payment_id'):
                context.user_data['payment_cancelled'] = True
                context.user_data.pop('payment_id', None)

                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data.get('payment_message_id'),
                        reply_markup=None
                    )
                except Exception as e:
                    print(f"Error removing payment button: {e}")

                context.user_data.pop('payment_message_id', None)

                await payment_cancelled(update, context, payment_id)

            else:
                await payment_cancelled(update, context, payment_id)
    except Exception as e:
        print(f"Error in payment callback: {e}")

async def callback_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    print(f"Получен callback query: {query.data}")

    try:
        await query.answer()
        if query.data == "send_to_selected":
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Введите названия чатов через запятую и немного подождите:"
            )
            context.user_data['method'] = 'selected'
            try:
                await query.message.delete()
            except:
                pass

        elif query.data == "send_to_all":
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Подождите немного"
            )
            context.user_data['method'] = 'all'
            try:
                await query.message.delete()
            except:
                pass
            await send_to_all_chats(update, context)

    except Exception as e:
        print(f"Общая ошибка в обработке callback: {e}")
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла ошибка. Попробуйте снова."
            )
        except Exception as msg_error:
            print(f"Ошибка при отправке сообщения об ошибке: {msg_error}")

async def save_file(file, user_id, media_paths, temp_dir, file_type):
    working_dir = get_working_dir()
    user_temp_dir = os.path.join(working_dir, temp_dir, str(user_id))
    os.makedirs(user_temp_dir, exist_ok=True)

    media_bytes = await file.download_as_bytearray()
    file_hash = hashlib.md5(media_bytes).hexdigest()

    if not any(file_hash == path[0] for path in media_paths):
        unique_id = str(uuid.uuid4())
        extension = 'jpg' if file_type == 'photo' else 'mp4'
        media_path = os.path.join(user_temp_dir, f"{user_id}_{file_type}_{unique_id}.{extension}")
        absolute_media_path = os.path.abspath(media_path)
        print(f"media_path type: {type(media_path)}, value: {media_path}")

        with open(media_path, "wb") as f:
            f.write(media_bytes)

        media_paths.append((file_hash, absolute_media_path))

async def handle_media(update: Update, context: CallbackContext) -> None:
    user_id = context.user_data['user_id']
    temp_dir = 'temp'

    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    media_paths = context.user_data.get('media_paths', [])
    message_id = update.message.message_id

    if 'processed_messages' in context.user_data and message_id in context.user_data['processed_messages']:
        return

    if update.message.document and update.message.document.mime_type.startswith('image/'):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Пожалуйста, отправьте фото как фотографию, а не как файл"
        )
        return

    try:
        if update.message.photo:
            largest_photo = update.message.photo[-1]
            file_info = await largest_photo.get_file()
            if file_info.file_path.endswith(('.jpg', '.jpeg', '.png')):
                if file_info.file_size <= 20 * 1024 * 1024:
                    await save_file(file_info, user_id, media_paths, temp_dir, 'photo')
                    file_name = f"{user_id}_photo_{file_info.file_id}.jpg"
                    if 'file_message_id' in context.user_data:
                        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['file_message_id'])
                    new_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Файл получен: {file_name} "
                                                                                                        f"\n-----------------------"
                                                                                                        f"\nВведите сообщение, которое хотите отправить. Вы также можете выбрать еще фото или видео для отправки")
                    context.user_data['file_message_id'] = new_message.message_id
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id,text="Файл слишком большой, выберите другой")
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="Неподдерживаемый формат файла, отправьте JPG или PNG")
    except BadRequest:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Файл слишком большой, выберите другой")

    try:
        if update.message.video:
            video = update.message.video
            file_info = await video.get_file()
            if file_info.file_path.endswith(('.mp4', '.mov')):
                if file_info.file_size <= 200 * 1024 * 1024:
                    await save_file(file_info, user_id, media_paths, temp_dir, 'video')
                    file_name = f"{user_id}_video_{file_info.file_id}.mp4"
                    if 'file_message_id' in context.user_data:
                        await context.bot.delete_message(chat_id=update.effective_chat.id,message_id=context.user_data['file_message_id'])
                    new_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Файл получен: {file_name} "
                                                                                                        f"\n-----------------------"
                                                                                                        f"\nВведите сообщение, которое хотите отправить. Вы также можете выбрать еще фото или видео для отправки")
                    context.user_data['file_message_id'] = new_message.message_id
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id,text="Файл слишком большой, выберите другой")
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="Неподдерживаемый формат файла, отправьте MOV или MP4")
    except BadRequest:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Файл слишком большой, выберите другой")

    if media_paths:
        print(f"media_paths type: {type(media_paths)}, value: {media_paths}")

        if 'processed_messages' not in context.user_data:
            context.user_data['processed_messages'] = []
        context.user_data['processed_messages'].append(message_id)

    context.user_data['media_paths'] = media_paths

def cleanup_photos(folder):
    try:
        for file in os.listdir(folder):
            os.remove(os.path.join(folder, file))
        os.rmdir(folder)
    except Exception as e:
        print(f"Ошибка при очистке папок: {e}")

async def cleanup_temp_directory(user_id, temp_dir='temp'):
    working_dir = get_working_dir()
    user_temp_dir = os.path.join(working_dir, temp_dir, str(user_id))
    if os.path.exists(user_temp_dir):
        for filename in os.listdir(user_temp_dir):
            file_path = os.path.join(user_temp_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Ошибка при удалении {file_path}: {e}")
        os.rmdir(user_temp_dir)

async def delete_user_data(update: Update, context: CallbackContext) -> None:
    try:
        user_id = context.user_data['user_id']
        working_dir = get_working_dir()
        user_profile = os.path.join(working_dir, "users", str(user_id))

        if os.path.exists(user_profile):
            shutil.rmtree(user_profile)
            await update.message.reply_text('Вы успешно вышли из аккаунта')
        else:
            await update.message.reply_text('Мы не нашли аккаунт WhatsApp')

    except KeyError:
        await update.message.reply_text('Перед тем как начать работу, запустите сессию')

def delete_user_data_after_nologging(user_id: int):
    try:
        working_dir = get_working_dir()
        user_profile = os.path.join(working_dir, "users", str(user_id))

        if os.path.exists(user_profile):
            shutil.rmtree(user_profile)
        return True

    except Exception:
        return False

def get_config_path():
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
    return os.path.join(exe_dir, 'config.json')

def get_default_config_path():
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, 'config.json')

def ensure_config_exists():
    config_path = get_config_path()
    if not os.path.exists(config_path):
        default_config = get_default_config_path()
        shutil.copy2(default_config, config_path)
    return config_path

def get_working_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def ensure_folders_exist():
    working_dir = get_working_dir()
    folders = ['users', 'photos', 'temp']
    
    created_paths = {}
    for folder in folders:
        folder_path = os.path.join(working_dir, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        created_paths[folder] = folder_path
    
    return created_paths

config_path = ensure_config_exists()
with open(config_path, 'r') as f:
    config = json.load(f)

paths = ensure_folders_exist()

conv_handler = ConversationHandler (
    entry_points=[CommandHandler("whatsapp", ws_auto)],
    states={
        1: [MessageHandler(filters.TEXT, get_message)],
    },
    fallbacks=[],
)

app = ApplicationBuilder()\
    .token(config['api_token'])\
    .build()

app.add_handler(CallbackQueryHandler(handle_payment_callbacks, pattern="^cancel_payment_"))
app.add_handler(CallbackQueryHandler(callback_handler, pattern="^(send_to_selected|send_to_all)$"))

app.add_handler(conv_handler)
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("pay", payment))
app.add_handler(CommandHandler("whatsapp_auth", auth))
app.add_handler(CommandHandler("whatsapp_exit", delete_user_data))
app.add_handler(CommandHandler("subscription", check_subscription))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_media))

app.run_polling()
