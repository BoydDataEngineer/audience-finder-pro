# app.py - Opportunity Finder v2.8 met Engelse UI en Toast-notificaties

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

# --- Constanten voor Relevance Score ---
FOUND_VIA_DIRECT = 'Direct Search'
FOUND_VIA_POST = 'Relevant Post'
FOUND_VIA_COMMENT = 'Relevant Comment'

def calculate_relevance_score(found_via_set: set):
    score = 0
    if FOUND_VIA_DIRECT in found_via_set: score += 1
    if FOUND_VIA_POST in found_via_set: score += 2
    if FOUND_VIA_COMMENT in found_via_set: score += 3
    return score

# --- Zoekfuncties (beide met Cancel-logica) ---

def find_communities_hybrid(_reddit, search_queries: tuple, direct_limit: int, post_limit: int, comment_limit: int):
    aggregated_results = {}
    progress_bar = st.session_state.get('progress_bar_placeholder')
    for i, query in enumerate(search_queries):
        if st.session_state.get('community_cancel_scan'): break
        if progress_bar:
            progress_bar.progress(i / len(search_queries), text=f"Searching for: '{query}'...")
        try:
            for sub in _reddit.subreddits.search(query, limit=direct_limit):
                if st.session_state.get('community_cancel_scan'): break
                if sub.display_name.startswith('u_'): continue
                if sub.display_name not in aggregated_results: aggregated_results[sub.display_name] = {'Community': sub.display_name, 'Members': sub.subscribers, 'Found Via': set()}
                aggregated_results[sub.display_name]['Found Via'].add(FOUND_VIA_DIRECT)
        except PRAWException: pass
        if st.session_state.get('community_cancel_scan'): break
        try:
            for post in _reddit.subreddit("all").search(query, sort="relevance", time_filter="month", limit=post_limit):
                if st.session_state.get('community_cancel_scan'): break
                if post.subreddit.display_name.startswith('u_') or post.subreddit.over18: continue
                community_name = post.subreddit.display_name
                if community_name not in aggregated_results: aggregated_results[community_name] = {'Community': community_name, 'Members': post.subreddit.subscribers, 'Found Via': set()}
                aggregated_results[community_name]['Found Via'].add(FOUND_VIA_POST)
                if comment_limit > 0:
                    try:
                        post.comments.replace_more(limit=0)
                        for comment in post.comments.list()[:comment_limit]:
                            if st.session_state.get('community_cancel_scan'): break
                            if hasattr(comment, 'body') and query.lower() in comment.body.lower():
                                aggregated_results[community_name]['Found Via'].add(FOUND_VIA_COMMENT); break
                    except Exception: continue
        except PRAWException: pass
    if progress_bar: progress_bar.progress(1.0, text="Finalizing results...")
    if not aggregated_results: return pd.DataFrame()
    final_list = [{'Community': f"r/{name}", **data} for name, data in aggregated_results.items()]
    df = pd.DataFrame(final_list)
    if df.empty: return df
    df['Relevance Score'] = df['Found Via'].apply(calculate_relevance_score)
    df['Found Via'] = df['Found Via'].apply(lambda s: ', '.join(sorted(list(s))))
    df['Community Link'] = df['Community'].apply(lambda name: f"https://www.reddit.com/{name}")
    df['Top Posts (Month)'] = df['Community'].apply(lambda name: f"https://www.reddit.com/{name}/top/?t=month")
    df = df.sort_values(by=['Relevance Score', 'Members'], ascending=[False, False])
    return df[['Community', 'Relevance Score', 'Found Via', 'Members', 'Community Link', 'Top Posts (Month)']].reset_index(drop=True)

def find_buying_signals(_reddit, subreddit_name: str, keywords: list, time_filter: str, post_limit: int, comment_limit: int):
    """Vindt buying signals en ondersteunt een cancel-operatie."""
    signals = []
    subreddit = _reddit.subreddit(subreddit_name)
    top_posts = subreddit.top(time_filter=time_filter, limit=post_limit)
    for post in top_posts:
        if st.session_state.get('signal_cancel_scan'): break
        post_content = f"{post.title.lower()} {post.selftext.lower()}"
        matched_post_keywords = {keyword for keyword in keywords if keyword.lower() in post_content}
        if matched_post_keywords and post.author:
            signals.append({"Subreddit": subreddit_name, "Match": ', '.join(matched_post_keywords), "Type": "Post", "Text": post.title.replace('\n', ' ').strip(), "Author": post.author.name, "Link": f"https://reddit.com{post.permalink}"})
        if comment_limit > 0:
            post.comments.replace_more(limit=0)
            for comment in post.comments.list()[:comment_limit]:
                if st.session_state.get('signal_cancel_scan'): break
                if hasattr(comment, 'body') and comment.author:
                    for keyword in keywords:
                        if keyword.lower() in comment.body.lower():
                            signals.append({"Subreddit": subreddit_name, "Match": keyword, "Type": "Comment", "Text": comment.body.replace('\n', ' ').strip()[:300] + '...', "Author": comment.author.name, "Link": f"https://reddit.com{comment.permalink}"}); break
    return signals

# --- UI Functies (Login) ---
def show_password_form():
    st.title("🚀 The Opportunity Finder")
    st.header("Step 1: App Access Login")
    with st.form(key='password_login_form'):
        password = st.text_input("Please enter the password", type="password", label_visibility="collapsed")
        if st.form_submit_button("Login", use_container_width=True):
            if password == APP_PASSWORD: st.session_state["password_correct"] = True; st.rerun()
            else: st.error("🚨 The password you entered is incorrect.")

def show_reddit_login_page():
    st.title("🚀 The Opportunity Finder")
    st.header("Step 2: Connect your Reddit Account")
    st.markdown("Access confirmed. Please log in with Reddit to allow the app to perform searches on your behalf.")
    reddit_auth_instance = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, user_agent="TheOpportunityFinder/Boyd (OAuth Setup)")
    auth_url = reddit_auth_instance.auth.url(scopes=["identity", "read", "history"], state="pro_login", duration="permanent")
    st.link_button("Login with Reddit", auth_url, type="primary", use_container_width=True)
    st.info("ℹ️ You will be redirected to Reddit to grant permission. This app never sees your password.")

# --- Hoofdapplicatie ---
def show_main_app(reddit):
    # State variabelen voor beide taken
    if 'community_scan_running' not in st.session_state: st.session_state.community_scan_running = False
    if 'community_cancel_scan' not in st.session_state: st.session_state.community_cancel_scan = False
    if 'community_scan_was_cancelled' not in st.session_state: st.session_state.community_scan_was_cancelled = False
    if 'signal_scan_running' not in st.session_state: st.session_state.signal_scan_running = False
    if 'signal_cancel_scan' not in st.session_state: st.session_state.signal_cancel_scan = False
    if 'signal_scan_was_cancelled' not in st.session_state: st.session_state.signal_scan_was_cancelled = False
    
    is_any_scan_running = st.session_state.community_scan_running or st.session_state.signal_scan_running

    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        st.title("🚀 The Opportunity Finder")
        st.markdown(f"Logged in as **u/{st.session_state.username}**.")
    with col2:
        if st.button("Logout", use_container_width=True, disabled=is_any_scan_running):
            st.session_state.clear(); st.rerun()

    # --- Deel 1: Communities Vinden ---
    st.header("1. Discover Communities")
    is_community_scan_running = st.session_state.community_scan_running
    with st.expander("⚙️ Advanced Search Settings"):
        st.markdown("Control the trade-off between search speed and thoroughness.")
        c1, c2, c3 = st.columns(3)
        direct_limit = c1.slider("Direct Search Depth", 5, 50, 10, disabled=is_community_scan_running)
        post_limit = c2.slider("Post Search Depth", 10, 100, 25, disabled=is_community_scan_running)
        comment_limit = c3.slider("Comment Search Depth", 0, 50, 20, disabled=is_community_scan_running)

    with st.form(key='community_search_form'):
        search_queries_input = st.text_area("Keywords (one per line)", placeholder="For example:\nSaaS for startups...", height=120, label_visibility="collapsed", disabled=is_community_scan_running)
        community_form_submitted = st.form_submit_button("Find Communities", type="primary", use_container_width=True, disabled=is_community_scan_running)
        if community_form_submitted:
            queries_tuple = tuple(sorted([q.strip() for q in search_queries_input.split('\n') if q.strip()]))
            if not queries_tuple:
                st.warning("Please enter at least one search query.")
            else:
                st.session_state.community_scan_running = True
                st.session_state.community_cancel_scan = False
                st.session_state.community_scan_was_cancelled = False
                st.session_state.search_params = {"queries": queries_tuple, "direct": direct_limit, "post": post_limit, "comment": comment_limit}
                st.rerun()

    if is_community_scan_running:
        st.info("Community search in progress...")
        if st.button("Cancel Search", use_container_width=True):
            st.session_state.community_cancel_scan = True
            st.session_state.community_scan_was_cancelled = True
        st.session_state['progress_bar_placeholder'] = st.progress(0.0)
        try:
            p = st.session_state.search_params
            st.session_state['audience_df'] = find_communities_hybrid(reddit, p['queries'], p['direct'], p['post'], p['comment'])
        finally:
            st.session_state.community_scan_running = False
            st.session_state.community_cancel_scan = False
            if 'search_params' in st.session_state: del st.session_state.search_params
            if 'progress_bar_placeholder' in st.session_state: del st.session_state['progress_bar_placeholder']
            st.rerun()

    if st.session_state.get("community_scan_was_cancelled"):
        st.warning("️️Community search was cancelled by the user.")
        st.session_state.community_scan_was_cancelled = False
        if 'audience_df' in st.session_state: del st.session_state['audience_df']
    elif "audience_df" in st.session_state:
        st.header("Search Results")
        results_df = st.session_state['audience_df']
        if results_df is not None and not results_df.empty:
            st.dataframe(results_df, use_container_width=True, hide_index=True)
            csv_data = results_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Communities as CSV", csv_data, 'community_discovery_results.csv', 'text/csv', use_container_width=True)
        else:
            st.success("✅ Search complete. No communities found for these terms.")

    st.divider()

    # --- Deel 2: Scan for Opportunities (UI Aangepast) ---
    st.header("2. Scan for Opportunities")
    is_signal_scan_running = st.session_state.signal_scan_running
    st.markdown("Deep-dive into specific communities to find posts and comments indicating a need or problem.")
    with st.form(key="signal_scanner_form", border=True):
        preset = st.radio("Scan Intensity", ["🟢 Fast", "🔵 Standard", "🔴 Deep", "⚙️ Custom"], index=1, horizontal=True, disabled=is_signal_scan_running)
        c1, c2 = st.columns(2)
        post_limit_custom = c1.number_input("Posts per subreddit", 1, 200, 50, 1, disabled=is_signal_scan_running)
        comment_limit_custom = c2.number_input("Max comments per post", 0, 1000, 100, 10, disabled=is_signal_scan_running)
        time_filter = st.radio("Time frame for top posts", ["day", "week", "month", "year", "all"], index=2, horizontal=True, disabled=is_signal_scan_running)
        subreddits_input = st.text_area("Subreddits to scan (one per line)", placeholder="e.g. sidehustle\nsolopreneur", height=120, disabled=is_signal_scan_running)
        keywords_input = st.text_area("Pain point keywords (one per line)", placeholder="e.g. market research\nfind clients", height=120, disabled=is_signal_scan_running)
        signal_form_submitted = st.form_submit_button("🔎 Run Opportunity finder", type="primary", use_container_width=True, disabled=is_signal_scan_running)
    
    if signal_form_submitted and not is_signal_scan_running:
        if 'signals_df' in st.session_state:
            del st.session_state['signals_df']

        subreddits_list = [s.strip() for s in subreddits_input.split('\n') if s.strip()]
        keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]
        
        if not subreddits_list or not keywords_list:
            st.error("❗ Please provide both subreddits and keywords to start a scan.")
        else:
            st.session_state.signal_scan_running = True
            st.session_state.signal_cancel_scan = False
            st.session_state.signal_scan_was_cancelled = False
            if preset.startswith("🟢"): st.session_state.limits = (10, 20)
            elif preset.startswith("🔵"): st.session_state.limits = (50, 100)
            elif preset.startswith("🔴"): st.session_state.limits = (100, 500)
            else: st.session_state.limits = (post_limit_custom, comment_limit_custom)
            st.session_state.time_filter = time_filter
            st.session_state.subreddits = subreddits_list
            st.session_state.keywords = keywords_list
            st.rerun()

    if is_signal_scan_running:
        st.info("🔎 Opportunity scan in progress...")
        if st.button("Cancel Opportunity Scan", use_container_width=True):
            st.session_state.signal_cancel_scan = True
            st.session_state.signal_scan_was_cancelled = True
        
        all_signals, progress_bar = [], st.progress(0.0, text="Starting scan...")
        try:
            post_limit, comment_limit = st.session_state.limits
            custom_subreddits, custom_keywords = st.session_state.subreddits, st.session_state.keywords
            
            for i, sub_name_raw in enumerate(custom_subreddits):
                if st.session_state.signal_cancel_scan: break
                sub_name = sub_name_raw.replace('r/', '').strip()
                progress_bar.progress(i / len(custom_subreddits), text=f"Scanning r/{sub_name}...")
                try:
                    signals = find_buying_signals(reddit, sub_name, custom_keywords, st.session_state.time_filter, post_limit, comment_limit)
                    if signals: all_signals.extend(signals)
                except (NotFound, Forbidden, BadRequest) as e: st.warning(f"Skipped r/{sub_name}: {e.__class__.__name__}")
            
            st.session_state["signals_df"] = pd.DataFrame(all_signals) if all_signals else pd.DataFrame()
        finally:
            st.session_state.signal_scan_running = False
            st.session_state.signal_cancel_scan = False
            st.rerun()

    if st.session_state.get("signal_scan_was_cancelled"):
        st.warning("️️Opportunity scan was cancelled by the user.")
        st.session_state.signal_scan_was_cancelled = False
        if "signals_df" in st.session_state: del st.session_state["signals_df"]
    elif "signals_df" in st.session_state:
        df_signals = st.session_state["signals_df"]
        if not df_signals.empty:
            st.success(f"✅ Success! Found {len(df_signals)} opportunities.")
            st.dataframe(df_signals, use_container_width=True, hide_index=True)
            csv_signals = df_signals.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Opportunities as CSV", csv_signals, 'opportunity_finder_opportunities.csv', 'text/csv', use_container_width=True)
        else:
            st.toast("✅ Scan complete. No opportunities were found for these terms.")
            del st.session_state['signals_df'] # Verwijder state zodat toast niet opnieuw verschijnt

# --- Hoofdlogica (Login State Machine) ---
def main():
    st.set_page_config(page_title="The Opportunity Finder", layout="wide")
    auth_code = st.query_params.get("code")
    if "refresh_token" in st.session_state:
        try:
            reddit_instance = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, user_agent=f"TheOpportunityFinder/Boyd (user: {st.session_state.get('username', '...')})", refresh_token=st.session_state["refresh_token"])
            show_main_app(reddit_instance)
        except PRAWException:
            st.error("Reddit connection failed. Please log in again."); st.session_state.clear(); st.rerun()
    elif auth_code:
        try:
            temp_reddit = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, user_agent="TheOpportunityFinder/Boyd (Token Exchange)")
            refresh_token = temp_reddit.auth.authorize(auth_code)
            st.session_state["refresh_token"] = refresh_token
            user_reddit = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, user_agent="TheOpportunityFinder/Boyd (Get Username)", refresh_token=refresh_token)
            st.session_state["username"] = user_reddit.user.me().name
            st.session_state["password_correct"] = True
            st.query_params.clear(); st.rerun()
        except PRAWException as e:
            st.error(f"Reddit authentication failed: {e}. Please try again."); st.session_state.clear(); st.rerun()
    elif st.session_state.get("password_correct"):
        show_reddit_login_page()
    else:
        show_password_form()

if __name__ == "__main__":
    main()