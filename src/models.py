from sqlalchemy import Column, Integer, String, ForeignKey, Table, Float, Date, func
from sqlalchemy.orm import relationship, backref, joinedload
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
import pandas as pd
from pypdf import PdfReader
import re
from pydantic import BaseModel
import openai
from tqdm.auto import tqdm
from typing import Optional
from loguru import logger
from enum import Enum
import os
from collections import defaultdict
import dateutil
from datetime import datetime, date

Base = declarative_base()
payment = ['payment - thank you', 'credit card bill payment'] # always stays same

class User(Base): 
    __tablename__ = "user"
    user_id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    statements = relationship("Statement", cascade="all, delete-orphan", back_populates="user")
    transactions = relationship("Transaction", cascade="all, delete-orphan", back_populates="user")
    comment = relationship("Comment", back_populates="user")

    def get_user_df(self, db: Session, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Method to read in the user data and return a Pandas dataframe with transactions between `start_date` and `end_date`
        for Streamlit use ordered by date

        Returns:
            pd.DataFrame: with columns ['transaaction_id', 'date', 'amount', 'category', 'place', 'st_type', 'page_num', 'acc_last_4_digits']
        """
        transactions = db.query(Transaction).options(
            joinedload(Transaction.gpt_label), 
            joinedload(Transaction.statement)
        ).filter(
            Transaction.user_id == self.user_id, 
            Transaction.date >= start_date,
            Transaction.date <= end_date
            ).order_by(Transaction.date.asc()).all()
        data = []
        for transaction in transactions:
            row = {
                'transaction_id': transaction.transaction_id,
                'date': transaction.date,
                'amount': transaction.amount,
                'description': transaction.description,
                'category': transaction.gpt_label.category,
                'place': transaction.gpt_label.place,
                'st_type': transaction.statement.st_type,
                'currency': transaction.statement.currency,
                'acc_last_4_digits': transaction.statement.acc_last_4_digits,
            }      
            data.append(row)
        return pd.DataFrame(data)
    
    def get_in_db(self, db: Session):
        """
        checks if user obj already exists in db (same first/last name)
        and returns the db obj it does, None if it not in db
        """
        return db.query(User).filter(User.first_name == self.first_name, User.last_name == self.last_name).first()
    
    @staticmethod
    def get_by_user_id(db, user_id):
        """retrieves user obj given user_id"""
        return db.query(User).filter(User.user_id == user_id).first()
    
    @staticmethod
    def get_by_first_last_name(db, first_name, last_name):
        """retrieves user obj given first name and last name"""
        return db.query(User).filter(User.first_name == first_name, User.last_name == last_name).first()
    
    @staticmethod
    def delete_by_user_id(db, user_id):
        """deletes user obj given user_id"""
        user = User.get_by_user_id(db, user_id)
        if user:
            db.delete(user)
            db.commit()

class Statement(Base):
    __tablename__ = "statement"
    statement_id = Column(Integer, primary_key=True)
    st_type = Column(String)
    st_name = Column(String)
    page_num = Column(Integer)
    st_text = Column(String)
    currency = Column(String)
    acc_last_4_digits = Column(Integer)
    user_id = Column(Integer, ForeignKey("user.user_id"))
    user = relationship("User", back_populates="statements")
    transactions = relationship("Transaction", cascade="all, delete-orphan", back_populates="statement")

    def get_in_db(self, db: Session):
        """
        checks if Statement obj is already in db (same name and account number)
        and returns the db obj it does, None if it not in db
        """
        return db.query(Statement).filter(Statement.user_id == self.user_id, Statement.st_name == self.st_name, Statement.acc_last_4_digits == self.acc_last_4_digits).first()
    
    def _parse_statement(self, file):
        """
        Given a pdf file, parses it and adds the extracted info to the statement obj

        Returns:
            Statement: obj with the newly added information
        """
        self.st_name = file.name
        reader = PdfReader(file)
        self.page_num = len(reader.pages)

        # Extract info from first page
        first_page = reader.pages[0]
        currency_symbols = {'$','₩'}
        first_page_text = first_page.extract_text(extraction_mode='layout', layout_mode_space_vertically=False)
        pattern = re.compile(r'Account [Nn]umber:\s+.*\b(\d{4})$')
        lines = [' '.join(line.split()) for line in first_page_text.split('\n') if line.strip()]
        for line in lines:
            match_acc = pattern.search(line)
            if match_acc:
                self.acc_last_4_digits = int(match_acc.group(1))
                break

        for currency in currency_symbols:
            if currency in first_page_text:
                self.currency = currency
                break
        
        # Extract text from all pages
        st_text = ""
        for page in reader.pages:
            page_text = page.extract_text(extraction_mode='layout', layout_mode_space_vertically=False)
            st_text = st_text + "\n" + page_text
        self.st_text = st_text

        return self
    
    def get_in_db(self, db: Session):
        """
        checks if statement obj already exists in db (same user, st_text)
        and returns the db obj it does, None if it not in db
        """
        return db.query(Statement).filter(Statement.user_id == self.user_id, Statement.st_text == self.st_text).first()
    
class Transaction(Base):
    __tablename__ = "transaction"
    transaction_id = Column(Integer, primary_key=True)
    date = Column(Date)
    description = Column(String)
    amount = Column(Float)
    user_id = Column(Integer, ForeignKey("user.user_id"))
    statement_id = Column(Integer, ForeignKey("statement.statement_id"))
    gpt_label_id = Column(Integer, ForeignKey("gptLabel.gpt_label_id"))
    user = relationship("User", back_populates="transactions")
    gpt_label = relationship("GPTLabel", back_populates="transactions")
    statement = relationship("Statement", back_populates = "transactions")

    @staticmethod
    def create_transactions(db: Session, st: Statement) -> list:
        """
        Given a statement object, accesses the statement text and processes the transactions on each line
        
        Returns:
            list: of transaction objects
        """
        tr_list = []
        statement_text = st.st_text
        lines = [' '.join(line.split()) for line in statement_text.split('\n') if line.strip(' ')]
        pattern = re.compile(r'(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)\s+(-?\d{1,3}(?:,\d{3})*(?:\.\d{2}))$')

        # Custom heuristics
        for line in lines:
            match = pattern.search(line)
            if match:
                date = dateutil.parser.parse(match.group(1))
                raw_desc = match.group(2)
                amount = float(match.group(3).replace(',', ''))
                
                clean_desc_pattern = re.compile(r'^(\d{2}/\d{2}(?:/\d{2,4})?)\s*|(\d{4}\s\d{4})$')
                desc = clean_desc_pattern.sub('', raw_desc).strip()
        
                if not desc.lower().startswith('page'):
                    desc = ' '.join(word.capitalize() for word in desc.lower().split(' '))
                    if st.st_type == 'credit_card' and not any(exc in desc.lower() for exc in payment):
                        # convert liabilites to negative values
                        tr = Transaction(user_id = st.user_id, statement_id = st.statement_id, date = date, description = desc, amount = -amount)
                    else:
                        tr = Transaction(user_id = st.user_id, statement_id = st.statement_id, date = date, description = desc, amount = amount)
                    db.add(tr)
                    db.commit()
                    db.refresh(tr)
                    tr_list.append(tr)
        return tr_list 
    
    @staticmethod
    def get_transaction_dates(db, user_id) -> list:
        """ 
        Returns:
            list: of all transaction dates given user_id
        """ 
        dates = db.query(Transaction.date).filter(Transaction.user_id == user_id).order_by(Transaction.date.asc()).all()
        return [date[0] for date in dates]

class GPTLabel(Base):
    __tablename__ = "gptLabel"
    gpt_label_id = Column(Integer, primary_key=True)
    category = Column(String)
    place = Column(String)
    user_id = Column(Integer, ForeignKey("user.user_id"))
    transactions = relationship("Transaction", back_populates="gpt_label")

    @staticmethod
    def set_gpt_label(db: Session, tr: Transaction) -> None:
        """
        If transaction description has been seen before, set trasaction's gpt_label to the existing gpt_label.
        Else, create a new gpt_label and assign transaction's gpt_label to that. 
        """
        existing_gpt_label = db.query(GPTLabel).join(Transaction).filter(Transaction.description==tr.description, Transaction.gpt_label_id != None).first()
        if existing_gpt_label:
            tr.gpt_label_id = existing_gpt_label.gpt_label_id
        else:
            # never seen this description before, calling GPT 4o API
            category, place = GPTLabel._parse_description(tr.description)
            gpt_label = GPTLabel(category = category, place = place, user_id = tr.user_id)
            db.add(gpt_label)
            db.commit()
            db.refresh(gpt_label)
            tr.gpt_label_id = gpt_label.gpt_label_id
    
    @staticmethod
    def update_gpt_label(db: Session, transaction: Transaction, new_category = None, new_place = None) -> None:
        """
        Method that updates the gpt labels (category, place) of the transaction description
        """
        if not transaction or not transaction.gpt_label: 
            raise ValueError("Transaction not found while trying to update GPT label")
        if new_category:
            transaction.gpt_label.category = new_category
        if new_place:
            transaction.gpt_label.place = new_place
        db.commit()

    @staticmethod
    def validate_gpt_labels(db: Session, old_user_df: pd.DataFrame, new_user_df: pd.DataFrame) -> None:
        """
        Given two user dataframes, locate what GPT labels changed and update the db
        """
        diff = old_user_df.compare(new_user_df)
        if diff.empty:
            logger.info("no user feedback")
            return
        changed_indices = diff.index.get_level_values(0)
        for i in changed_indices: 
            updated_row = new_user_df.loc[i, ['description', 'category', 'place']].to_dict()
            transaction  = db.query(Transaction).filter(Transaction.description == updated_row['description']).first()
            GPTLabel.update_gpt_label(db, transaction, updated_row['category'], updated_row['place'])
        logger.info("user feedback detected and updated")
        

    @staticmethod
    def _parse_description(desc) -> tuple:
        """
        Method that given a single description, parses it using GPT-4o

        Returns:
            tuple: (str, str, str) = (verified_description, category column, place column)
            `verified_description` is to reflect optional user changes on the description on the streamlit page
        """
        # never seen this description before, calling GPT 4o API
        client = openai.OpenAI(
        api_key = openai.api_key,
        )

        # Custom heuristics
        if any(exc in desc.lower() for exc in payment):
            return Category.credit_card_payment.value, None
        elif 'online banking transfer' in desc.lower() or 'online banking payment' in desc.lower():
            return "my_account_transfer", None
        elif "zelle" in desc.lower() or "venmo" in desc.lower():
            return Category.cash_transfer.value, None
        elif "payroll" in desc.lower():
            return "payroll", None
        # GPT API Call
        else:
            completion = client.beta.chat.completions.parse(
                model='gpt-4o-2024-08-06',
                messages=[
                            {"role": "system", "content": 
                            "You are a highly accurate assistant tasked with categorizing bank transaction descriptions. "
                            "Your main goals are: "
                            "1. Identify and return the main category of the transaction. "
                            "2. If a place of transaction is mentioned, return the place. "
                            "When identifying the category, always prioritize the first relevant term in the description. "
                            "If multiple categories apply, select the one that best matches the first relevant term. "
                            "If a description involves a recurring payment or known entities like 'Zelle' or 'Venmo', consider them as 'cash_transfer'. "
                            "If the category is unclear, try to infer based on common transaction patterns but avoid guessing if unsure."},
                            {"role": "user", "content": desc},
                        ],
                response_format = Parsed_description
            )
            try:
                parsed = completion.choices[0].message.parsed
                return parsed.category.value, parsed.place
            except Exception as e:
                raise Exception(f"Failed to parse description {desc}: {e} ")
        
class Comment(Base):
    __tablename__ = "comment"
    comment_id = Column(Integer, primary_key=True)
    title = Column(String)
    date = Column(Date)
    body = Column(String)
    user_id = Column(Integer, ForeignKey("user.user_id"))
    user = relationship("User", back_populates="comment")

    @staticmethod
    def create_comment(db, title, body, user_id):
        """creates a comment obj given a title, body, and user_id and returns it"""
        comment = Comment(title = title, date = datetime.now().date(), body = body, user_id = user_id)
        db.add(comment)
        db.commit()
        db.refresh(comment)
        return comment
    
    @staticmethod
    def get_all_comments(db: Session, user_id):
        """
        finds and returns all comments of user `user_id`.
        """
        return db.query(Comment).filter(Comment.user_id == user_id).all()
    
def updates_database(db: Session, first_name: str, last_name: str, uploaded_files_cc: list, uploaded_files_acc: list) -> None:
    """
    Main function that updates the db given the user name and the statement files
    """
    user = User(first_name = first_name, last_name = last_name)
    uploaded_files = [(cc_statement,'credit_card') for cc_statement in uploaded_files_cc]
    uploaded_files.extend([(acc_statement,'bank_account') for acc_statement in uploaded_files_acc])
    if not user.get_in_db(db):
        # Add new user
        db.add(user)
        db.commit()
        db.refresh(user)
    user = user.get_in_db(db)
    user_id = user.user_id
    try:
        # Create statements
        for file, st_type in uploaded_files: 
            st = Statement(user_id = user_id, st_type = st_type)._parse_statement(file)
            if not st.get_in_db(db):
                db.add(st)
                db.commit()
                db.refresh(st)
                # create transactions
                tr_list = Transaction.create_transactions(db, st) # gpt label set as empty 
                for tr in tqdm(tr_list): 
                    GPTLabel.set_gpt_label(db,tr) # assign gpt label
                    db.commit()
                    db.refresh(tr)
    except Exception as e: # if something goes wrong, clean up
        logger.error(f"Error {e}Something went wrong as a user was being added to DB.")
        db.rollback()
        user = db.query(User).filter_by(user_id=user_id).first()
        if user:
            db.delete(user)
            db.commit()


# Prepare structured ouput for GPT response
class Category(str, Enum):
    income = "income"
    investment = "investment"
    cash_transfer = "cash_transfer"
    credit_card_payment = "credit_card_payment"
    interest = "interest"
    tax = "tax"
    grocery = "grocery"
    delivery = "delivery"
    dine_out = "dine_out"
    transportation = "transportation"
    subscription = "subscription"
    housing = "housing"
    healthcare = "healthcare"
    insurance = "insurance"
    shopping = "shopping"
    leisure = "leisure"
    other = "other"

class Parsed_description(BaseModel):
    category: Category
    place: Optional[str]