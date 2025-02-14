from aiogram import Bot
from aiogram.types import ReplyKeyboardRemove
import aiohttp
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class BotFunctions(Bot):
    def __init__(self, token: str): 
        super().__init__(token=token)
        self.session = aiohttp.ClientSession()

    async def send_message(self, chat_id: int, text: str, **kwargs):
        try:
            await super().send_message(
                chat_id=chat_id,
                text=text,
                **kwargs
            )
            logger.info(f"Сообщение отправлено в {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {str(e)}")
            return False

    async def send_document(self, chat_id: int, document):
        try:
            await super().send_document(
                chat_id=chat_id,
                document=document
            )
            logger.info(f"Документ отправлен в {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки документа: {str(e)}")
            return False

    async def close(self):
        await self.session.close()
        await super().close()