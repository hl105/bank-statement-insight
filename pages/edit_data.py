import streamlit as st
import pandas as pd
import src.streamlit_helpers as h
from src.models import *
from src.config import Session
import sys

st.set_page_config(page_title=f"Edit Data", page_icon="🏖️")

user =  st.session_state.get('user', False)
if not user:
    st.write("Please go back to the main page and click submit when you are done.")

##################### STREAMLIT PAGE #####################

else:
    with Session() as db:
        all_transaction_dates = Transaction.get_transaction_dates(db, user.user_id)

    st.title(f"{user.first_name}'s Statement Analysis")

    st.subheader("Timeframe Selection")
    st.write('Choose timeframe of transactions that you want to consider:')
    start_date, end_date = st.select_slider(
        "Select a range of dates",
        options=all_transaction_dates,
        value=(all_transaction_dates[0],all_transaction_dates[-1])
    )
    st.subheader("GPT Label validation")
    st.write("""You also have to validate the columns: `category` and `place`. 
                The categories were classifed using OpenAI's GPT-4o API, and thus can be wrong. 
                Please edit the following table accordingly, and when you are done click `submit`.
                """)
    with Session() as db:
        old_user_df = user.get_user_df(db, start_date, end_date)
        new_user_df = st.data_editor(data=old_user_df, hide_index=True, column_order=('date','description', 'category', 'place', 'amount', 'acc_last_4_digits', 'st_type','currency'))

        st.caption("the fixed categories will be saved in a local database so that the mistake is not repeated.")
        st.caption("No data processed by the API is used to train models unless the user has opted IN. Only the transaction description is passed to the API.")
        
        if st.button("submit"):
            GPTLabel.validate_gpt_labels(db, old_user_df, new_user_df)
            st.session_state['new_user_df'] = new_user_df
            st.switch_page("pages/analysis_page.py")
