import pandas as pd
import streamlit as st
import sys
from loguru import logger

CURRENCY_WON_TO_DOLLAR = 0.00072
CURRENCY_DOLLAR_TO_WON = 1381


@st.cache_data
def get_amount_per_currency(df, currencies: list[str]) -> list[int]:
    """
    Method that calculates the net ammount spent per currency in the given list `currencies` from `df`.

    Returns:
        list: of amount spent per currency in the same order given by `currencies`
    """
    currency_grouped = df.groupby('currency')['amount'].sum().to_dict()
    amount_per_currency = []
    for currency in currencies:
        amount_per_currency.append(int(currency_grouped.get(currency, 0)))
    return amount_per_currency

@st.cache_data
def amount_to_dollars(row):
    if row['currency'] == '₩':
        dollar_amount = CURRENCY_WON_TO_DOLLAR*row['amount']
        return dollar_amount
    # you can add elif other currency to dollar here
    else: # currency is dollar
        return row['amount']

@st.cache_data   
def calculate_date_diff(df, colName) -> int:
    """
    Method to calculate the average gap of days between the transactions of the given category 

    Returns:
        int: average gap of days between the transactions of the given category 
    """
    df_category = df[df['category']==colName].copy()
    if df_category.shape[0]>1: # if more than 1 row
        df_category['date_diff'] = df_category['date'].diff().apply(lambda x: x.days)
        return df_category['date_diff'].mean()
    else:
        return f"only 1 entry in {colName}"

@st.cache_data
def calculate_avg_amount_per_time(df, amount_col, freq: str, exclude_categories: list = []) -> float:
    """
    Method to calculate average spending per day excluding categories `exclude_categories`
    
    Params:
        df: Pandas dataframe
        amount_col: the amount column we want to calculate the average per day from
        freq: one of date offset frequency aliases. e.g. '10D' or 'W'
        exclude: columns to exclude 
    
    Returns:
        float: average spending per day exlcluding specified categories 
    """
    # Convert from date obj to to datetime obj for grouping
    df['date'] = pd.to_datetime(df['date']) 
    # filter categories
    df_cat_excluded = df[~df['category'].isin(exclude_categories)]
    grouped_by_time = df_cat_excluded.groupby(pd.Grouper(key='date', freq=freq))
    return grouped_by_time[amount_col].sum().reset_index()[amount_col].mean()

@st.cache_data
def get_df_grouped_by_category(df, amount_col):
    df_category_spendings = df.groupby(['category'])[amount_col].sum().sort_values(ascending=False).reset_index()
    return df_category_spendings

@st.cache_data
def get_top_n_categories(df, amount_col, n) -> list:
    """
    Method to get the names of the top `n` categories in the column `category`.
    by the column `amount_col` of the given dataframe `df`

    Returns:
        list: of the top n names
    """
    df_category_spendings = get_df_grouped_by_category(df, amount_col)
    top_n_categories = df_category_spendings['category'][:n].to_list()
    return top_n_categories

@st.cache_data
def split_finances(df, finance_type) -> pd.DataFrame:
    """
    Method that returns:
    - IF 'spendings' a `spendings` dataframe with only negative `dollar_amounts`.
    Also renames positive `dollar_amount` as `spendings`.

    Returns:
        pd.DataFrame: altered subset of `df` that only contains spendings/earnings. 
    """
    valid = {'spendings','earnings'}
    if finance_type not in valid:
        raise ValueError(f"results: status must be one of {valid}")
    
    if finance_type == 'spendings':
        df_spendings = df[df['dollar_amount'] < 0].copy()
        df_spendings['dollar_amount'] = df_spendings['dollar_amount'] * -1 # make spendings positive for barplot 
        df_spendings_renamed = df_spendings.rename(columns={'dollar_amount': 'spendings'})
        return df_spendings_renamed
    elif finance_type == "earnings":
        df_earnings = df[df['dollar_amount'] >= 0].copy()
        df_earnings_renamed = df_earnings.rename(columns={'dollar_amount': 'earnings'})
        return df_earnings_renamed        