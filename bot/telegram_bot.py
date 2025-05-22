from __future__ import annotations
from telegram import ReplyKeyboardMarkup

import asyncio
import logging
import os
import io
import json
import logging
import requests

from uuid import uuid4
from io import BytesIO
from telegram import constants
from telegram import BotCommandScopeAllGroupChats, Update, constants
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle
from telegram import InputTextMessageContent, BotCommand
from telegram.error import RetryAfter, TimedOut, BadRequest
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, \
    filters, InlineQueryHandler, CallbackQueryHandler, Application, ContextTypes, CallbackContext

from pydub import AudioSegment
from PIL import Image

from utils import is_group_chat, get_thread_id, message_text, wrap_with_indicator, split_into_chunks, \
    edit_message_with_retry, get_stream_cutoff_values, is_allowed, get_remaining_budget, is_admin, is_within_budget, \
    get_reply_to_message_id, add_chat_request_to_usage_tracker, error_handler, is_direct_result, handle_direct_result, \
    cleanup_intermediate_files

from openai_helper import OpenAIHelper, localized_text
from usage_tracker import UsageTracker

from datetime import datetime
from supabase_client import SupabaseClient



class ChatGPTTelegramBot:

    async def check_access(self, update: Update) -> bool:
        user_id = update.effective_user.id
        # используем готовый метод
        if not self.supabase.is_user_approved(user_id):
            await update.effective_message.reply_text(
                "⛔️ Доступ запрещён. Пожалуйста, подайте заявку и дождитесь одобрения администратора."
            )
            return False
        return True

    async def image_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_access(update):
            return  # Пользователь не одобрен — прерываем выполнение
        logging.info("⚙️ Вызван image_search")
        logging.info(f"📨 Сообщение: {update.message.text}")

        query = update.message.text.partition(' ')[2]
        logging.info(f"🔍 Извлечён запрос: {query}")
        if not query:
            await update.message.reply_text(
                "❗️Укажи, что искать: `/image_search кот в очках`",
                parse_mode=constants.ParseMode.MARKDOWN
            )
            return

        arguments = {
            "query": query,
            "type": "photo",
            "region": "wt-wt"
        }

        try:
            result_raw = await self.openai.plugin_manager.call_function(
                function_name="search_images",
                helper=self.openai,
                arguments=json.dumps(arguments)
            )

            logging.info(f"📸 Результат от плагина: {result_raw}")
            result = json.loads(result_raw)
            image_url = result['direct_result']['value']

            #await update.message.reply_text(f"🔗 Найдено изображение: {image_url}")

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            response = requests.get(image_url, headers=headers)
            logging.info(f"📥 Статус ответа: {response.status_code}, длина: {len(response.content)} байт")

            if len(response.content) > 20 * 1024 * 1024:
                raise ValueError("❗️Файл слишком большой для отправки через Telegram")

            response.raise_for_status()

            image_data = BytesIO(response.content)
            image_data.name = "result.jpg"

            logging.info("📤 Отправляем изображение в Telegram")
            await update.message.reply_photo(photo=image_data)

        except Exception as e:
            logging.error(f"❌ Ошибка: {e}")
            await update.message.reply_text("😔 Не удалось загрузить или отправить изображение.")

    def __init__(self, config: dict, openai: OpenAIHelper, supabase):
        """
        Initializes the bot with the given configuration and GPT bot object.
        :param config: A dictionary containing the bot configuration
        :param openai: OpenAIHelper object
        """
        self.supabase = SupabaseClient()
        self.config = config
        self.openai = openai
        self.supabase = supabase
        self.db = SupabaseClient()
        bot_language = self.config['bot_language']

        self.commands = [
            BotCommand(command='help', description=localized_text('help_description', bot_language)),
            BotCommand(command='reset', description=localized_text('reset_description', bot_language)),
            BotCommand(command='stats', description=localized_text('stats_description', bot_language)),
            BotCommand(command='resend', description=localized_text('resend_description', bot_language))
        ]

        # Команды по фичам
        if self.config.get('enable_image_generation', False):
            self.commands.append(BotCommand(command='image', description=localized_text('image_description', bot_language)))

        if self.config.get('enable_tts_generation', False):
            self.commands.append(BotCommand(command='tts', description=localized_text('tts_description', bot_language)))

        self.group_commands = [BotCommand(
            command='chat', description=localized_text('chat_description', bot_language)
        )] + self.commands

        # Остальные переменные
        self.disallowed_message = localized_text('disallowed', bot_language)
        self.budget_limit_message = localized_text('budget_limit', bot_language)
        self.usage = {}
        self.last_message = {}
        self.inline_queries_cache = {}

        self.admin_user_ids = config.get("admin_user_ids", [])
        self.allowed_user_ids = config.get("allowed_user_ids", [])  # Возможно, больше не нужен
        self.DATA_DIR = "data"
        os.makedirs(self.DATA_DIR, exist_ok=True)

    def get_users_list_text(self):
        response = self.client.table("users").select("*").execute()
        users = response.data
        if not users:
            return "Пользователей нет."

        lines = []
        for user in users:
            uid = user.get("user_id")
            name = user.get("username") or user.get("name") or "Без имени"
            status = user.get("status", "участник")
            lines.append(f"{uid} — {name} ({status})")
        return "\n".join(lines)

    def get_requests_keyboard(self):
        response = self.client.table("join_requests").select("*").execute()
        requests = response.data
        if not requests:
            return "Заявок нет.", None

        text_lines = []
        keyboard = []
        for req in requests:
            uid = req.get("user_id")
            name = req.get("username") or req.get("name") or "Без имени"
            text_lines.append(f"{uid} — {name}")
            keyboard.append([
                InlineKeyboardButton("Одобрить", callback_data=f"approve_request_{uid}"),
                InlineKeyboardButton("Отклонить", callback_data=f"reject_request_{uid}")
            ])
        return "\n".join(text_lines), InlineKeyboardMarkup(keyboard)

    def get_blocked_users_text(self):
        response = self.client.table("blocked_users").select("user_id").execute()
        blocked = response.data
        if not blocked:
            return "Заблокированных пользователей нет."
        return "\n".join([str(user["user_id"]) for user in blocked])

    def add_join_request(self, user_id: int, username: str):
        self.client.table("join_requests").upsert({
            "user_id": user_id,
            "username": username
        }).execute()

    async def approve_request(self, user_id, username, bot):
        # Добавляем в users
        self.client.table("users").upsert({
            "user_id": user_id,
            "username": username,
            "status": "approved",
            "joined": str(datetime.now().date())
        }).execute()

        # Удаляем из join_requests
        self.client.table("join_requests").delete().eq("user_id", user_id).execute()

        try:
            await bot.send_message(
                chat_id=int(user_id),
                text="✅ Ваша заявка одобрена! Теперь вы можете использовать функционал бота."
            )
        except Exception as e:
            print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

    def reject_request(self, user_id):
        self.client.table("join_requests").delete().eq("user_id", user_id).execute()

    def block_user(self, user_id):
        self.client.table("blocked_users").upsert({"user_id": user_id}).execute()
        self.client.table("users").delete().eq("user_id", user_id).execute()

    def unblock_user(self, user_id):
        self.client.table("blocked_users").delete().eq("user_id", user_id).execute()

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids
    
    def format_usage_section(title, tokens, images, vision, tts, minutes, seconds, cost, config, lang):
        section = f"*{title}:*\n"
        section += f"{tokens} {localized_text('stats_tokens', lang)}\n"
        if config.get('enable_image_generation', False):
            section += f"{images} {localized_text('stats_images', lang)}\n"
        if config.get('enable_vision', False):
            section += f"{vision} {localized_text('stats_vision', lang)}\n"
        if config.get('enable_tts_generation', False):
            section += f"{tts} {localized_text('stats_tts', lang)}\n"
        section += (
            f"{minutes} {localized_text('stats_transcribe', lang)[0]} "
            f"{seconds} {localized_text('stats_transcribe', lang)[1]}\n"
        )
        section += f"{localized_text('stats_total', lang)}{cost:.2f}\n"
        section += "----------------------------\n"
        return section

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.check_access(update):
            user = update.message.from_user
            logging.warning(f'User {user.name} (id: {user.id}) is not allowed to request their usage statistics')
            await self.send_disallowed_message(update, context)
            return

        user = update.message.from_user
        user_id = user.id
        username = user.name
        logging.info(f'User {username} (id: {user_id}) requested their usage statistics')

        if user_id not in self.usage:
            self.usage[user_id] = UsageTracker(user_id, username)

        tracker = self.usage[user_id]
        tokens_today, tokens_month = tracker.get_current_token_usage()
        images_today, images_month = tracker.get_current_image_count()
        transcribe_today = tracker.get_current_transcription_duration()
        vision_today, vision_month = tracker.get_current_vision_tokens()
        tts_today, tts_month = tracker.get_current_tts_usage()
        current_cost = tracker.get_current_cost()

        bot_language = self.config['bot_language']
        chat_id = update.effective_chat.id
        chat_messages, chat_token_length = self.openai.get_conversation_stats(chat_id)

        # Conversation stats block
        text_current_conversation = (
            f"*{localized_text('stats_conversation', bot_language)[0]}*:\n"
            f"{chat_messages} {localized_text('stats_conversation', bot_language)[1]}\n"
            f"{chat_token_length} {localized_text('stats_conversation', bot_language)[2]}\n"
            "----------------------------\n"
        )

        # Usage blocks
        text_today = format_usage_section(
            localized_text('usage_today', bot_language),
            tokens_today, images_today, vision_today, tts_today,
            transcribe_today[0], transcribe_today[1],
            current_cost['cost_today'],
            self.config, bot_language
        )

        text_month = format_usage_section(
            localized_text('usage_month', bot_language),
            tokens_month, images_month, vision_month, tts_month,
            transcribe_today[2], transcribe_today[3],
            current_cost['cost_month'],
            self.config, bot_language
        )

        # Budget
        remaining_budget = get_remaining_budget(self.config, self.usage, update)
        text_budget = "\n\n"
        if remaining_budget < float('inf'):
            period = self.config['budget_period']
            text_budget += (
                f"{localized_text('stats_budget', bot_language)}"
                f"{localized_text(period, bot_language)}: "
                f"${remaining_budget:.2f}.\n"
            )

        usage_text = text_current_conversation + text_today + text_month + text_budget
        await update.message.reply_text(usage_text, parse_mode=constants.ParseMode.MARKDOWN)

    async def resend(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Resend the last request
        """
        if not await self.check_access(update):
            logging.warning(f'User {update.message.from_user.name}  (id: {update.message.from_user.id})'
                        ' is not allowed to resend the message')
            await self.send_disallowed_message(update, context)
            return


        chat_id = update.effective_chat.id
        if chat_id not in self.last_message:
            logging.warning(f'User {update.message.from_user.name} (id: {update.message.from_user.id})'
                            ' does not have anything to resend')
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                text=localized_text('resend_failed', self.config['bot_language'])
            )
            return

        # Update message text, clear self.last_message and send the request to prompt
        logging.info(f'Resending the last prompt from user: {update.message.from_user.name} '
                     f'(id: {update.message.from_user.id})')
        with update.message._unfrozen() as message:
            message.text = self.last_message.pop(chat_id)

        await self.prompt(update=update, context=context)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Resets the conversation.
        """
        if not await self.check_access(update):
            logging.warning(f'User {update.message.from_user.name} (id: {update.message.from_user.id}) '
                        'is not allowed to reset the conversation')
            await self.send_disallowed_message(update, context)
            return

        logging.info(f'Resetting the conversation for user {update.message.from_user.name} '
                     f'(id: {update.message.from_user.id})...')

        chat_id = update.effective_chat.id
        reset_content = message_text(update.message)
        self.openai.reset_chat_history(chat_id=chat_id, content=reset_content)
        await update.effective_message.reply_text(
            message_thread_id=get_thread_id(update),
            text=localized_text('reset_done', self.config['bot_language'])
        )

    async def image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Generates an image for the given prompt using DALL·E APIs
        """
    # Проверка доступа пользователя
        if not await self.check_access(update):
            await self.send_disallowed_message(update, context)
            return

        if not self.config['enable_image_generation'] \
                or not await self.check_allowed_and_within_budget(update, context):
            return

        image_query = message_text(update.message)
        if image_query == '':
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                text=localized_text('image_no_prompt', self.config['bot_language'])
            )
            return


        logging.info(f'New image generation request received from user {update.message.from_user.name} '
                     f'(id: {update.message.from_user.id})')

        async def _generate():
            if not await self.check_access(update):
                await self.send_disallowed_message(update, context)
                return
            try:
                image_url, image_size = await self.openai.generate_image(prompt=image_query)
                if self.config['image_receive_mode'] == 'photo':
                    await update.effective_message.reply_photo(
                        reply_to_message_id=get_reply_to_message_id(self.config, update),
                        photo=image_url
                    )
                elif self.config['image_receive_mode'] == 'document':
                    await update.effective_message.reply_document(
                        reply_to_message_id=get_reply_to_message_id(self.config, update),
                        document=image_url
                    )
                else:
                    raise Exception(f"env variable IMAGE_RECEIVE_MODE has invalid value {self.config['image_receive_mode']}")
                # add image request to users usage tracker
                user_id = update.message.from_user.id
                self.usage[user_id].add_image_request(image_size, self.config['image_prices'])
                # add guest chat request to guest usage tracker
                if str(user_id) not in self.config['allowed_user_ids'] and 'guests' in self.usage:
                    self.usage["guests"].add_image_request(image_size, self.config['image_prices'])

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=f"{localized_text('image_fail', self.config['bot_language'])}: {str(e)}",
                    parse_mode=constants.ParseMode.MARKDOWN
                )

        await wrap_with_indicator(update, context, _generate, constants.ChatAction.UPLOAD_PHOTO)

    async def tts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Generates speech for the given input using TTS APIs.
        """
        if not await self.check_access(update):
            await self.send_disallowed_message(update, context)
            return

        if not self.config['enable_tts_generation'] or not await self.check_allowed_and_within_budget(update, context):
            return

        tts_query = message_text(update.message)
        if tts_query == '':
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                text=localized_text('tts_no_prompt', self.config['bot_language'])
            )
            return

        logging.info(f'New speech generation request received from user {update.message.from_user.name} '
                    f'(id: {update.message.from_user.id})')

        async def _generate():
            try:
                speech_file, text_length = await self.openai.generate_speech(text=tts_query)

                await update.effective_message.reply_voice(
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    voice=speech_file
                )
                speech_file.close()

                user_id = update.message.from_user.id

                self.usage[user_id].add_tts_request(
                    text_length, self.config['tts_model'], self.config['tts_prices']
                )

                # Проверка, что user_id не в списке разрешённых
                allowed_ids = self.config.get("allowed_user_ids", [])
                if isinstance(allowed_ids, str):
                    allowed_ids = [x.strip() for x in allowed_ids.split(",") if x.strip()]

                if str(user_id) not in allowed_ids and "guests" in self.usage:
                    self.usage["guests"].add_tts_request(
                        text_length, self.config['tts_model'], self.config['tts_prices']
                    )

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=f"{localized_text('tts_fail', self.config['bot_language'])}: {str(e)}",
                    parse_mode=constants.ParseMode.MARKDOWN
                )

        await wrap_with_indicator(update, context, _generate, constants.ChatAction.UPLOAD_VOICE)

    async def transcribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Transcribe audio messages.
        """
        if not await self.check_access(update):
            await self.send_disallowed_message(update, context)
            return

        if not self.config['enable_transcription'] or not await self.check_allowed_and_within_budget(update, context):
            return

        if is_group_chat(update) and self.config['ignore_group_transcriptions']:
            logging.info('Transcription coming from group chat, ignoring...')
            return

        chat_id = update.effective_chat.id
        filename = update.message.effective_attachment.file_unique_id

        async def _execute():
            filename_mp3 = f'{filename}.mp3'
            bot_language = self.config['bot_language']
            try:
                media_file = await context.bot.get_file(update.message.effective_attachment.file_id)
                await media_file.download_to_drive(filename)
            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=(
                        f"{localized_text('media_download_fail', bot_language)[0]}: "
                        f"{str(e)}. {localized_text('media_download_fail', bot_language)[1]}"
                    ),
                    parse_mode=constants.ParseMode.MARKDOWN
                )
                return

            try:
                audio_track = AudioSegment.from_file(filename)
                audio_track.export(filename_mp3, format="mp3")
                logging.info(f'New transcribe request received from user {update.message.from_user.name} '
                             f'(id: {update.message.from_user.id})')

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=localized_text('media_type_fail', bot_language)
                )
                if os.path.exists(filename):
                    os.remove(filename)
                return

            user_id = update.message.from_user.id
            if user_id not in self.usage:
                self.usage[user_id] = UsageTracker(user_id, update.message.from_user.name)

            try:
                transcript = await self.openai.transcribe(filename_mp3)

                transcription_price = self.config['transcription_price']
                self.usage[user_id].add_transcription_seconds(audio_track.duration_seconds, transcription_price)

                allowed_user_ids = self.config['allowed_user_ids']
                if str(user_id) not in allowed_user_ids and 'guests' in self.usage:
                    self.usage["guests"].add_transcription_seconds(audio_track.duration_seconds, transcription_price)

                # check if transcript starts with any of the prefixes
                response_to_transcription = any(transcript.lower().startswith(prefix.lower()) if prefix else False
                                                for prefix in self.config['voice_reply_prompts'])

                if self.config['voice_reply_transcript'] and not response_to_transcription:

                    # Split into chunks of 4096 characters (Telegram's message limit)
                    transcript_output = f"_{localized_text('transcript', bot_language)}:_\n\"{transcript}\""
                    chunks = split_into_chunks(transcript_output)

                    for index, transcript_chunk in enumerate(chunks):
                        await update.effective_message.reply_text(
                            message_thread_id=get_thread_id(update),
                            reply_to_message_id=get_reply_to_message_id(self.config, update) if index == 0 else None,
                            text=transcript_chunk,
                            parse_mode=constants.ParseMode.MARKDOWN
                        )
                else:
                    # Get the response of the transcript
                    response, total_tokens = await self.openai.get_chat_response(chat_id=chat_id, query=transcript)

                    self.usage[user_id].add_chat_tokens(total_tokens, self.config['token_price'])
                    if str(user_id) not in allowed_user_ids and 'guests' in self.usage:
                        self.usage["guests"].add_chat_tokens(total_tokens, self.config['token_price'])

                    # Split into chunks of 4096 characters (Telegram's message limit)
                    transcript_output = (
                        f"_{localized_text('transcript', bot_language)}:_\n\"{transcript}\"\n\n"
                        f"_{localized_text('answer', bot_language)}:_\n{response}"
                    )
                    chunks = split_into_chunks(transcript_output)

                    for index, transcript_chunk in enumerate(chunks):
                        await update.effective_message.reply_text(
                            message_thread_id=get_thread_id(update),
                            reply_to_message_id=get_reply_to_message_id(self.config, update) if index == 0 else None,
                            text=transcript_chunk,
                            parse_mode=constants.ParseMode.MARKDOWN
                        )

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=f"{localized_text('transcribe_fail', bot_language)}: {str(e)}",
                    parse_mode=constants.ParseMode.MARKDOWN
                )
            finally:
                if os.path.exists(filename_mp3):
                    os.remove(filename_mp3)
                if os.path.exists(filename):
                    os.remove(filename)

        await wrap_with_indicator(update, context, _execute, constants.ChatAction.TYPING)

    async def vision(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Interpret image using vision model.
        """
        if not await self.check_access(update):
            await self.send_disallowed_message(update, context)
            return
        if not self.config['enable_vision'] or not await self.check_allowed_and_within_budget(update, context):
            return

        chat_id = update.effective_chat.id
        prompt = update.message.caption

        if is_group_chat(update):
            if self.config['ignore_group_vision']:
                logging.info('Vision coming from group chat, ignoring...')
                return
            else:
                trigger_keyword = self.config['group_trigger_keyword']
                if (prompt is None and trigger_keyword != '') or \
                   (prompt is not None and not prompt.lower().startswith(trigger_keyword.lower())):
                    logging.info('Vision coming from group chat with wrong keyword, ignoring...')
                    return
        
        image = update.message.effective_attachment[-1]
        

        async def _execute():
            bot_language = self.config['bot_language']
            try:
                media_file = await context.bot.get_file(image.file_id)
                temp_file = io.BytesIO(await media_file.download_as_bytearray())
            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=(
                        f"{localized_text('media_download_fail', bot_language)[0]}: "
                        f"{str(e)}. {localized_text('media_download_fail', bot_language)[1]}"
                    ),
                    parse_mode=constants.ParseMode.MARKDOWN
                )
                return
            
            # convert jpg from telegram to png as understood by openai

            temp_file_png = io.BytesIO()

            try:
                original_image = Image.open(temp_file)
                
                original_image.save(temp_file_png, format='PNG')
                logging.info(f'New vision request received from user {update.message.from_user.name} '
                             f'(id: {update.message.from_user.id})')

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=localized_text('media_type_fail', bot_language)
                )
            
            

            user_id = update.message.from_user.id
            if user_id not in self.usage:
                self.usage[user_id] = UsageTracker(user_id, update.message.from_user.name)

            if self.config['stream']:

                stream_response = self.openai.interpret_image_stream(chat_id=chat_id, fileobj=temp_file_png, prompt=prompt)
                i = 0
                prev = ''
                sent_message = None
                backoff = 0
                stream_chunk = 0

                async for content, tokens in stream_response:
                    if is_direct_result(content):
                        return await handle_direct_result(self.config, update, content)

                    if len(content.strip()) == 0:
                        continue

                    stream_chunks = split_into_chunks(content)
                    if len(stream_chunks) > 1:
                        content = stream_chunks[-1]
                        if stream_chunk != len(stream_chunks) - 1:
                            stream_chunk += 1
                            try:
                                await edit_message_with_retry(context, chat_id, str(sent_message.message_id),
                                                              stream_chunks[-2])
                            except:
                                pass
                            try:
                                sent_message = await update.effective_message.reply_text(
                                    message_thread_id=get_thread_id(update),
                                    text=content if len(content) > 0 else "..."
                                )
                            except:
                                pass
                            continue

                    cutoff = get_stream_cutoff_values(update, content)
                    cutoff += backoff

                    if i == 0:
                        try:
                            if sent_message is not None:
                                await context.bot.delete_message(chat_id=sent_message.chat_id,
                                                                 message_id=sent_message.message_id)
                            sent_message = await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(self.config, update),
                                text=content,
                            )
                        except:
                            continue

                    elif abs(len(content) - len(prev)) > cutoff or tokens != 'not_finished':
                        prev = content

                        try:
                            use_markdown = tokens != 'not_finished'
                            await edit_message_with_retry(context, chat_id, str(sent_message.message_id),
                                                          text=content, markdown=use_markdown)

                        except RetryAfter as e:
                            backoff += 5
                            await asyncio.sleep(e.retry_after)
                            continue

                        except TimedOut:
                            backoff += 5
                            await asyncio.sleep(0.5)
                            continue

                        except Exception:
                            backoff += 5
                            continue

                        await asyncio.sleep(0.01)

                    i += 1
                    if tokens != 'not_finished':
                        total_tokens = int(tokens)

                
            else:

                try:
                    interpretation, total_tokens = await self.openai.interpret_image(chat_id, temp_file_png, prompt=prompt)


                    try:
                        await update.effective_message.reply_text(
                            message_thread_id=get_thread_id(update),
                            reply_to_message_id=get_reply_to_message_id(self.config, update),
                            text=interpretation,
                            parse_mode=constants.ParseMode.MARKDOWN
                        )
                    except BadRequest:
                        try:
                            await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(self.config, update),
                                text=interpretation
                            )
                        except Exception as e:
                            logging.exception(e)
                            await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(self.config, update),
                                text=f"{localized_text('vision_fail', bot_language)}: {str(e)}",
                                parse_mode=constants.ParseMode.MARKDOWN
                            )
                except Exception as e:
                    logging.exception(e)
                    await update.effective_message.reply_text(
                        message_thread_id=get_thread_id(update),
                        reply_to_message_id=get_reply_to_message_id(self.config, update),
                        text=f"{localized_text('vision_fail', bot_language)}: {str(e)}",
                        parse_mode=constants.ParseMode.MARKDOWN
                    )
            vision_token_price = self.config['vision_token_price']
            self.usage[user_id].add_vision_tokens(total_tokens, vision_token_price)

            allowed_user_ids = self.config['allowed_user_ids']
            if str(user_id) not in allowed_user_ids and 'guests' in self.usage:
                self.usage["guests"].add_vision_tokens(total_tokens, vision_token_price)

        await wrap_with_indicator(update, context, _execute, constants.ChatAction.TYPING)

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        React to incoming messages and respond accordingly.
        """
        if update.edited_message or not update.message or update.message.via_bot:
            return

        if not await self.check_allowed_and_within_budget(update, context):
            return
        
        if not await self.check_access(update):
            await self.send_disallowed_message(update, context)
            return

        logging.info(
            f'New message received from user {update.message.from_user.name} (id: {update.message.from_user.id})')
        chat_id = update.effective_chat.id
        user_id = update.message.from_user.id
        prompt = message_text(update.message)
        self.last_message[chat_id] = prompt

        if is_group_chat(update):
            trigger_keyword = self.config['group_trigger_keyword']

            if prompt.lower().startswith(trigger_keyword.lower()) or update.message.text.lower().startswith('/chat'):
                if prompt.lower().startswith(trigger_keyword.lower()):
                    prompt = prompt[len(trigger_keyword):].strip()

                if update.message.reply_to_message and \
                        update.message.reply_to_message.text and \
                        update.message.reply_to_message.from_user.id != context.bot.id:
                    prompt = f'"{update.message.reply_to_message.text}" {prompt}'
            else:
                if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
                    logging.info('Message is a reply to the bot, allowing...')
                else:
                    logging.warning('Message does not start with trigger keyword, ignoring...')
                    return

        try:
            total_tokens = 0

            if self.config['stream']:
                await update.effective_message.reply_chat_action(
                    action=constants.ChatAction.TYPING,
                    message_thread_id=get_thread_id(update)
                )

                stream_response = self.openai.get_chat_response_stream(chat_id=chat_id, query=prompt)
                i = 0
                prev = ''
                sent_message = None
                backoff = 0
                stream_chunk = 0

                async for content, tokens in stream_response:
                    if is_direct_result(content):
                        return await handle_direct_result(self.config, update, content)

                    if len(content.strip()) == 0:
                        continue

                    stream_chunks = split_into_chunks(content)
                    if len(stream_chunks) > 1:
                        content = stream_chunks[-1]
                        if stream_chunk != len(stream_chunks) - 1:
                            stream_chunk += 1
                            try:
                                await edit_message_with_retry(context, chat_id, str(sent_message.message_id),
                                                              stream_chunks[-2])
                            except:
                                pass
                            try:
                                sent_message = await update.effective_message.reply_text(
                                    message_thread_id=get_thread_id(update),
                                    text=content if len(content) > 0 else "..."
                                )
                            except:
                                pass
                            continue

                    cutoff = get_stream_cutoff_values(update, content)
                    cutoff += backoff

                    if i == 0:
                        try:
                            if sent_message is not None:
                                await context.bot.delete_message(chat_id=sent_message.chat_id,
                                                                 message_id=sent_message.message_id)
                            sent_message = await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(self.config, update),
                                text=content,
                            )
                        except:
                            continue

                    elif abs(len(content) - len(prev)) > cutoff or tokens != 'not_finished':
                        prev = content

                        try:
                            use_markdown = tokens != 'not_finished'
                            await edit_message_with_retry(context, chat_id, str(sent_message.message_id),
                                                          text=content, markdown=use_markdown)

                        except RetryAfter as e:
                            backoff += 5
                            await asyncio.sleep(e.retry_after)
                            continue

                        except TimedOut:
                            backoff += 5
                            await asyncio.sleep(0.5)
                            continue

                        except Exception:
                            backoff += 5
                            continue

                        await asyncio.sleep(0.01)

                    i += 1
                    if tokens != 'not_finished':
                        total_tokens = int(tokens)

            else:
                async def _reply():
                    nonlocal total_tokens
                    response, total_tokens = await self.openai.get_chat_response(chat_id=chat_id, query=prompt)

                    if is_direct_result(response):
                        return await handle_direct_result(self.config, update, response)

                    # Split into chunks of 4096 characters (Telegram's message limit)
                    chunks = split_into_chunks(response)

                    for index, chunk in enumerate(chunks):
                        try:
                            await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(self.config,
                                                                            update) if index == 0 else None,
                                text=chunk,
                                parse_mode=constants.ParseMode.MARKDOWN
                            )
                        except Exception:
                            try:
                                await update.effective_message.reply_text(
                                    message_thread_id=get_thread_id(update),
                                    reply_to_message_id=get_reply_to_message_id(self.config,
                                                                                update) if index == 0 else None,
                                    text=chunk
                                )
                            except Exception as exception:
                                raise exception

                await wrap_with_indicator(update, context, _reply, constants.ChatAction.TYPING)

            add_chat_request_to_usage_tracker(self.usage, self.config, user_id, total_tokens)

        except Exception as e:
            logging.exception(e)
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                reply_to_message_id=get_reply_to_message_id(self.config, update),
                text=f"{localized_text('chat_fail', self.config['bot_language'])} {str(e)}",
                parse_mode=constants.ParseMode.MARKDOWN
            )

    async def inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle the inline query. This is run when you type: @botusername <query>
        """
        query = update.inline_query.query
        if len(query) < 3:
            return
        if not await self.check_access(update):
            return

        callback_data_suffix = "gpt:"
        result_id = str(uuid4())
        self.inline_queries_cache[result_id] = query
        callback_data = f'{callback_data_suffix}{result_id}'

        await self.send_inline_query_result(update, result_id, message_content=query, callback_data=callback_data)

    async def send_inline_query_result(self, update: Update, result_id, message_content, callback_data=""):
        """
        Send inline query result
        """
        if not await self.check_access(update):
            return  
        try:
            reply_markup = None
            bot_language = self.config['bot_language']
            if callback_data:
                reply_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(text=f'🤖 {localized_text("answer_with_chatgpt", bot_language)}',
                                         callback_data=callback_data)
                ]])

            inline_query_result = InlineQueryResultArticle(
                id=result_id,
                title=localized_text("ask_chatgpt", bot_language),
                input_message_content=InputTextMessageContent(message_content),
                description=message_content,
                thumbnail_url='https://user-images.githubusercontent.com/11541888/223106202-7576ff11-2c8e-408d-94ea-b02a7a32149a.png',
                reply_markup=reply_markup
            )

            await update.inline_query.answer([inline_query_result], cache_time=0)
        except Exception as e:
            logging.error(f'An error occurred while generating the result card for inline query {e}')

    async def handle_callback_inline_query(self, update: Update, context: CallbackContext):
        callback_data = update.callback_query.data
        user = update.effective_user
        user_id = user.id
        username = user.username or user.full_name
        await update.callback_query.answer()

        if callback_data == "start_dialog":
            # 1.1) Одобренный пользователь — сразу меню ролей
            if self.supabase.is_user_approved(user_id):
                keyboard = [
                    [InlineKeyboardButton("Преподаватель", callback_data="role_teacher")],
                    [InlineKeyboardButton("Ученик",       callback_data="role_student")],
                ]
                await update.callback_query.edit_message_text(
                    "Выберите, кто вы:", reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return

            # 1.2) Получаем все pending-заявки
            pending = self.supabase.get_pending_requests()

            # 1.3) Уже подавал заявку?
            if any(req.get("user_id") == user_id for req in pending):
                await update.callback_query.answer(
                    "Вы уже подали заявку. Ожидайте одобрения администратора.",
                    show_alert=True
                )
                return

            # 1.4) Создаём новую заявку
            try:
                self.supabase.add_join_request(user_id, username)
                await update.callback_query.answer(
                    "✅ Заявка отправлена. Ожидайте одобрения администратора.",
                    show_alert=True
                )
            except Exception as e:
                logging.error(f"[ERROR] add_join_request: {e}")
                await update.callback_query.answer(
                    "❗️ Ошибка при отправке заявки. Попробуйте позже.",
                    show_alert=True
                )
                return

            # 1.5) Оповещаем админов
            for admin_id in self.admin_user_ids:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"📨 Новая заявка от пользователя:\n\n"
                            f"👤 {username} (ID: {user_id})"
                        )
                    )
                except Exception as e:
                    logging.error(f"Ошибка при уведомлении админа {admin_id}: {e}")
            return

        # 2) Всё остальное — только для одобренных
        if not self.supabase.is_user_approved(user_id):
            await update.callback_query.answer(
                "⛔️ Доступ запрещён. Подайте заявку и дождитесь одобрения администратора.",
                show_alert=True
            )
            return

        # 3) Выбор роли
        if callback_data == "role_teacher":
            keyboard = [
                [InlineKeyboardButton(lang, callback_data=f"teacher_lang_{lang.lower()}")]
                for lang in ["Английский", "Китайский", "Французский", "Немецкий", "Итальянский", "Польский"]
            ]
            await update.callback_query.edit_message_text(
                "Выберите язык преподавания:", reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        if callback_data == "role_student":
            keyboard = [
                [InlineKeyboardButton(lang, callback_data=f"student_lang_{lang.lower()}")]
                for lang in ["Английский", "Китайский", "Французский", "Немецкий", "Итальянский", "Польский"]
            ]
            await update.callback_query.edit_message_text(
                "Выберите язык изучения:", reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # 4) Приветствие после выбора языка
        if callback_data.startswith("teacher_lang_"):
            await update.callback_query.edit_message_text(
                "Привет! Ты можешь присылать сюда файлы, изображения и тексты для проверки, "
                "просить сгенерировать задания на нужную тему, голосовые сообщения и другое."
            )
            return

        if callback_data.startswith("student_lang_"):
            await update.callback_query.edit_message_text(
                "Привет! Я могу давать материал для изучения, проверить твой уровень знаний, "
                "отправлять тесты и проверять их, генерировать голосовые сообщения для практики прослушки "
                "и принимать твои для практики разговора."
            )
            return

        user_id = update.callback_query.from_user.id
        inline_message_id = update.callback_query.inline_message_id
        name = update.callback_query.from_user.name
        callback_data_suffix = "gpt:"
        query = ""
        bot_language = self.config['bot_language']
        answer_tr = localized_text("answer", bot_language)
        loading_tr = localized_text("loading", bot_language)

        try:
            if callback_data.startswith(callback_data_suffix):
                unique_id = callback_data.split(':')[1]
                total_tokens = 0

                # Retrieve the prompt from the cache
                query = self.inline_queries_cache.get(unique_id)
                if query:
                    self.inline_queries_cache.pop(unique_id)
                else:
                    error_message = (
                        f'{localized_text("error", bot_language)}. '
                        f'{localized_text("try_again", bot_language)}'
                    )
                    await edit_message_with_retry(context, chat_id=None, message_id=inline_message_id,
                                                  text=f'{query}\n\n_{answer_tr}:_\n{error_message}',
                                                  is_inline=True)
                    return

                unavailable_message = localized_text("function_unavailable_in_inline_mode", bot_language)
                if self.config['stream']:
                    stream_response = self.openai.get_chat_response_stream(chat_id=user_id, query=query)
                    i = 0
                    prev = ''
                    backoff = 0
                    async for content, tokens in stream_response:
                        if is_direct_result(content):
                            cleanup_intermediate_files(content)
                            await edit_message_with_retry(context, chat_id=None,
                                                          message_id=inline_message_id,
                                                          text=f'{query}\n\n_{answer_tr}:_\n{unavailable_message}',
                                                          is_inline=True)
                            return

                        if len(content.strip()) == 0:
                            continue

                        cutoff = get_stream_cutoff_values(update, content)
                        cutoff += backoff

                        if i == 0:
                            try:
                                await edit_message_with_retry(context, chat_id=None,
                                                              message_id=inline_message_id,
                                                              text=f'{query}\n\n{answer_tr}:\n{content}',
                                                              is_inline=True)
                            except:
                                continue

                        elif abs(len(content) - len(prev)) > cutoff or tokens != 'not_finished':
                            prev = content
                            try:
                                use_markdown = tokens != 'not_finished'
                                divider = '_' if use_markdown else ''
                                text = f'{query}\n\n{divider}{answer_tr}:{divider}\n{content}'

                                # We only want to send the first 4096 characters. No chunking allowed in inline mode.
                                text = text[:4096]

                                await edit_message_with_retry(context, chat_id=None, message_id=inline_message_id,
                                                              text=text, markdown=use_markdown, is_inline=True)

                            except RetryAfter as e:
                                backoff += 5
                                await asyncio.sleep(e.retry_after)
                                continue
                            except TimedOut:
                                backoff += 5
                                await asyncio.sleep(0.5)
                                continue
                            except Exception:
                                backoff += 5
                                continue

                            await asyncio.sleep(0.01)

                        i += 1
                        if tokens != 'not_finished':
                            total_tokens = int(tokens)

                else:
                    async def _send_inline_query_response():
                        nonlocal total_tokens
                        # Edit the current message to indicate that the answer is being processed
                        await context.bot.edit_message_text(inline_message_id=inline_message_id,
                                                            text=f'{query}\n\n_{answer_tr}:_\n{loading_tr}',
                                                            parse_mode=constants.ParseMode.MARKDOWN)

                        logging.info(f'Generating response for inline query by {name}')
                        response, total_tokens = await self.openai.get_chat_response(chat_id=user_id, query=query)

                        if is_direct_result(response):
                            cleanup_intermediate_files(response)
                            await edit_message_with_retry(context, chat_id=None,
                                                          message_id=inline_message_id,
                                                          text=f'{query}\n\n_{answer_tr}:_\n{unavailable_message}',
                                                          is_inline=True)
                            return

                        text_content = f'{query}\n\n_{answer_tr}:_\n{response}'

                        # We only want to send the first 4096 characters. No chunking allowed in inline mode.
                        text_content = text_content[:4096]

                        # Edit the original message with the generated content
                        await edit_message_with_retry(context, chat_id=None, message_id=inline_message_id,
                                                      text=text_content, is_inline=True)

                    await wrap_with_indicator(update, context, _send_inline_query_response,
                                              constants.ChatAction.TYPING, is_inline=True)

                add_chat_request_to_usage_tracker(self.usage, self.config, user_id, total_tokens)

        except Exception as e:
            logging.error(f'Failed to respond to an inline query via button callback: {e}')
            logging.exception(e)
            localized_answer = localized_text('chat_fail', self.config['bot_language'])
            await edit_message_with_retry(context, chat_id=None, message_id=inline_message_id,
                                          text=f"{query}\n\n_{answer_tr}:_\n{localized_answer} {str(e)}",
                                          is_inline=True)

    async def check_allowed_and_within_budget(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        is_inline: bool = False
    ) -> bool:
        # 0) Вычисляем пользователя и его имя
        user = update.inline_query.from_user if is_inline else update.message.from_user
        user_id = user.id
        user_name = user.username or user.full_name

        # 1) Проверяем, одобрен ли пользователь
        if not self.supabase.is_user_approved(user_id):
            if is_inline:
                await update.inline_query.answer(
                    results=[],
                    switch_pm_text="⛔️ Доступ запрещён. Подайте заявку.",
                    switch_pm_parameter="start",
                    cache_time=0
                )
            else:
                await update.message.reply_text(
                    "⛔️ Доступ запрещён. Подайте заявку и дождитесь одобрения администратора."
                )
            return False

        # 2) Общие права (is_allowed)
        if not await is_allowed(self.config, update, context, is_inline=is_inline):
            logging.warning(f'User {user_name} (id: {user_id}) is not allowed to use the bot')
            await self.send_disallowed_message(update, context, is_inline)
            return False

        # 3) Бюджет (is_within_budget)
        if not is_within_budget(self.config, self.usage, update, is_inline=is_inline):
            logging.warning(f'User {user_name} (id: {user_id}) reached their usage limit')
            await self.send_budget_reached_message(update, context, is_inline)
            return False

        # 4) Всё ок
        return True

    async def post_init(self, application: Application) -> None:
        """
        Post initialization hook for the bot.
        """
        await application.bot.set_my_commands(self.group_commands, scope=BotCommandScopeAllGroupChats())
        await application.bot.set_my_commands(self.commands)

    def run(self):
        """
        Runs the bot indefinitely until the user presses Ctrl+C
        """
        application = ApplicationBuilder() \
            .token(self.config['token']) \
            .proxy_url(self.config['proxy']) \
            .get_updates_proxy_url(self.config['proxy']) \
            .post_init(self.post_init) \
            .concurrent_updates(True) \
            .build()

        # Добавляем обработчики команд
        application.add_handler(CommandHandler('admin', self.admin_panel))
        application.add_handler(CallbackQueryHandler(self.handle_admin_buttons, pattern="^admin_"))
        application.add_handler(CommandHandler('reset', self.reset))
        application.add_handler(CommandHandler("image_search", self.image_search))
        self.commands.append(BotCommand(command="image_search", description="Поиск изображения через DuckDuckGo"))
        application.add_handler(CommandHandler('help', self.help))
        application.add_handler(CommandHandler('image', self.image))
        application.add_handler(CommandHandler('tts', self.tts))
        application.add_handler(CommandHandler('start', self.help))
        application.add_handler(CommandHandler('stats', self.stats))
        application.add_handler(CommandHandler('resend', self.resend))
        application.add_handler(CommandHandler(
            'chat', self.prompt, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
        )
        application.add_handler(MessageHandler(
            filters.PHOTO | filters.Document.IMAGE,
            self.vision))
        application.add_handler(MessageHandler(
            filters.AUDIO | filters.VOICE | filters.Document.AUDIO |
            filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO,
            self.transcribe))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.prompt))
        application.add_handler(InlineQueryHandler(self.inline_query, chat_types=[
            constants.ChatType.GROUP, constants.ChatType.SUPERGROUP, constants.ChatType.PRIVATE
        ]))
        # Обработчик для админских кнопок по шаблону
        application.add_handler(CallbackQueryHandler(self.handle_admin_buttons, pattern="^(approve_request_|reject_request_|block_user_|unblock_user_)"))

        # Обработчик ошибок
        application.add_error_handler(error_handler)

        # Обработчик inline callback запросов
        application.add_handler(CallbackQueryHandler(self.handle_callback_inline_query))
        application.run_polling()

    async def help(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Shows the help menu and a button to start dialog.
        """
        user = update.effective_user
        user_id = user.id
        username = user.username or user.full_name

        # Асинхронно проверяем одобрение пользователя
        if not self.supabase.is_user_approved(user_id):
            # Асинхронно получаем заявки
            requests = self.supabase.get_pending_requests()
            if any(str(user_id) == str(req.get("user_id")) for req in requests):
                await update.message.reply_text("Вы уже подали заявку. Ожидайте одобрения администратора.")
            else:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📨 Подать заявку", callback_data="start_dialog")]
                ])
                await update.message.reply_text(
                    "👋 Добро пожаловать! Чтобы получить доступ к функциям бота, подайте заявку:",
                    reply_markup=keyboard
                )
            return

        if not await is_allowed(self.config, update, _):
            logging.warning(f'User {update.effective_user.full_name} (id: {user_id}) is not allowed to use /help')
            await self.send_disallowed_message(update, _)
            return

        commands = self.group_commands if is_group_chat(update) else self.commands
        bot_language = self.config['bot_language']
        commands_description = [f'/{command.command} - {command.description}' for command in commands]
        help_localized = localized_text('help_text', bot_language)

        help_text = (
            help_localized[0] +
            '\n\n' +
            '\n'.join(commands_description) +
            '\n\n' +
            help_localized[1] +
            '\n\n' +
            (help_localized[2] if len(help_localized) > 2 else '')
        )

        keyboard = [
            [InlineKeyboardButton("Давай начнём", callback_data="start_dialog")]
        ]
        await update.message.reply_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_admin_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data
        await query.answer()

        if not isinstance(data, str):
            logging.error(f"callback_query.data is not a string! type: {type(data)}, value: {data}")
            await query.answer("Ошибка данных кнопки", show_alert=True)
            return

        print(f"[DEBUG] Callback data type: {type(data)}, value: {data}")
        print("===> handle_admin_buttons called")

        await query.answer()

        # 1) Список участников
        if data == "admin_list_users":
            users = self.supabase.get_users()
            text = "\n".join([f"{uid}: {rec.get('username')}" for uid, rec in users.items()]) or "Нет участников."
            await query.edit_message_text(text)
            return

        # 2) Заявки на вступление
        if data == "admin_view_requests":
            requests = self.supabase.get_requests()
            if not requests:
                await query.edit_message_text("Заявок нет.")
                return

            keyboard = []
            for uid, info in requests.items():
                keyboard.append([
                    InlineKeyboardButton("✅", callback_data=f"approve_request_{uid}"),
                    InlineKeyboardButton("❌", callback_data=f"reject_request_{uid}"),
                    InlineKeyboardButton(f"{info.get('username')} ({uid})", callback_data="noop")
                ])
            await query.edit_message_text(
                "📝 Заявки на вступление:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # 3) Заблокированные
        if data == "admin_blocked_users":
            blocked = self.supabase.get_blocked_users()
            text = "\n".join(map(str, blocked)) or "Нет заблокированных."
            await query.edit_message_text(text)
            return

        # 4) Одобрить заявку
        if data.startswith("approve_request_"):
            str_uid = data.split("_")[-1]
            user_id = int(str_uid)
            requests = self.supabase.get_requests()
            username = requests.get(str_uid, {}).get("username", "")

            try:
                self.supabase.approve_user(user_id, username)
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ Ваша заявка одобрена! Теперь вы можете пользоваться ботом."
                )
                await query.edit_message_text("✅ Заявка одобрена и пользователь уведомлён.")
            except Exception as e:
                logging.error(f"Ошибка при одобрении заявки: {e}")
                await query.answer("❗️Не удалось одобрить заявку.", show_alert=True)
            return

        # 5) Отклонить заявку
        if data.startswith("reject_request_"):
            str_uid = data.split("_")[-1]
            user_id = int(str_uid)
            try:
                self.supabase.reject_user(user_id)
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Ваша заявка отклонена."
                )
                await query.edit_message_text("❌ Заявка отклонена и пользователь уведомлён.")
            except Exception as e:
                logging.error(f"Ошибка при отклонении заявки: {e}")
                await query.answer("❗️Не удалось отклонить заявку.", show_alert=True)
            return
        elif data == "admin_blocked_users":
            blocked = self.supabase.get_blocked_users()
            text = "\n".join(map(str, blocked)) if blocked else "Заблокированных пользователей нет."
            await query.edit_message_text(text)
            return

        elif data.startswith("unblock_user_"):
            user_id = data.split("_")[-1]
            self.supabase.unblock_user(user_id)
            await query.edit_message_text("Пользователь разблокирован.")
            return

        elif data.startswith("block_user_"):
            user_id = data.split("_")[-1]
            self.supabase.block_user(user_id)
            await query.edit_message_text("Пользователь заблокирован.")
            return

        if data == 'admin_approve':
            await query.edit_message_text("✅ Заявка одобрена.")
        elif data == 'admin_reject':
            await query.edit_message_text("❌ Заявка отклонена.")
        else:
            await query.edit_message_text(f"Неизвестное действие: {data}")
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not is_admin(self.config, user_id):
            await update.message.reply_text("❌ У вас нет доступа к этой команде.")
            return

        keyboard = [
            [InlineKeyboardButton("📋 Просмотреть участников",    callback_data="admin_list_users")],
            [InlineKeyboardButton("📝 Заявки на вступление",     callback_data="admin_view_requests")],
            [InlineKeyboardButton("🚫 Заблокированные пользователи", callback_data="admin_blocked_users")],
        ]
        await update.message.reply_text("🛠 Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))
