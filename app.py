import streamlit as st
import pandas as pd
from io import BytesIO

from reddit_scanner import find_communities
from signal_finder import (
    initialize_reddit_client,
    find_buying_signals,
)

# --- Inlogscherm ---
def show_login_form():
    st.title("🚀 The Audience Finder PRO")
    st.header("Login")

    with st.form(key='login_form'):
        password = st.text_input("Please enter the password", type="password", label_visibility="collapsed")
        submitted = st.form_submit_button("Login")

        if submitted:
            if password == st.secrets.get("app_password", "test"):
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("🚨 The password you entered is incorrect.")

# --- Hoofdapplicatie ---
def show_main_app():
    st.title("🚀 The Audience Finder PRO")
    st.markdown("Discover relevant Reddit communities **and buying signals** based on your search queries.")

    st.header("1. Enter Your Search Queries")
    st.markdown("Enter one search query per line. Combine words on a single line for more specific results.")

    with st.form(key='search_form'):
        search_queries_input = st.text_area(
            "Label for screen readers, not displayed",
            label_visibility="collapsed",
            height=150,
            placeholder="For example:\nSaaS for startups\ndigital nomad\nproductivity tools"
        )
        find_button_submitted = st.form_submit_button("Find Communities", type="primary")

    if find_button_submitted:
        search_queries_list = [query.strip() for query in search_queries_input.split('\n') if query.strip()]
        
        if not search_queries_list:
            st.warning("Please enter at least one search query.")
        else:
            with st.spinner('🔍 Searching Reddit...'):
                try:
                    results_df = find_communities(search_queries_list)

                    if not results_df.empty:
                        df_for_display = results_df.copy()
                        df_for_download = results_df.copy()
                        df_for_download['Status'] = 'Not Started'
                        df_for_download['Priority'] = ''
                        df_for_download['Notes'] = ''
                        df_for_download['Last Contact'] = ''

                        st.session_state["audience_display"] = df_for_display
                        st.session_state["audience_download"] = df_for_download
                    else:
                        st.session_state["audience_display"] = None
                        st.session_state["audience_download"] = None

                except Exception as e:
                    st.error(f"An error occurred: {e}")

    st.header("2. Discovered Communities")

    if st.session_state.get("audience_display") is not None:
        st.dataframe(st.session_state["audience_display"], use_container_width=True)
    else:
        st.write("—")

    st.header("3. Download Your Results")

    if st.session_state.get("audience_download") is not None:
        csv_data = st.session_state["audience_download"].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download as CSV",
            data=csv_data,
            file_name='audience_finder_results.csv',
            mime='text/csv'
        )
    else:
        st.write("—")

    # --- Koopsignalen Scan ---
    st.header("4. Buying Signal Scanner (Pro Feature)")

    time_filter = st.radio(
        "Select time frame for top posts",
        options=["day", "week", "month", "year", "all"],
        index=2,
        horizontal=True
    )

    # --- Preset keuze met tooltip ---
    st.markdown("**Scan Intensity**")
    preset = st.radio(
        label="Choose scan depth",
        options=["🟢 Fast (10 posts / 20 comments)", 
                "🔵 Standard (50 / 100)", 
                "🔴 Deep (100 / 500)", 
                "⚙️ Custom"],
        index=1,
        horizontal=True,
        help=(
            "🟢 Fast: Quick test with minimal depth.\n"
            "🔵 Standard: Balanced speed and coverage.\n"
            "🔴 Deep: Slower, but finds more signals.\n"
            "⚙️ Custom: Set your own limits below."
        )
    )
    # --- Limieten instellen op basis van preset ---
    if preset.startswith("🟢"):
        post_limit = 10
        comment_limit = 20
    elif preset.startswith("🔵"):
        post_limit = 50
        comment_limit = 100
    elif preset.startswith("🔴"):
        post_limit = 100
        comment_limit = 500
    else:
        col1, col2 = st.columns(2)
        with col1:
            post_limit = st.number_input(
                "Number of top posts per subreddit",
                min_value=1,
                max_value=100,
                value=50,
                step=1
            )
        with col2:
            comment_limit = st.number_input(
                "Max comments per post",
                min_value=0,
                max_value=500,
                value=100,
                step=10
            )


    subreddits_input = st.text_area(
        "Subreddits to scan (one per line)",
        placeholder="e.g. sidehustle\nsolopreneur\nstartups",
        height=200
    )

    keywords_input = st.text_area(
        "Pain point keywords to search for (one per line)",
        placeholder="e.g. find product-market fit\nmarket research\nwhere to post",
        height=200
    )

    if st.button("🔎 Run Buying Signal Scan"):
        custom_subreddits = [s.strip() for s in subreddits_input.split('\n') if s.strip()]
        custom_keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]

        if not custom_subreddits or not custom_keywords:
            st.warning("❗ Please fill in both subreddits and keywords before scanning.")
        else:
            with st.spinner("🔍 Initializing Reddit client..."):
                reddit = initialize_reddit_client()

            if reddit:
                total = len(custom_subreddits)
                results = []
                progress = st.progress(0.0, text="Starting scan...")

                for i, subreddit in enumerate(custom_subreddits):
                    progress.progress(i / total, text=f"Scanning r/{subreddit} ({i}/{total})...")  # 👈 begint bij 0/x
                    try:
                        signals = signals = find_buying_signals(reddit, [subreddit], custom_keywords, time_filter, post_limit, comment_limit)
                        results.extend(signals)
                        progress.progress((i + 1) / total, text=f"✅ Completed r/{subreddit} ({i+1}/{total})")
                    except Exception as e:
                        st.warning(f"❌ Error scanning r/{subreddit}: {e}")
                        progress.progress((i + 1) / total, text=f"⚠️ Skipped r/{subreddit} ({i+1}/{total})")

                progress.progress(1.0, text="🎉 All subreddits processed!")

                if results:
                    df_signals = pd.DataFrame(results)
                    st.session_state["signals_display"] = df_signals
                else:
                    st.session_state["signals_display"] = None
            else:
                st.error("❌ Failed to initialize Reddit client.")

    # --- Signalen tonen indien beschikbaar ---
    if st.session_state.get("signals_display") is not None:
        st.success(f"✅ Found {len(st.session_state['signals_display'])} buying signals.")
        st.dataframe(st.session_state["signals_display"], use_container_width=True)

        csv = st.session_state["signals_display"].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Signals as CSV",
            data=csv,
            file_name='buying_signals.csv',
            mime='text/csv'
        )

# --- App logica ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if st.session_state["logged_in"]:
    show_main_app()
else:
    show_login_form()