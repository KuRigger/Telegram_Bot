import hashlib
import os
import logging
import traceback
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
import asyncio  

load_dotenv()

logger = logging.getLogger(__name__)

class AdminStates(StatesGroup):
    AUTH_REQUESTED = State() 
    AUTHENTICATED = State()   

class AdminPanel:
    def __init__(self, bot, data_processor, survey_manager):
        self.bot = bot
        self.data_processor = data_processor
        self.survey_manager = survey_manager
        self.admin_password = os.getenv("ADMIN_PASSWORD")
        self.active_sessions = set()   
        self.login_attempts = {}         


    async def handle_admin_command(self, message: types.Message, state: FSMContext) -> bool:
        current_state = await state.get_state()
        
        if current_state == AdminStates.AUTHENTICATED:
            return await self._process_authenticated(message, state)
        
        if message.text.startswith("/admin"):
            await state.set_state(AdminStates.AUTH_REQUESTED)
            await self._request_password(message.chat.id)
            return True
        
        if await state.get_state() == AdminStates.AUTH_REQUESTED:
            return await self._check_password(message, state)
        
        return False

    async def _process_authenticated(self, message: types.Message, state: FSMContext) -> bool:
        command = message.text.strip().lower()
        
        if command == "/get_report":
            await self._handle_get_report(message.chat.id)
            return True
        elif command == "/run_survey":
            await self._handle_run_survey(message.chat.id)
            return True
        elif command == "/exit_admin":
            await self._handle_exit_admin(message, state)
            return True
        else:
            logger.debug(f"Админ {message.from_user.id} отправил неизвестную команду: {message.text}")
            return False

    async def _check_password(self, message: types.Message, state: FSMContext) -> bool:
        user_id = message.from_user.id
        input_hash = hashlib.sha256(message.text.encode()).hexdigest()
        correct_hash = hashlib.sha256(self.admin_password.encode()).hexdigest()

        if input_hash == correct_hash:
            self.active_sessions.add(user_id)
            await state.set_state(AdminStates.AUTHENTICATED)
            
            await message.answer(
                "✅ Успешная аутентификация!\n"
                "Доступные команды:\n"
                "/get_report — получить отчет\n"
                "/run_survey — запустить опрос\n"
                "/exit_admin — выйти из админ-панели",
                reply_markup=self._get_admin_keyboard()
            )
            
            logger.info(f"Администратор {user_id} вошел в систему")
            return True
        else:
            await self._handle_wrong_password(message.chat.id, user_id)
            await state.clear()
            return False

    async def _request_password(self, chat_id: int):
        await self.bot.send_message(
            chat_id,
            "🔒 Введите пароль администратора:",
            reply_markup=types.ForceReply(selective=True)
        )


    async def _handle_get_report(self, chat_id: int):
        try:

            success = await asyncio.to_thread(self.data_processor.process_all_data)
            
            if not success:
                await self.bot.send_message(chat_id, "⚠️ Ошибка формирования отчёта")
                return
                
            if not os.path.exists("analysis_results.csv"):
                await self.bot.send_message(chat_id, "⚠️ Файл не найден")
                return
                
            await self.bot.send_document(
                chat_id,
                types.FSInputFile("analysis_results.csv"),
                caption="📊 Отчёт готов"
            )
        except Exception as e:
            await self.bot.send_message(chat_id, f"⚠️ Ошибка: {str(e)}")

    async def _handle_exit_admin(self, message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        await state.clear()
        self.active_sessions.discard(user_id)
        await message.answer(
            "🔒 Сессия администратора завершена",
            reply_markup=types.ReplyKeyboardRemove()
        )
        logger.info(f"Администратор {user_id} вышел из системы")

    async def _handle_run_survey(self, chat_id: int):
        try:
            success = await self.survey_manager.run_scheduled_survey()
            msg = "✅ Опрос запущен для всех пользователей!" if success else "⚠️ Ошибка запуска"
            logger.info(f"Администратор {chat_id} запустил опрос")
        except Exception as e:
            msg = f"💥 Критическая ошибка: {str(e)}"
            logger.error(f"Ошибка запуска опроса: {traceback.format_exc()}")   
        await self.bot.send_message(chat_id, msg)

    def _get_admin_keyboard(self):
        return types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="/get_report"), types.KeyboardButton(text="/run_survey")],
                [types.KeyboardButton(text="/exit_admin")]
            ],
            resize_keyboard=True,
            input_field_placeholder="Выберите действие"
        )

    async def _handle_wrong_password(self, chat_id: int, user_id: int):
        attempts = self.login_attempts.get(user_id, 0) + 1
        self.login_attempts[user_id] = attempts

        if attempts >= 3:
            await self.bot.send_message(chat_id, "🚫 Доступ заблокирован на 24 часа")
            del self.login_attempts[user_id]
            logger.warning(f"Блокировка пользователя {user_id} из-за 3 неудачных попыток")
        else:
            await self.bot.send_message(
                chat_id,
                f"⚠️ Неверный пароль. Осталось попыток: {3 - attempts}"
            )
            logger.info(f"Неудачная попытка входа {user_id} (попытка {attempts})")