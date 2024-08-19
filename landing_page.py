import streamlit as st
from src.models import *
from src.config import Session

with st.form("form_statements"):

    first_name = st.text_input("Nice to see you! What is your first name? ღ'ᴗ'ღ", "first name")
    last_name = st.text_input("What is your last name?", "last name")

    uploaded_files_cc = st.file_uploader(
    "***Choose CREDIT CARD statements***, i.e. Please place all statements that have spendings as **positive** values here", accept_multiple_files=True, key ="cc"
    )

    uploaded_files_acc = st.file_uploader(
    "***Choose BANK ACCOUNT statements***, i.e. Please place all statements that have spendings as **negative** values here", accept_multiple_files=True, key = "bs"
    )

    # Every form must have a submit button.
    submitted = st.form_submit_button("Submit")
    st.write("The form may take a while to submit. You can track the process on the console")
    if submitted:
        with Session() as db:
            updates_database(db, first_name, last_name, uploaded_files_cc, uploaded_files_acc)
            user = User.get_by_first_last_name(db, first_name, last_name)
        st.session_state['user'] = user
        st.switch_page("pages/edit_data.py")

