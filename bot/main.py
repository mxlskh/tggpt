import logging
import os
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from plugin_manager import PluginManager
from openai_helper import OpenAIHelper, default_max_tokens, are_functions_available
from telegram_bot import ChatGPTTelegramBot

def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    markup = ReplyKeyboardMarkup(
        [['👩‍🎓 Ученик', '👨‍🏫 Преподаватель']],
        resize_keyboard=True, one_time_keyboard=True
    )
    update.message.reply_text("Выбери свою роль:", reply_markup=markup)
    user_state[chat_id] = {'step': 'role'}

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    text = update.message.text

    if chat_id not in user_state:
        update.message.reply_text("Пожалуйста, начни с команды /start.")
        return

    state = user_state[chat_id]

    if state['step'] == 'role':
        if text in ['👩‍🎓 Ученик', '👨‍🏫 Преподаватель']:
            state['role'] = text
            state['step'] = 'language'

            markup = ReplyKeyboardMarkup(
                [['🇬🇧 Английский', '🇩🇪 Немецкий']],
                resize_keyboard=True, one_time_keyboard=True
            )
            update.message.reply_text("Выбери язык обучения:", reply_markup=markup)
        else:
            update.message.reply_text("Пожалуйста, выбери роль из предложенных.")

    elif state['step'] == 'language':
        if text in ['🇬🇧 Английский', '🇩🇪 Немецкий', '🇫🇷 Французский', '🇨🇳 Китайский']:
            state['language'] = text
            state['step'] = 'goal'

            markup = ReplyKeyboardMarkup(
                [['📚 Грамматика', '📖 Чтение'], ['👂 Аудирование', '🗣 Разговорная практика']],
                resize_keyboard=True, one_time_keyboard=True
            )
            update.message.reply_text("Выбери цель обучения:", reply_markup=markup)
        else:
            update.message.reply_text("Пожалуйста, выбери язык из списка.")

    elif state['step'] == 'goal':
        state['goal'] = text
        role = state.get('role')
        language = state.get('language')
        goal = state.get('goal')

        update.message.reply_text(
            f"✅ Готово!\n\nРоль: {role}\nЯзык: {language}\nЦель: {goal}\n\nТы можешь начать работу, используя /help или другие команды."
        )

        user_state.pop(chat_id)  # Сбросить состояние

def main():
    # Read .env file
    load_dotenv()

    # Setup logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Check if the required environment variables are set
    required_values = ['TELEGRAM_BOT_TOKEN', 'OPENAI_API_KEY']
    missing_values = [value for value in required_values if os.environ.get(value) is None]
    if len(missing_values) > 0:
        logging.error(f'The following environment values are missing in your .env: {", ".join(missing_values)}')
        exit(1)

    # Setup configurations
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
        'image_model': os.environ.get('IMAGE_MODEL', 'dall-e-2'),
        'image_quality': os.environ.get('IMAGE_QUALITY', 'standard'),
        'image_style': os.environ.get('IMAGE_STYLE', 'vivid'),
        'image_size': os.environ.get('IMAGE_SIZE', '512x512'),
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
        'tts_model': os.environ.get('TTS_MODEL', 'tts-1'),
        'tts_voice': os.environ.get('TTS_VOICE', 'alloy'),
    }

    if openai_config['enable_functions'] and not functions_available:
        logging.error(f'ENABLE_FUNCTIONS is set to true, but the model {model} does not support it. '
                        'Please set ENABLE_FUNCTIONS to false or use a model that supports it.')
        exit(1)
    if os.environ.get('MONTHLY_USER_BUDGETS') is not None:
        logging.warning('The environment variable MONTHLY_USER_BUDGETS is deprecated. '
                        'Please use USER_BUDGETS with BUDGET_PERIOD instead.')
    if os.environ.get('MONTHLY_GUEST_BUDGET') is not None:
        logging.warning('The environment variable MONTHLY_GUEST_BUDGET is deprecated. '
                        'Please use GUEST_BUDGET with BUDGET_PERIOD instead.')

    telegram_config = {
        'token': os.environ['TELEGRAM_BOT_TOKEN'],
        'admin_user_ids': os.environ.get('ADMIN_USER_IDS', '-'),
        'allowed_user_ids': os.environ.get('ALLOWED_TELEGRAM_USER_IDS', '*'),
        'enable_quoting': os.environ.get('ENABLE_QUOTING', 'true').lower() == 'true',
        'enable_image_generation': os.environ.get('ENABLE_IMAGE_GENERATION', 'true').lower() == 'true',
        'enable_transcription': os.environ.get('ENABLE_TRANSCRIPTION', 'true').lower() == 'true',
        'enable_vision': os.environ.get('ENABLE_VISION', 'true').lower() == 'true',
        'enable_tts_generation': os.environ.get('ENABLE_TTS_GENERATION', 'true').lower() == 'true',
        'budget_period': os.environ.get('BUDGET_PERIOD', 'monthly').lower(),
        'user_budgets': os.environ.get('USER_BUDGETS', os.environ.get('MONTHLY_USER_BUDGETS', '*')),
        'guest_budget': float(os.environ.get('GUEST_BUDGET', os.environ.get('MONTHLY_GUEST_BUDGET', '100.0'))),
        'stream': os.environ.get('STREAM', 'true').lower() == 'true',
        'proxy': os.environ.get('PROXY', None) or os.environ.get('TELEGRAM_PROXY', None),
        'voice_reply_transcript': os.environ.get('VOICE_REPLY_WITH_TRANSCRIPT_ONLY', 'false').lower() == 'true',
        'voice_reply_prompts': os.environ.get('VOICE_REPLY_PROMPTS', '').split(';'),
        'ignore_group_transcriptions': os.environ.get('IGNORE_GROUP_TRANSCRIPTIONS', 'true').lower() == 'true',
        'ignore_group_vision': os.environ.get('IGNORE_GROUP_VISION', 'true').lower() == 'true',
        'group_trigger_keyword': os.environ.get('GROUP_TRIGGER_KEYWORD', ''),
        'token_price': float(os.environ.get('TOKEN_PRICE', 0.002)),
        'image_prices': [float(i) for i in os.environ.get('IMAGE_PRICES', "0.016,0.018,0.02").split(",")],
        'vision_token_price': float(os.environ.get('VISION_TOKEN_PRICE', '0.01')),
        'image_receive_mode': os.environ.get('IMAGE_FORMAT', "photo"),
        'tts_model': os.environ.get('TTS_MODEL', 'tts-1'),
        'tts_prices': [float(i) for i in os.environ.get('TTS_PRICES', "0.015,0.030").split(",")],
        'transcription_price': float(os.environ.get('TRANSCRIPTION_PRICE', 0.006)),
        'bot_language': os.environ.get('BOT_LANGUAGE', 'ru'),
    }

    plugin_config = {
        'plugins': os.environ.get('PLUGINS', '').split(',')
    }

    plugin_manager = PluginManager(config=plugin_config)
    openai_helper = OpenAIHelper(config=openai_config, plugin_manager=plugin_manager)
    telegram_bot = ChatGPTTelegramBot(config=telegram_config, openai=openai_helper)
    
    # Adding message handlers for role selection
    updater = Updater(token=telegram_config['token'], use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(MessageHandler(Filters.text, handle_message))

    telegram_bot.run()

if __name__ == '__main__':
    user_state = {}  # Store user states (role, language, goal)
    main()
