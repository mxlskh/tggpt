import logging
import os
from dotenv import load_dotenv
from plugin_manager import PluginManager
from openai_helper import OpenAIHelper, default_max_tokens, are_functions_available
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from collections import defaultdict

def main():
    # Загружаем переменные из .env
    load_dotenv()

    # Настройка логирования
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Проверка обязательных переменных окружения
    required_values = ['TELEGRAM_BOT_TOKEN', 'OPENAI_API_KEY']
    missing_values = [value for value in required_values if os.environ.get(value) is None]
    if len(missing_values) > 0:
        logging.error(f'The following environment values are missing in your .env: {", ".join(missing_values)}')
        exit(1)

    # Конфигурация для OpenAI
    model = os.environ.get('OPENAI_MODEL', 'gpt-4o')
    functions_available = are_functions_available(model=model)
    max_tokens_default = default_max_tokens(model=model)
    openai_config = {
        'api_key': os.environ['OPENAI_API_KEY'],
        'show_usage': os.environ.get('SHOW_USAGE', 'false').lower() == 'true',
        'stream': os.environ.get('STREAM', 'true').lower() == 'true',
        'proxy': os.environ.get('PROXY', None) or os.environ.get('OPENAI_PROXY', None),
        'max_history_size': int(os.environ.get('MAX_HISTORY_SIZE', 15)),
        'max_conversation_age_minutes': int(os.environ.get('MAX_CONVERSATION_AGE_MINUTES', 180)),
        'assistant_prompt': os.environ.get('ASSISTANT_PROMPT', 'You are a helpful assistant.'),
        'max_tokens': int(os.environ.get('MAX_TOKENS', max_tokens_default)),
        'n_choices': int(os.environ.get('N_CHOICES', 1)),
        'temperature': float(os.environ.get('TEMPERATURE', 1.0)),
        'image_model': os.environ.get('IMAGE_MODEL', 'dall-e-3'),
        'image_quality': os.environ.get('IMAGE_QUALITY', 'HD'),
        'image_style': os.environ.get('IMAGE_STYLE', 'natural'),
        'image_size': os.environ.get('IMAGE_SIZE', '1024x1024'),
        'model': model,
        'enable_functions': os.environ.get('ENABLE_FUNCTIONS', str(functions_available)).lower() == 'true',
        'functions_max_consecutive_calls': int(os.environ.get('FUNCTIONS_MAX_CONSECUTIVE_CALLS', 10)),
        'presence_penalty': float(os.environ.get('PRESENCE_PENALTY', 0.0)),
        'frequency_penalty': float(os.environ.get('FREQUENCY_PENALTY', 0.0)),
        'bot_language': os.environ.get('BOT_LANGUAGE', 'ru'),
        'show_plugins_used': os.environ.get('SHOW_PLUGINS_USED', 'false').lower() == 'true',
        'whisper_prompt': os.environ.get('WHISPER_PROMPT', ''),
        'vision_model': os.environ.get('VISION_MODEL', 'gpt-4o'),
        'enable_vision_follow_up_questions': os.environ.get('ENABLE_VISION_FOLLOW_UP_QUESTIONS', 'true').lower() == 'true',
        'vision_prompt': os.environ.get('VISION_PROMPT', 'What is in this image'),
        'vision_detail': os.environ.get('VISION_DETAIL', 'auto'),
        'vision_max_tokens': int(os.environ.get('VISION_MAX_TOKENS', '300')),
        'tts_model': os.environ.get('TTS_MODEL', 'tts-1-hd'),
        'tts_voice': os.environ.get('TTS_VOICE', 'alloy'),
    }

    if openai_config['enable_functions'] and not functions_available:
        logging.error(f'ENABLE_FUNCTIONS is set to true, but the model {model} does not support it. '
                        'Please set ENABLE_FUNCTIONS to false or use a model that supports it.')
        exit(1)

    # Конфигурация для Telegram
    telegram_config = {
        'token': os.environ['TELEGRAM_BOT_TOKEN'],
        'admin_user_ids': os.environ.get('ADMIN_USER_IDS', '-').split(','),
        'allowed_user_ids': os.environ.get('ALLOWED_TELEGRAM_USER_IDS', '*'),
    }

    # Список пользователей
    users = defaultdict(dict)
    pending_requests = set()  # Множество для заявок на вступление
    blocked_users = set()  # Множество для заблокированных пользователей

    # Функция для проверки прав администратора
    def is_admin(user_id):
        return str(user_id) in telegram_config['admin_user_ids']

    # Функция для создания Inline клавиатуры
    def admin_keyboard():
        keyboard = [
            [InlineKeyboardButton("Просмотр пользователей", callback_data='view_users')],
            [InlineKeyboardButton("Просмотр заявок", callback_data='view_pending_requests')],
            [InlineKeyboardButton("Блокировка пользователей", callback_data='block_user')],
        ]
        return InlineKeyboardMarkup(keyboard)

    # Обработка нажатия кнопок
    def handle_admin_command(update: Update, context: CallbackContext):
        query = update.callback_query
        user_id = update.effective_user.id

        if is_admin(user_id):
            if query.data == 'view_users':
                query.answer(text=view_users())
            elif query.data == 'view_pending_requests':
                query.answer(text=view_pending_requests())
            elif query.data == 'block_user':
                query.answer(text="Введите ID пользователя для блокировки.")
        else:
            query.answer(text="У вас нет прав администратора.")

    # Функции для администрирования
    def view_users():
        return "\n".join([f"User {user_id}" for user_id in users])

    def view_pending_requests():
        return "\n".join([f"Request from {user_id}" for user_id in pending_requests])

    # Создаем Updater и Dispatcher
    updater = Updater(telegram_config['token'], use_context=True)
    dispatcher = updater.dispatcher

    # Регистрация обработчиков команд и кнопок
    dispatcher.add_handler(CallbackQueryHandler(handle_admin_command))

    # Запуск бота
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
