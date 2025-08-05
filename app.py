# app.py - Opportunity Finder v2.1 met Spinner en Geharmoniseerde UI

import streamlit as st
import pandas as pd
import numpy as np
import praw
from praw.exceptions import PRAWException
from prawcore.exceptions import NotFound, Forbidden, BadRequest

# --- Configuratie & Secrets ---
CLIENT_ID = st.secrets.get("reddit_client_id")
CLIENT_SECRET = st.secrets.get("reddit_client_secret")
APP_PASSWORD = st.secrets.get("app_password")
REDIRECT_URI = st.secrets.get("redirect_uri")

# --- Hybride Zoekfunctie (met de progress bar verwijderd) ---

def calculate_relevance_score(found_via_string):
    """Berekent een logische score op basis van de gevonden methodes."""
    score = 0
    if "Direct Search" in found_via_string: score += 1
    if "Relevant Post" in found_via_string: score += 2
    if "Relevant Comment" in found_via_string: score += 3
    return score

@st.cache_data(ttl=3600, show_spinner=False)
def find_communities_hybrid(_reddit_instance, search_queries: tuple, direct_limit: int, post_limit: int, comment_limit: int):
    # VERWIJDERD: De st.progress_bar is hier weggehaald, de spinner regelt dit nu.
    reddit = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, user_agent=f"OpportunityFinder by Boyd v2.1 (spinner_fix)", refresh_token=st.session_state.get("refresh_token"))
    aggregated_results = {}

    for query in search_queries:
        # Direct Search
        try:
            for sub in reddit.subreddits.search(query, limit=direct_limit):
                if sub.display_name.startswith('u_'): continue
                if sub.display_name not in aggregated_results: aggregated_results[sub.display_name] = {'Community': sub.display_name, 'Members': sub.subscribers, 'Found Via': set()}
                aggregated_results[sub.display_name]['Found Via'].add('Direct Search')
        except PRAWException: pass
        # Post & Comment Search
        try:
            for post in reddit.subreddit("all").search(query, sort="relevance", time_filter="month", limit=post_limit):
                if post.subreddit.display_name.startswith('u_') or post.subreddit.over18: continue
                community_name = post.subreddit.display_name
                if community_name not in aggregated_results: aggregated_results[community_name] = {'Community': community_name, 'Members': post.subreddit.subscribers, 'Found Via': set()}
                aggregated_results[community_name]['Found Via'].add('Relevant Post')
                if comment_limit > 0:
                    try:
                        post.comments.replace_more(limit=0)
                        for comment in post.comments.list()[:comment_limit]:
                            if hasattr(comment, 'body') and query.lower() in comment.body.lower():
                                aggregated_results[community_name]['Found Via'].add('Relevant Comment'); break
                    except Exception: continue
        except PRAWException: pass
    
    if not aggregated_results: return pd.DataFrame()

    final_list = [{'Community': f"r/{name}", **data} for name, data in aggregated_results.items()]
    df = pd.DataFrame(final_list)
    if df.empty: return df

    df['Found Via'] = df['Found Via'].apply(lambda s: ', '.join(sorted(list(s))))
    df['Relevance Score'] = df['Found Via'].apply(calculate_relevance_score)
    df['Community Link'] = df['Community'].apply(lambda name: f"https://www.reddit.com/{name}")
    df['Top Posts (Month)'] = df['Community'].apply(lambda name: f"https://www.reddit.com/{name}/top/?t=month")

    df = df.sort_values(by=['Relevance Score', 'Members'], ascending=[False, False])
    column_order = ['Community', 'Relevance Score', 'Found Via', 'Members', 'Community Link', 'Top Posts (Month)']
    return df[column_order].reset_index(drop=True)

# --- De 'find_buying_signals' functie blijft onveranderd ---
def find_buying_signals(_reddit, subreddit_name: str, keywords: list, time_filter: str, post_limit: int, comment_limit: int):
    # ... (Deze functie blijft exact hetzelfde) ...
    signals = []
    subreddit = _reddit.subreddit(subreddit_name)
    top_posts = subreddit.top(time_filter=time_filter, limit=post_limit)
    for post in top_posts:
        post_content = f"{post.title.lower()} {post.selftext.lower()}"
        matched_post_keywords = {keyword for keyword in keywords if keyword.lower() in post_content}
        if matched_post_keywords and post.author:
            signals.append({"Subreddit": subreddit_name, "Match": ', '.join(matched_post_keywords), "Type": "Post", "Text": post.title.replace('\n', ' ').strip(), "Author": post.author.name, "Link": f"https://reddit.com{post.permalink}"})
        if comment_limit > 0:
            post.comments.replace_more(limit=0)
            for comment in post.comments.list()[:comment_limit]:
                if hasattr(comment, 'body') and comment.author:
                    for keyword in keywords:
                        if keyword.lower() in comment.body.lower():
                            signals.append({"Subreddit": subreddit_name, "Match": keyword, "Type": "Comment", "Text": comment.body.replace('\n', ' ').strip()[:300] + '...', "Author": comment.author.name, "Link": f"https://reddit.com{comment.permalink}"}); break
    return signals

# --- UI Functies (Login) blijven onveranderd ---
def show_password_form():
    # ... (deze functie blijft hetzelfde) ...
    st.title("🚀 The Opportunity Finder")
    st.header("Step 1: App Access Login")
    with st.form(key='password_login_form'):
        password = st.text_input("Please enter the password", type="password", label_visibility="collapsed")
        if st.form_submit_button("Login", use_container_width=True):
            if password == APP_PASSWORD: st.session_state["password_correct"] = True; st.rerun()
            else: st.error("🚨 The password you entered is incorrect.")

def show_reddit_login_page():
    # ... (deze functie blijft hetzelfde) ...
    st.title("🚀 The Opportunity Finder")
    st.header("Step 2: Connect your Reddit Account")
    st.markdown("Access confirmed. Please log in with Reddit to allow the app to perform searches on your behalf.")
    reddit_auth_instance = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, user_agent="TheOpportunityFinder/Boyd (OAuth Setup)")
    auth_url = reddit_auth_instance.auth.url(scopes=["identity", "read", "history"], state="pro_login", duration="permanent")
    st.link_button("Login with Reddit", auth_url, type="primary", use_container_width=True)
    st.info("ℹ️ You will be redirected to Reddit to grant permission. This app never sees your password.")

# --- Hoofdapplicatie (Met de upgrade geïntegreerd) ---
def show_main_app(reddit):
    if 'signal_scan_running' not in st.session_state: st.session_state.signal_scan_running = False
    
    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        st.title("🚀 The Opportunity Finder")
        st.markdown(f"Logged in as **u/{st.session_state.username}**.")
    with col2:
        if st.button("Logout", use_container_width=True, disabled=st.session_state.signal_scan_running):
            st.session_state.clear(); st.rerun()

    # --- Deel 1: Communities Vinden (MET UI HARMONISATIE) ---
    st.header("1. Discover Relevant Communities")
    
    with st.expander("⚙️ Advanced Search Settings"):
        st.markdown("Control the trade-off between search speed and thoroughness.")
        c1, c2, c3 = st.columns(3)
        direct_limit = c1.slider("Direct Search Depth", 5, 50, 10, help="How many communities to find based on name/description. Quick but less precise.")
        post_limit = c2.slider("Post Search Depth", 10, 100, 25, help="How many posts to analyze. Finds communities where your topic is actively discussed.")
        comment_limit = c3.slider("Comment Search Depth", 0, 50, 20, help="How many comments *per post* to analyze. Deepest (and slowest) search for finding hidden user pain points.")

    with st.form(key='community_search_form'):
        search_queries_input = st.text_area("Enter search queries (one per line)", placeholder="e.g., SaaS for startups\nmachine learning projects", height=120, label_visibility="collapsed")
        community_form_submitted = st.form_submit_button("Find Communities", type="primary", use_container_width=True)

    if community_form_submitted:
        queries_tuple = tuple(sorted([q.strip() for q in search_queries_input.split('\n') if q.strip()]))
        if not queries_tuple:
            st.warning("Please enter at least one search query.")
        else:
            # NIEUW: De spinner die de bug oplost
            with st.spinner("Discovering communities... This may take a moment depending on your settings."):
                st.session_state['audience_df'] = find_communities_hybrid(reddit, queries_tuple, direct_limit, post_limit, comment_limit)
            
    st.subheader("Discovered Communities")
    if "audience_df" in st.session_state and st.session_state.audience_df is not None:
        if not st.session_state.audience_df.empty:
            st.dataframe(st.session_state["audience_df"], use_container_width=True, hide_index=True)
            csv_data = st.session_state["audience_df"].to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Communities as CSV", csv_data, 'community_discovery_results.csv', 'text/csv', use_container_width=True)
        else:
            st.success("✅ Search complete. No communities found for these terms.")
    else:
        st.info("Enter queries above and click 'Find Communities' to start your discovery.")

    st.divider()

    # --- Deel 2: Opportunity Finder (ONVERANDERD) ---
    st.header("2. Scan for Buying Signals")
    # ... (De rest van de app blijft volledig ongewijzigd) ...
    st.markdown("Deep-dive into specific communities to find posts and comments indicating a need or problem.")
    with st.form(key="signal_scanner_form", border=True):
        preset = st.radio("Scan Intensity", ["🟢 Fast", "🔵 Standard", "🔴 Deep", "⚙️ Custom"], index=1, horizontal=True, disabled=st.session_state.signal_scan_running)
        st.caption("(Custom settings are used only when '⚙️ Custom' is selected)")
        c1, c2 = st.columns(2)
        post_limit_custom = c1.number_input("Posts per subreddit", 1, 200, 50, 1, disabled=st.session_state.signal_scan_running)
        comment_limit_custom = c2.number_input("Max comments per post", 0, 1000, 100, 10, disabled=st.session_state.signal_scan_running)
        st.divider()
        time_filter = st.radio("Time frame for top posts", ["day", "week", "month", "year", "all"], index=2, horizontal=True, disabled=st.session_state.signal_scan_running)
        subreddits_input = st.text_area("Subreddits to scan (one per line)", placeholder="e.g. r/sidehustle\nr/solopreneur", height=150, disabled=st.session_state.signal_scan_running)
        keywords_input = st.text_area("Pain point keywords (one per line)", placeholder="e.g. market research\nfind clients", height=150, disabled=st.session_state.signal_scan_running)
        signal_form_submitted = st.form_submit_button("🔎 Run Buying Signal Scan", type="primary", use_container_width=True, disabled=st.session_state.signal_scan_running)
    if signal_form_submitted and not st.session_state.signal_scan_running:
        st.session_state.signal_scan_running = True
        if preset.startswith("🟢"): st.session_state.limits = (10, 20)
        elif preset.startswith("🔵"): st.session_state.limits = (50, 100)
        elif preset.startswith("🔴"): st.session_state.limits = (100, 500)
        else: st.session_state.limits = (post_limit_custom, comment_limit_custom)
        st.session_state.time_filter = time_filter
        st.session_state.subreddits = [s.strip() for s in subreddits_input.split('\n') if s.strip()]
        st.session_state.keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
        st.rerun()
    if st.session_state.signal_scan_running:
        st.info("Buying signal scan in progress...")
        all_signals, progress_bar = [], st.progress(0.0, text="Starting scan...")
        try:
            post_limit, comment_limit = st.session_state.limits
            custom_subreddits, custom_keywords = st.session_state.subreddits, st.session_state.keywords
            if not custom_subreddits or not custom_keywords: st.warning("❗ Please provide both subreddits and keywords.")
            else:
                for i, sub_name_raw in enumerate(custom_subreddits):
                    sub_name = sub_name_raw.replace('r/', '').strip()
                    progress_bar.progress(i / len(custom_subreddits), text=f"Scanning r/{sub_name}...")
                    try:
                        signals = find_buying_signals(reddit, sub_name, custom_keywords, st.session_state.time_filter, post_limit, comment_limit)
                        if signals: all_signals.extend(signals)
                    except (NotFound, Forbidden, BadRequest) as e: st.warning(f"Skipped r/{sub_name}: {e.__class__.__name__}")
                if all_signals: st.session_state["signals_df"] = pd.DataFrame(all_signals)
                else: st.session_state["signals_df"] = None
        finally:
            st.session_state.signal_scan_running = False; st.rerun()
    if "signals_df" in st.session_state and st.session_state.signals_df is not None:
        df_signals = st.session_state["signals_df"]
        st.success(f"✅ Found {len(df_signals)} buying signals.")
        st.dataframe(df_signals, use_container_width=True, hide_index=True)
        csv_signals = df_signals.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Signals as CSV", csv_signals, 'opportunity_finder_signals.csv', 'text/csv', use_container_width=True)

# --- Hoofdlogica (Login State Machine) ---
def main():
    # ... (deze functie blijft ook hetzelfde) ...
    st.set_page_config(page_title="The Opportunity Finder", layout="wide")
    auth_code = st.query_params.get("code")
    if "refresh_token" in st.session_state:
        try:
            reddit_instance = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, user_agent=f"TheOpportunityFinder/Boyd (user: {st.session_state.get('username', '...')})", refresh_token=st.session_state["refresh_token"])
            if not reddit_instance.user.me(): raise PRAWException("Token expired.")
            show_main_app(reddit_instance)
        except PRAWException as e: st.error(f"Reddit connection failed: {e}. Please log in again."); st.session_state.clear(); st.rerun()
    elif auth_code:
        try:
            temp_reddit = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, user_agent="TheOpportunityFinder/Boyd (Token Exchange)")
            refresh_token = temp_reddit.auth.authorize(auth_code)
            st.session_state["refresh_token"] = refresh_token
            user_reddit = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, user_agent="TheOpportunityFinder/Boyd (Get Username)", refresh_token=refresh_token)
            st.session_state["username"] = user_reddit.user.me().name
            st.session_state["password_correct"] = True
            st.query_params.clear(); st.rerun()
        except PRAWException as e: st.error(f"Reddit authentication failed: {e}. Please try again."); st.session_state.clear(); st.rerun()
    elif st.session_state.get("password_correct"):
        show_reddit_login_page()
    else:
        show_password_form()

if __name__ == "__main__":
    main()