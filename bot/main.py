import logging
import os

from dotenv import load_dotenv

from plugin_manager import PluginManager
from openai_helper import OpenAIHelper, default_max_tokens, are_functions_available
from telegram_bot import ChatGPTTelegramBot

from telegram.ext import Application


def main():
    load_dotenv()

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    required_values = ['TELEGRAM_BOT_TOKEN', 'OPENAI_API_KEY']
    missing_values = [value for value in required_values if os.environ.get(value) is None]
    if len(missing_values) > 0:
        logging.error(f'Missing env values: {", ".join(missing_values)}')
        exit(1)

    model = os.environ.get('OPENAI_MODEL', 'gpt-4o')
    functions_available = are_functions_available(model=model)
    max_tokens_default = default_max_tokens(model=model)

    openai_config = {
        'api_key': os.environ['OPENAI_API_KEY'],
        'model': model,
        'stream': os.environ.get('STREAM', 'true').lower() == 'true',
        'enable_functions': os.environ.get('ENABLE_FUNCTIONS', str(functions_available)).lower() == 'true',
        'bot_language': os.environ.get('BOT_LANGUAGE', 'ru'),
        # ... остальные параметры ...
    }

    telegram_config = {
        'token': os.environ['TELEGRAM_BOT_TOKEN'],
        'bot_language': os.environ.get('BOT_LANGUAGE', 'ru'),
        # ... другие параметры ...
    }

    plugin_config = {
        'plugins': os.environ.get('PLUGINS', 'ddg_image_search').split(',')
    }

    # Создаём компоненты
    plugin_manager = PluginManager(config=plugin_config)
    openai_helper = OpenAIHelper(config=openai_config, plugin_manager=plugin_manager)
    bot = ChatGPTTelegramBot(config=telegram_config, openai=openai_helper)

    # Создаём Application
    application = Application.builder().token(telegram_config['token']).build()

    # Добавляем команды
    application.add_handler(CommandHandler('reset', bot.reset))
    application.add_handler(CommandHandler("image_search", bot.image_search))
    application.add_handler(CommandHandler('help', bot.help))
    application.add_handler(CommandHandler('image', bot.image))
    application.add_handler(CommandHandler('tts', bot.tts))
    application.add_handler(CommandHandler('start', bot.help))
    application.add_handler(CommandHandler('stats', bot.stats))
    application.add_handler(CommandHandler('resend', bot.resend))

    # ✅ Админ команды
    application.add_handler(CommandHandler('admin', bot.admin_panel))
    application.add_handler(CallbackQueryHandler(bot.handle_admin_buttons))
    application.add_handler(MessageHandler(filters.TEXT & filters.REPLY, bot.block_user_handler))

    # Запуск
    application.run_polling()


if __name__ == '__main__':
    main()
