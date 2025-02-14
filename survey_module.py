import os
import traceback
from aiogram.fsm.state import State, StatesGroup
from aiogram import types
from aiogram.fsm.context import FSMContext
import logging
import pandas as pd
import re
from dotenv import load_dotenv
from aiogram.fsm.storage.base import StorageKey

load_dotenv()

logger = logging.getLogger(__name__)

class SurveyStates(StatesGroup):
    CONSENT = State()
    IN_PROGRESS = State()

class SurveyManager:
    def __init__(self, data_processor, bot, storage):  
        self.data_processor = data_processor
        self.bot = bot
        self.storage = storage
        self.questions = [
            {
                "user_question": "Сколько Вы сделали сегодня шагов?",
                "column_name": "Шаги",
                "type": "int",
                "min": 0,
                "max": 50000
            },
            {
                "user_question": "Сколько времени Вы уделили занятиям физической активностью? (в минутах)",
                "column_name": "Время активности",
                "type": "int",
                "min": 0,
                "max": 1440
            },
            {
                "user_question": "Если носите smart-часы, какой средний пульс за день?",
                "column_name": "Средний пульс",
                "type": "int",
                "min": 40,
                "max": 200,
                "optional": True  
            },
            {
                "user_question": "Сколько часов Вы спали прошлой ночью?",
                "column_name": "Длительность сна",
                "type": "float",
                "min": 0.0,
                "max": 24.0
            },
            {
                "user_question": "Как Вы оцениваете качество своего сна?",
                "column_name": "Качество сна",
                "type": "category",
                "options": ["Отлично", "Хорошо", "Удовлетворительно", "Плохо"]
            },
            {
                "user_question": "Во сколько Вы уснули этой ночью? (ЧЧ:ММ)",
                "column_name": "Время засыпания",
                "type": "time",
                "format": r"^\d{1,2}:\d{2}$"  
            },
            {
                "user_question": "Во сколько Вы сегодня проснулись? (ЧЧ:ММ)",
                "column_name": "Время пробуждения",
                "type": "time",
                "format": r"^\d{1,2}:\d{2}$"
            },
            {
                "user_question": "Оцените свое настроение от 1 до 10",
                "column_name": "Оценка настроения",
                "type": "int",
                "min": 1,
                "max": 10
            },
            {
                "user_question": "Были сегодня стрессовые события? Если были, опишите",
                "column_name": "Стресс",
                "type": "text"
            },
            {
                "user_question": "Сколько Вам полных лет?",
                "column_name": "Возраст",
                "type": "int",
                "min": 7,
                "max": 25
            },
            {
                "user_question": "Ваш пол?",
                "column_name": "Пол",
                "type": "category",
                "options": ["Мужской", "Женский"]
            },
            {
                "user_question": "Тяжёлый день? Сколько было уроков?",
                "column_name": "Количество уроков",
                "type": "int",
                "min": 0,
                "max": 12
            }
        ]
        self.active_surveys = {}

    async def send_consent_request(self, chat_id: int, state: FSMContext):
        try:
            markup = types.ReplyKeyboardMarkup(
                keyboard=[
                    [types.KeyboardButton(text="Согласен"), types.KeyboardButton(text="Отказаться")]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            await self.bot.send_message(
                chat_id,
                "📝 Подтвердите согласие на обработку данных:",
                reply_markup=markup
            )
            await state.set_state(SurveyStates.CONSENT) 
            logger.info(f"Состояние CONSENT установлено для {chat_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки клавиатуры: {e}")
            await self.bot.send_message(chat_id, "⚠️ Ошибка. Попробуйте позже.")

    async def handle_consent(self, message: types.Message, state: FSMContext):
        if message.text == "Согласен":
            self.data_processor._update_users_file(message.chat.id)
            await message.answer("✅ Согласие принято. Добро пожаловать в ПсихоРитм! Что случилось?")
            await state.clear()
        else:
            await message.answer("❌ Согласие отклонено.")
            await state.clear()

    async def _start_survey(self, chat_id: int, state: FSMContext):
        await self.bot.send_message(
            chat_id,  
            "📝 Начинаем ежедневный опрос!",
            reply_markup=types.ReplyKeyboardRemove()
        )
        self.active_surveys[chat_id] = True
        await state.set_data({
            'current_question': 0,
            'answers': {},
            'start_time': pd.Timestamp.now()
        })
        await self._ask_question(chat_id, 0)
        await state.set_state(SurveyStates.IN_PROGRESS)

    async def _ask_question(self, chat_id: int, question_num: int):
        question = self.questions[question_num]
        markup = self._get_markup_for_question(question)
        text = f"({question_num+1}/{len(self.questions)}) {question['user_question']}"
        
        await self.bot.send_message(
            chat_id,
            text,
            reply_markup=markup
        )

    def _get_markup_for_question(self, question):
        if question['type'] == 'category':
            buttons = [[types.KeyboardButton(text=option)] for option in question['options']]
            return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        return types.ReplyKeyboardRemove()

    async def handle_answer(self, message: types.Message, state: FSMContext):
        data = await state.get_data()
        current_q = data['current_question']
        question = self.questions[current_q]
        
        if not self._validate_answer(question, message.text):
            await message.answer("⚠️ Пожалуйста, введите корректные данные")
            return

        data['answers'][question['column_name']] = message.text
        await state.update_data(answers=data['answers'])
        
        if current_q + 1 < len(self.questions):
            await state.update_data(current_question=current_q + 1)
            await self._ask_question(message.chat.id, current_q + 1)
        else:
            await self._complete_survey(message.chat.id, data, state)

    def _validate_answer(self, question, answer):
        if question['type'] == 'int':
            if not answer.isdigit():
                return False
            value = int(answer)
            return question['min'] <= value <= question['max']
        
        elif question['type'] == 'float':
            try:
                value = float(answer)
                return question['min'] <= value <= question['max']
            except ValueError:
                return False
        
        elif question['type'] == 'time':
            try:
                hours, minutes = map(int, answer.replace('.', ':').split(':'))
                return 0 <= hours < 24 and 0 <= minutes < 60
            except:
                return False
        
        elif question['type'] == 'category':
            return answer in question['options']
        
        return True

    async def _complete_survey(self, chat_id: int, data: dict, state: FSMContext):
        try:
            self.data_processor.save_response(chat_id, data['answers'])
            await self.bot.send_message(
                chat_id,
                "📊 Спасибо за прохождение опроса! Ваши ответы сохранены.",
                reply_markup=types.ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")
            await self.bot.send_message(chat_id, "⚠️ Ошибка сохранения данных")
        finally:
            self.active_surveys[chat_id] = False  
            await state.clear()  
            logger.info(f"Состояние пользователя {chat_id} сброшено")

    async def is_survey_in_progress(self, chat_id: int) -> bool:
        return self.active_surveys.get(chat_id, False)

    async def run_scheduled_survey(self) -> bool:
            try:
                logger.info("=== ЗАПУСК ОПРОСА АДМИНИСТРАТОРОМ ===")
                
                if not os.path.exists("users.csv"):
                    logger.error("❌ Файл users.csv не найден!")
                    return False

                user_ids = pd.read_csv("users.csv")['user_id'].astype(int).tolist()
                admin_ids = [7687534894]  
                user_ids = [uid for uid in user_ids if uid not in admin_ids]
                logger.info(f"Найдено пользователей: {len(user_ids)}")

                success = 0
                for user_id in user_ids:
                    try:
                        storage_key = StorageKey(
                            chat_id=user_id,
                            user_id=user_id,
                            bot_id=self.bot.id
                        )
                        user_state = FSMContext(storage=self.storage, key=storage_key) 
                        
                        await self._start_survey(user_id, user_state)
                        success += 1
                        logger.info(f"✅ Опрос запущен для {user_id}")
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка для {user_id}: {traceback.format_exc()}")
                
                logger.info(f"Успешно запущено: {success}/{len(user_ids)}")
                return success > 0

            except Exception as e:
                logger.critical(f"💥 Критическая ошибка: {traceback.format_exc()}")
                return False