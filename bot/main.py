import logging
import os
from dotenv import load_dotenv

from database import Database
from plugin_manager import PluginManager
from openai_helper import OpenAIHelper, default_max_tokens, are_functions_available
from telegram_bot import ChatGPTTelegramBot


def main():
    # Load .env
    load_dotenv()

    # Setup logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    required_values = ['TELEGRAM_BOT_TOKEN', 'OPENAI_API_KEY']
    missing_values = [val for val in required_values if not os.environ.get(val)]
    if missing_values:
        logging.error(f'Missing .env variables: {", ".join(missing_values)}')
        exit(1)

    model = os.getenv('OPENAI_MODEL', 'gpt-4o')
    functions_available = are_functions_available(model=model)
    max_tokens_default = default_max_tokens(model)

    admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
    admin_user_ids = [int(uid.strip()) for uid in admin_ids_str.split(',') if uid.strip().isdigit()]
    logging.info(f"[CONFIG] Loaded admin IDs: {admin_user_ids}")

    openai_config = {
        'api_key': os.environ['OPENAI_API_KEY'],
        'stream': os.getenv('STREAM', 'true').lower() == 'true',
        'show_usage': os.getenv('SHOW_USAGE', 'false').lower() == 'true',
        'proxy': os.getenv('OPENAI_PROXY') or os.getenv('PROXY'),
        'max_history_size': int(os.getenv('MAX_HISTORY_SIZE', 15)),
        'max_conversation_age_minutes': int(os.getenv('MAX_CONVERSATION_AGE_MINUTES', 180)),
        'assistant_prompt': os.getenv('ASSISTANT_PROMPT', 'You are a helpful assistant.'),
        'max_tokens': int(os.getenv('MAX_TOKENS', max_tokens_default)),
        'temperature': float(os.getenv('TEMPERATURE', 1.0)),
        'n_choices': int(os.getenv('N_CHOICES', 1)),
        'enable_functions': os.getenv('ENABLE_FUNCTIONS', str(functions_available)).lower() == 'true',
        'functions_max_consecutive_calls': int(os.getenv('FUNCTIONS_MAX_CONSECUTIVE_CALLS', 10)),
        'presence_penalty': float(os.getenv('PRESENCE_PENALTY', 0.0)),
        'frequency_penalty': float(os.getenv('FREQUENCY_PENALTY', 0.0)),
        'model': model,
        'image_model': os.getenv('IMAGE_MODEL', 'dall-e-3'),
        'image_quality': os.getenv('IMAGE_QUALITY', 'HD'),
        'image_style': os.getenv('IMAGE_STYLE', 'natural'),
        'image_size': os.getenv('IMAGE_SIZE', '1024x1024'),
        'vision_model': os.getenv('VISION_MODEL', 'gpt-4o'),
        'enable_vision_follow_up_questions': os.getenv('ENABLE_VISION_FOLLOW_UP_QUESTIONS', 'true').lower() == 'true',
        'vision_prompt': os.getenv('VISION_PROMPT', 'What is in this image'),
        'vision_detail': os.getenv('VISION_DETAIL', 'auto'),
        'vision_max_tokens': int(os.getenv('VISION_MAX_TOKENS', '300')),
        'bot_language': os.getenv('BOT_LANGUAGE', 'ru'),
        'tts_model': os.getenv('TTS_MODEL', 'tts-1'),
        'tts_voice': os.getenv('TTS_VOICE', 'alloy'),
        'tts_prices': [float(p) for p in os.getenv('TTS_PRICES', '0.015,0.030').split(',')],
        'transcription_price': float(os.getenv('TRANSCRIPTION_PRICE', 0.006)),
        'enable_image_generation': os.getenv('ENABLE_IMAGE_GENERATION', 'true').lower() == 'true',
        'enable_transcription': os.getenv('ENABLE_TRANSCRIPTION', 'true').lower() == 'true',
        'enable_vision': os.getenv('ENABLE_VISION', 'true').lower() == 'true',
        'enable_tts_generation': os.getenv('ENABLE_TTS_GENERATION', 'true').lower() == 'true',
        'bot_language': os.getenv('BOT_LANGUAGE', 'ru'),
    }

    telegram_config = {
        'token': os.environ['TELEGRAM_BOT_TOKEN'],
        'admin_user_ids': admin_user_ids,
        'proxy': os.getenv('TELEGRAM_PROXY', None),
        'budget_period': os.getenv('BUDGET_PERIOD', 'monthly'),
        'user_budgets': os.getenv('USER_BUDGETS', '*'),
        'guest_budget': float(os.getenv('GUEST_BUDGET', '100.0')),
        'enable_quoting': os.getenv('ENABLE_QUOTING', 'true').lower() == 'true',
        'voice_reply_transcript': os.getenv('VOICE_REPLY_WITH_TRANSCRIPT_ONLY', 'false').lower() == 'true',
        'voice_reply_prompts': os.getenv('VOICE_REPLY_PROMPTS', '').split(';'),
        'ignore_group_transcriptions': os.getenv('IGNORE_GROUP_TRANSCRIPTIONS', 'true').lower() == 'true',
        'ignore_group_vision': os.getenv('IGNORE_GROUP_VISION', 'true').lower() == 'true',
        'group_trigger_keyword': os.getenv('GROUP_TRIGGER_KEYWORD', ''),
        'token_price': float(os.getenv('TOKEN_PRICE', 0.002)),
        'image_prices': [float(p) for p in os.getenv('IMAGE_PRICES', '0.016,0.018,0.02').split(',')],
        'vision_token_price': float(os.getenv('VISION_TOKEN_PRICE', '0.01')),
        'image_receive_mode': os.getenv('IMAGE_FORMAT', 'photo'),
        'tts_prices': [float(p) for p in os.getenv('TTS_PRICES', '0.015,0.030').split(',')],
    }

    plugin_config = {
        'plugins': os.getenv('PLUGINS', 'ddg_image_search').split(','),
    }

    plugin_manager = PluginManager(config=plugin_config)
    openai_helper = OpenAIHelper(config=openai_config, plugin_manager=plugin_manager)
    telegram_bot = ChatGPTTelegramBot(config=telegram_config, openai=openai_helper)
    telegram_bot.run()


if __name__ == '__main__':
    main()
