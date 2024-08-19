from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import openai
import os
from src.models import Base
import logging
from loguru import logger

def configure_openai():
        """
        Method that sents up the OpenAI API call environment
        """
        try:
            with open(os.path.join(os.getcwd(), 'api_key'), 'r') as f:
                openai.api_key = f.read().strip()
                if not openai.api_key:
                    raise Exception("no api key!")
        except Exception as e:
            openai.api_key = input("API Key not found! Input your API Key here\n:")
            with open('./api_key', 'w') as f:
                f.write(openai.api_key)
        
# Logger Config
log_level = "INFO"
log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS zz}</green> | <level>{level: <8}</level> | <yellow>Line {line: >4} ({file}):</yellow> <b>{message}</b>"
logger.remove()
logger.add("file.log", level=log_level, format=log_format, colorize=False, backtrace=True, diagnose=True)


DATABASE_URL = "sqlite:///./user_db.db"

engine = create_engine(DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
configure_openai()



