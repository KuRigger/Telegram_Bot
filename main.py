import logging
import asyncio
import sys
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone
from bot_functions import BotFunctions
from admin_panel import AdminPanel
from survey_module import SurveyManager, SurveyStates
from data_processing import DataProcessor
from chat_model import ChatModel
from dotenv import load_dotenv
from aiogram import F
from admin_panel import AdminStates 

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"), 
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG) 

class MentalHealthBot:
    def __init__(self):
        self.storage = MemoryStorage() 
        self.bot = Bot(token=os.getenv("BOT_TOKEN"))
        self.dp = Dispatcher(storage=self.storage)
        self.scheduler = AsyncIOScheduler(timezone=timezone(os.getenv("TZ")))
        self.data_processor = DataProcessor()
        self.survey_manager = SurveyManager(
            data_processor=self.data_processor,
            bot=self.bot,
            storage=self.storage  
        )
        self.admin_panel = AdminPanel(self.bot, self.data_processor, self.survey_manager)
        self.chat_model = ChatModel()
        self._register_handlers()
        self._schedule_jobs()


    def _register_handlers(self):
        self.dp.message.register(
            self.admin_panel.handle_admin_command, 
            F.text.startswith("/admin")
        )

        self.dp.message.register(
            self.admin_panel.handle_admin_command,
            F.reply_to_message.text.contains("пароль администратора")
        )

        self.dp.message.register(
            self.admin_panel.handle_admin_command,
            F.text.startswith(("/get_report", "/run_survey", "/exit_admin")),
            AdminStates.AUTHENTICATED   
        )

        self.dp.message.register(
            self._start_handler, 
            Command("start")
        )
        self.dp.message.register(
            self._survey_answer_handler, 
            SurveyStates.IN_PROGRESS
        )
        self.dp.message.register(
            self._consent_handler, 
            SurveyStates.CONSENT
        )

        self.dp.message.register(
            self._free_dialog_handler, 
            F.text & ~F.command
        )
        
    def _schedule_jobs(self):
        self.scheduler.add_job(
            self.data_processor.process_all_data,
            'cron',
            hour=23,
            timezone=timezone(os.getenv("TZ"))
        )

    async def _start_handler(self, message: types.Message, state: FSMContext):  
        try:
            logger.info(f"🔄 /start от {message.from_user.id} (chat_id: {message.chat.id})")
            await self.survey_manager.send_consent_request(message.chat.id, state)
        except Exception as e:
            logger.error(f"Ошибка в /start: {e}")
            await message.answer("⚠️ Ошибка. Попробуйте позже.")

    async def _admin_handler(self, message: types.Message):
        await self.admin_panel.handle_admin_command(message)

    async def _survey_answer_handler(self, message: types.Message, state: FSMContext):
        await self.survey_manager.handle_answer(message, state)

    async def _consent_handler(self, message: types.Message, state: FSMContext):
        await self.survey_manager.handle_consent(message, state)

    async def _free_dialog_handler(self, message: types.Message, state: FSMContext):
        try:
            if await state.get_state() == AdminStates.AUTHENTICATED:
                return

            if await self.survey_manager.is_survey_in_progress(message.chat.id):
                logger.info("Опрос активен, сообщение игнорируется.")
                return

            logger.debug(f"Запрос: {message.text}")
            response = await self.chat_model.generate_response(message.text, message.chat.id)
            logger.info(f"Ответ для отправки: {response}")
            await message.answer(response)

        except Exception as e:
            logger.error(f"Ошибка: {e}", exc_info=True)
            await message.answer("⚠️ Ошибка обработки.")

    async def run(self):
        self.scheduler.start()
        try:
            await self.dp.start_polling(self.bot)
        finally:
            await self.bot.session.close()
            self.scheduler.shutdown()

if __name__ == "__main__":
    try:
        bot = MentalHealthBot()
        asyncio.run(bot.run())
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {str(e)}")
        sys.exit(1)