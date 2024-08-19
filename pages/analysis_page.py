import streamlit as st
import pandas as pd
import src.streamlit_helpers as h
from src.models import *
from src.config import Session
import sys
import dateutil
import streamlit_tags

st.set_page_config(page_title=f"analysis page", page_icon="🏖️")

##################### VARIABLES AND FUNCTION CALLS #####################
user = st.session_state.get('user', False)
df_edited = st.session_state.get('new_user_df', pd.DataFrame())

if df_edited.empty:
       st.write("Please go back to the main page and click submit when you are done.")

else:

      ########################## INITALIZE #####################################
      categories = tuple(set(df_edited['category'].to_list()))

      st.header("Category Selection")
      st.caption(f'List of categories: {categories}')
      keyword = streamlit_tags.st_tags(
            label='Enter Categories you would like to exclude from analysis:',
            text='Press enter to add more.',
            value=['credit_card_payment', 'my_account_transfer'],
            suggestions= categories,
            key='1')
      

      #################### START OF VARIABLES AND FUNCTION CALLS ####################
      df = df_edited.copy() # use this for data manipulation
      df = df[~df['category'].isin(keyword)] # drop selected categories
      # Get net spending per currency
      amount_per_currency = h.get_amount_per_currency(df, ['₩','$'])
      won_net = amount_per_currency[0]
      dollar_net = amount_per_currency[1]

      # Convert all amounts to dollars for data analysis
      df['dollar_amount'] = df.apply(h.amount_to_dollars, axis=1)

      # SPENDINGS
      df_spendings = h.split_finances(df, 'spendings')
      spendings = df_spendings['spendings'].sum()

      df_category_spendings = h.get_df_grouped_by_category(df_spendings, 'spendings')
      top_categories = h.get_top_n_categories(df_spendings, 'spendings', 3)
      top_categories_date_diff = []
      for cat in top_categories:
            top_categories_date_diff.append((cat,h.calculate_date_diff(df_spendings, cat)))

      avg_spending_per_time = h.calculate_avg_amount_per_time(df, 'dollar_amount', 'D', ['leisure', 'transportation'])                  
      # EARNINGS
      df_earnings = h.split_finances(df, 'earnings')
      earnings = df_earnings['earnings'].sum()
      avg_earning_per_time = h.calculate_avg_amount_per_time(df, 'dollar_amount', 'W')

      #################### END OF VARIABLES AND FUNCTION CALLS ####################

      st.write(f"Won Net: {amount_per_currency[0]}")
      st.write(f"Dollar Net: {amount_per_currency[1]}")

      st.subheader("Spendings")
      st.write("by category")
      col1, col2 = st.columns(spec=[0.7,0.3])
      col1.bar_chart(data=df_spendings, x="category", y="spendings", color="#DD66E0")

      top_categories_str = ' '.join(top_categories)
      st.write(top_categories_str)
      col2.write(f"***top categories:*** `{top_categories_str}`")
      if col2.checkbox(f'show full dataset'):
            col2.write('spending by category')
            col2.dataframe(df_category_spendings, hide_index=True)

      col2.write(f"""spent {int(spendings)} dollars in total""")

      st.subheader("over time")
      st.bar_chart(df_spendings, x="date", y="spendings", color="category")
      st.write(f"""
      - Data is from `{min(df['date'])}` to `{max(df['date'])}`
      - On average, I spent `{round(avg_spending_per_time,2)}` per day.
      """)
      for avg_date_diff in top_categories_date_diff:
            if isinstance(avg_date_diff[1], float):
                  st.write(f"Every `{round(avg_date_diff[1],2)}` days on average I had an expense in the category {avg_date_diff[0]}")
            else:
                  st.write(avg_date_diff[1])

      st.subheader("earnings")
      col1, col2 = st.columns([0.5,0.5])
      col1.bar_chart(data= df_earnings, x="date", y="earnings", color="category")
      col2.write(f"""
      Total earnings is `{round(earnings,2)}` dollars.\n
      Average earnings per week is `{round(avg_earning_per_time,2)}` dollars.
      """)
      if col2.checkbox(f'show full dataset', key="earnings"):
            col2.write('earnings dataframe')
            col2.dataframe(df_earnings.drop(columns=['transaction_id', 'earnings']), hide_index=True)

      st.subheader("Net")
      st.write(f"""
      - In total, my net is `{won_net}` won and `{dollar_net}` dollars from
      `{min(df['date'])}` to `{max(df['date'])}`
      - in dollars, this adds up to `${won_net*h.CURRENCY_WON_TO_DOLLAR+dollar_net}`
      - in won, this adds up to `₩{won_net+dollar_net*h.CURRENCY_DOLLAR_TO_WON}`
      """)

      st.header("Specific Category")
      category = st.selectbox("What category would you like to know more about?",
                   categories,
                   index=None,
                  placeholder="Select category..."
      )
      df_category = df_edited[df_edited['category']==category].drop('transaction_id',axis=1)
      st.dataframe(df_category)

      st.header('reflections')
      st.subheader("Read past reflections:")
      with Session() as db:
            past_comments = Comment.get_all_comments(db, user.user_id)
            if not past_comments:
                  st.write("No comments yet!")
            else:
                  for ps in past_comments:
                        st.write(f"`{ps.title}`")
                        st.caption(ps.date)
                        st.write(ps.body)
                        st.divider()

      st.subheader("Add a new reflection:")
      title = st.text_input("What are your thoughts after reviewing the statement stats?", "title")
      body = st.text_area("body:", "write your thoughts here")
      if st.button("submit"):
            with Session() as db:
                  Comment.create_comment(db, title, body, user.user_id)
            st.write("comment submitted!")
                  