import pandas as pd
import numpy as np
import logging
import traceback
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from joblib import load
from tensorflow.keras.models import load_model
import os

logger = logging.getLogger(__name__)

class DataProcessor:
    def _update_users_file(self, user_id: int):
        try:
            users_file = "users.csv"
            
            if not os.path.exists(users_file):
                pd.DataFrame(columns=["user_id"]).to_csv(users_file, index=False)
            
            users_df = pd.read_csv(users_file)
            if user_id not in users_df["user_id"].values:
                users_df = pd.concat([users_df, pd.DataFrame({"user_id": [user_id]})], ignore_index=True)
                users_df.to_csv(users_file, index=False)
                logger.info(f"Пользователь {user_id} добавлен в users.csv")
                
        except Exception as e:
            logger.error(f"Ошибка обновления users.csv: {str(e)}")

    def save_response(self, user_id: int, answers: dict):
        try:
            response_data = pd.DataFrame([answers])
            response_data["user_id"] = user_id
            response_data["timestamp"] = pd.Timestamp.now()

            if not os.path.exists("survey_data.csv"):
                response_data.to_csv("survey_data.csv", index=False)
            else:
                response_data.to_csv("survey_data.csv", mode='a', header=False, index=False)

            logger.info(f"Ответы пользователя {user_id} сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения ответов: {str(e)}")
            raise

    def __init__(self):
        self.preprocessor = load('preprocessor.joblib')
        self.autoencoder = load_model('model.h5')
        self.required_columns = [
            'Шаги', 'Время активности', 'Средний пульс', 'Длительность сна',
            'Качество сна', 'Время засыпания', 'Время пробуждения', 
            'Стресс', 'Возраст', 'Пол', 'Количество уроков'
        ]
        self.sleep_mapping = {
            'отлично': 'хороший', 'хорошо': 'хороший',
            'удовлетворительно': 'средний', 'плохо': 'плохой',
            'unknown': 'unknown'
        }

    def _preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        missing = [col for col in self.required_columns if col not in data.columns]
        if missing:
            raise ValueError(f"Отсутствуют столбцы: {missing}")

        data['Время засыпания'] = data['Время засыпания'].apply(self._convert_time)
        data['Время пробуждения'] = data['Время пробуждения'].apply(self._convert_time)

        data['Время засыпания'] = data['Время засыпания'].fillna(data['Время засыпания'].median())
        data['Время пробуждения'] = data['Время пробуждения'].fillna(data['Время пробуждения'].median())

        data['Качество сна'] = (
            data['Качество сна']
            .astype(str).str.lower()
            .replace(self.sleep_mapping)
            .fillna('unknown')
        )
        
        data['Стресс'] = data['Стресс'].apply(lambda x: 'Да' if str(x).lower() != 'нет' else 'Нет')
        data['Пол'] = (
            data['Пол']
            .str.strip().str.lower()
            .replace({'мужской': 'мужской', 'женский': 'женский'})
            .fillna('unknown')
        )

        data['Количество уроков'] = data['Количество уроков'].apply(self._process_lessons)
        
        return data

    def _convert_time(self, time_str: str) -> int:
        try:
            time_str = str(time_str).replace('.', ':').replace(',', ':')
            h, m = map(int, time_str.split(':'))
            return h * 60 + m
        except:
            return np.nan

    def _process_lessons(self, lessons: str) -> float:
        lessons = str(lessons).strip()
        if lessons.lower() == 'все':
            return 8.0
        elif '-' in lessons:
            parts = lessons.split('-')
            return (float(parts[0]) + float(parts[1])) / 2
        else:
            try:
                return float(lessons)
            except:
                return 0.0

    def process_all_data(self) -> bool:
        try:
            if not os.path.exists('survey_data.csv'):
                pd.DataFrame(columns=self.required_columns).to_csv('survey_data.csv', index=False)
                logger.info("Создан пустой файл данных")
            
            new_data = pd.read_csv('survey_data.csv', encoding='utf-8')
            new_data = self._preprocess_data(new_data)

            processed_data = self.preprocessor.transform(new_data)

            reconstructions = self.autoencoder.predict(processed_data)
            mse = np.mean(np.power(processed_data - reconstructions, 2), axis=1)
            threshold = np.percentile(mse, 95)
            
            new_data['Reconstruction_Error'] = mse
            new_data['Anomaly'] = (mse > threshold).astype(int)
            new_data.to_csv('analysis_results.csv', index=False)
            
            logger.info("Отчет успешно сформирован")
            return True
        except Exception as e:
            logger.error(f"Ошибка обработки: {traceback.format_exc()}")
            return False