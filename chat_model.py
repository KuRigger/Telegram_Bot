from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList
import torch
import logging
import os
import re
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class StopOnEOS(StoppingCriteria):
    def __call__(self, input_ids, scores, **kwargs):
        return input_ids[0][-1] == self.eos_token_id

    def __init__(self, eos_token_id):
        self.eos_token_id = eos_token_id

class ChatModel:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name = os.getenv("CHAT_MODEL_NAME", "ai-forever/rugpt3large_based_on_gpt2")
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            padding_side="left",
            truncation_side="left"
        )
        self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
        
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
            device_map="auto"
        ).eval()

        self.stopping_criteria = StoppingCriteriaList([
            StopOnEOS(self.tokenizer.eos_token_id)
        ])

        self.generation_config = {
            "max_new_tokens": 200,  
            "do_sample": True,
            "top_k": 40,
            "top_p": 0.9,
            "temperature": 0.6,  
            "repetition_penalty": 1.3,
            "no_repeat_ngram_size": 3,
            "stopping_criteria": self.stopping_criteria
        }

    async def generate_response(self, prompt: str, user_id: int) -> str:
        try:
            formatted_prompt = self._format_prompt(prompt)
            
            inputs = self.tokenizer(
                formatted_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=1024
            ).to(self.device)

            with torch.inference_mode():
                outputs = self.model.generate(
                    **inputs,
                    **self.generation_config
                )

            full_response = self.tokenizer.decode(
                outputs[0][inputs.input_ids.shape[-1]:], 
                skip_special_tokens=True
            )
            
            return self._postprocess_response(full_response)
        
        except Exception as e:
            logger.error(f"Generation error: {str(e)}")
            return "Извините, произошла ошибка обработки. Попробуйте переформулировать вопрос."

    def _format_prompt(self, prompt: str) -> str:
        return (
            "Ты — психологический помощник для школьников. Отвечай подробно 3-5 предложениями. "
            "Используй техники КПТ и mindfulness. Примеры ответов:\n"
            "1. 'Сделай дыхательное упражнение 4-7-8: вдох 4 сек, задержка 7 сек, выдох 8 сек.'\n"
            "2. 'Составь список дел по приоритетам. Начни с самых важных.'\n"
            f"Вопрос: {prompt}\nОтвет:"
        )
    
    def _postprocess_response(self, text: str) -> str:
        text = re.sub(r'(Пользователь:|Ассистент:|Вопрос:|Ответ:|\\n)', '', text)
        
        match = re.search(r'[.!?…]', text)
        if match:
            text = text[:match.end()]
        
        blacklist = ["жизнь", "смысл", "религия", "политика", "суицид"]
        if any(word in text.lower() for word in blacklist):
            return "Обратись к школьному психологу или позвони на горячую линию: 8-800-2000-122."
        
        if len(text) < 15:
            return "Уточни, пожалуйста, свой вопрос."
        
        return text.strip()