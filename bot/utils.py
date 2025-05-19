from __future__ import annotations

import asyncio
import json
import logging
import os
import base64

import telegram
from telegram import Message, MessageEntity, Update, ChatMember, constants
from telegram.ext import CallbackContext, ContextTypes

from usage_tracker import UsageTracker
from database import Database


def message_text(message: Message) -> str:
    message_txt = message.text
    if message_txt is None:
        return ''
    for _, text in sorted(message.parse_entities([MessageEntity.BOT_COMMAND]).items(),
                          key=lambda item: item[0].offset):
        message_txt = message_txt.replace(text, '').strip()
    return message_txt if message_txt else ''


async def is_user_in_group(update: Update, context: CallbackContext, user_id: int) -> bool:
    try:
        chat_member = await context.bot.get_chat_member(update.message.chat_id, user_id)
        return chat_member.status in [ChatMember.OWNER, ChatMember.ADMINISTRATOR, ChatMember.MEMBER]
    except telegram.error.BadRequest as e:
        if str(e) == "User not found":
            return False
        raise e


def get_thread_id(update: Update) -> int | None:
    if update.effective_message and update.effective_message.is_topic_message:
        return update.effective_message.message_thread_id
    return None


def is_group_chat(update: Update) -> bool:
    if not update.effective_chat:
        return False
    return update.effective_chat.type in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP]


async def wrap_with_indicator(update: Update, context: CallbackContext, coroutine,
                              chat_action: constants.ChatAction = "", is_inline=False):
    task = context.application.create_task(coroutine(), update=update)
    while not task.done():
        if not is_inline:
            context.application.create_task(
                update.effective_chat.send_action(chat_action, message_thread_id=get_thread_id(update))
            )
        try:
            await asyncio.wait_for(asyncio.shield(task), 4.5)
        except asyncio.TimeoutError:
            pass


async def error_handler(_: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f'Exception while handling an update: {context.error}')


async def is_allowed(config, update: Update, context: CallbackContext, is_inline=False) -> bool:
    user_id = update.inline_query.from_user.id if is_inline else update.message.from_user.id
    if is_admin(config, user_id):
        return True
    db = Database()
    if db.is_approved(user_id):
        return True
    name = update.inline_query.from_user.name if is_inline else update.message.from_user.name
    logging.warning(f'User {name} (id: {user_id}) is not allowed to use the bot.')
    return False


def is_admin(config, user_id: int, log_no_admin=False) -> bool:
    if config['admin_user_ids'] == '-':
        if log_no_admin:
            logging.info('No admin user defined.')
        return False
    return user_id in config['admin_user_ids']


def get_reply_to_message_id(config, update: Update):
    if config['enable_quoting'] or is_group_chat(update):
        return update.message.message_id
    return None


def encode_image(fileobj):
    image = base64.b64encode(fileobj.getvalue()).decode('utf-8')
    return f'data:image/jpeg;base64,{image}'


def decode_image(imgbase64):
    image = imgbase64[len('data:image/jpeg;base64,'):]
    return base64.b64decode(image)
