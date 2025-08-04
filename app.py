import streamlit as st
import pandas as pd
import praw
from praw.exceptions import PRAWException
from prawcore.exceptions import NotFound, Forbidden, BadRequest

# --- Configuratie & Secrets ---
CLIENT_ID = st.secrets.get("reddit_client_id")
CLIENT_SECRET = st.secrets.get("reddit_client_secret")
APP_PASSWORD = st.secrets.get("app_password")
REDIRECT_URI = st.secrets.get("redirect_uri")

# --- Helper Functies ---
@st.cache_data(ttl=3600, show_spinner=False)
def find_communities_for_query(_reddit, query: str):
    """Zoekt naar subreddits voor EEN ENKELE zoekterm."""
    results = []
    for subreddit in _reddit.subreddits.search(query, limit=10):
        results.append({
            'Community': f"r/{subreddit.display_name}",
            'Members': subreddit.subscribers,
            'Community Link': f"https://www.reddit.com/r/{subreddit.display_name}",
            'Top Posts (Month)': f"https://www.reddit.com/r/{subreddit.display_name}/top/?t=month",
            'Found By': query
        })
    return results

def find_buying_signals(_reddit, subreddit_name: str, keywords: list, time_filter: str, post_limit: int, comment_limit: int):
    """Scant EEN ENKELE subreddit en geeft een lijst met gevonden signalen terug."""
    signals = []
    subreddit = _reddit.subreddit(subreddit_name)
    top_posts = subreddit.top(time_filter=time_filter, limit=post_limit)
    for post in top_posts:
        post_content = f"{post.title.lower()} {post.selftext.lower()}"
        matched_post_keywords = {keyword for keyword in keywords if keyword.lower() in post_content}
        if matched_post_keywords and post.author:
            signals.append({
                "Subreddit": subreddit_name, "Match": ', '.join(matched_post_keywords), "Type": "Post",
                "Text": post.title.replace('\n', ' ').strip(),
                "Author": post.author.name, "Link": f"https://reddit.com{post.permalink}"
            })
        if comment_limit > 0:
            post.comments.replace_more(limit=0)
            for comment in post.comments.list():
                if hasattr(comment, 'body') and comment.author:
                    for keyword in keywords:
                        if keyword.lower() in comment.body.lower():
                            signals.append({
                                "Subreddit": subreddit_name, "Match": keyword, "Type": "Comment",
                                "Text": comment.body.replace('\n', ' ').strip()[:300] + '...',
                                "Author": comment.author.name, "Link": f"https://reddit.com{comment.permalink}"
                            })
                            break
    return signals

# --- UI Functies voor Authenticatie ---
def show_password_form():
    st.title("🚀 The Opportunity Finder")
    st.header("Step 1: App Access Login")
    with st.form(key='password_login_form'):
        password = st.text_input("Please enter the password", type="password", label_visibility="collapsed")
        if st.form_submit_button("Login", use_container_width=True):
            if password == APP_PASSWORD:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("🚨 The password you entered is incorrect.")

def show_reddit_login_page():
    st.title("🚀 The Opportunity Finder")
    st.header("Step 2: Connect your Reddit Account")
    st.markdown("Access confirmed. Please log in with Reddit to allow the app to perform searches on your behalf.")
    reddit_auth_instance = praw.Reddit(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI, user_agent="TheOpportunityFinder/Boyd (OAuth Setup)"
    )
    auth_url = reddit_auth_instance.auth.url(scopes=["identity", "read", "history"], state="pro_login", duration="permanent")
    st.link_button("Login with Reddit", auth_url, type="primary", use_container_width=True)
    st.info("ℹ️ You will be redirected to Reddit to grant permission. This app never sees your password.")

# --- Hoofdapplicatie ---
def show_main_app(reddit):
    if 'community_scan_running' not in st.session_state: st.session_state.community_scan_running = False
    if 'signal_scan_running' not in st.session_state: st.session_state.signal_scan_running = False
    if 'cancel_scan' not in st.session_state: st.session_state.cancel_scan = False

    is_any_scan_running = st.session_state.community_scan_running or st.session_state.signal_scan_running

    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        st.title("🚀 The Opportunity Finder")
        st.markdown(f"Logged in as **u/{st.session_state.username}**.")
        st.markdown(f"Discover communities: **content ideas, business ideas and buying signals**.")
    with col2:
        if st.button("Logout", use_container_width=True, disabled=is_any_scan_running):
            st.session_state.clear()
            st.rerun()

    # --- Deel 1: Communities Vinden ---
    st.header("1. Find Relevant Communities")
    with st.form(key='community_search_form'):
        search_queries_input = st.text_area("Queries", label_visibility="collapsed", height=150, placeholder="For example:\nSaaS for startups...", disabled=is_any_scan_running)
        community_form_submitted = st.form_submit_button("Find Communities", type="primary", use_container_width=True, disabled=is_any_scan_running)

    if community_form_submitted and not st.session_state.community_scan_running:
        st.session_state.search_queries_list = [q.strip() for q in search_queries_input.split('\n') if q.strip()]
        if not st.session_state.search_queries_list:
            st.warning("Please enter at least one search query.")
        else:
            st.session_state.community_scan_running = True
            st.session_state.cancel_scan = False
            st.rerun()

    if st.session_state.community_scan_running:
        st.info("Community search in progress...")
        if st.button("Cancel Search"): st.session_state.cancel_scan = True
        all_results, progress_bar = [], st.progress(0.0, text="Starting search...")
        try:
            queries = st.session_state.search_queries_list
            for i, query in enumerate(queries):
                if st.session_state.cancel_scan:
                    st.warning("Search cancelled by user."); break
                progress_bar.progress((i + 1) / len(queries), text=f"Searching for: '{query}'...")
                all_results.extend(find_communities_for_query(reddit, query))
            if not st.session_state.cancel_scan:
                if all_results:
                    df = pd.DataFrame(all_results)
                    agg_df = df.groupby(['Community', 'Members', 'Community Link', 'Top Posts (Month)'])['Found By'].apply(lambda x: ', '.join(sorted(set(x)))).reset_index()
                    st.session_state["audience_df"] = agg_df.rename(columns={'Found By': 'Found By (Keywords)'}).sort_values(by='Members', ascending=False).reset_index(drop=True)
                else: st.session_state["audience_df"] = None
        finally:
            st.session_state.community_scan_running = False; st.session_state.cancel_scan = False; st.rerun()

    st.header("2. Discovered Communities")
    if "audience_df" in st.session_state and st.session_state.audience_df is not None:
        st.dataframe(st.session_state["audience_df"], use_container_width=True, hide_index=True)
    else: st.write("—")

    st.header("3. Download Community List")
    if "audience_df" in st.session_state and st.session_state.audience_df is not None:
        df_for_download = st.session_state['audience_df'].copy()
        df_for_download['Status'] = 'Not Started'; df_for_download['Priority'] = ''; df_for_download['Notes'] = ''
        csv_data = df_for_download.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Communities as CSV", csv_data, 'community_finder_results.csv', 'text/csv', use_container_width=True)
    else: st.write("—")

    st.divider()
    st.header("4. Opportunity Finder")

    # --- Deel 2: Koopsignalen Scan (met GECORRIGEERDE OPMAAK) ---
    with st.form(key="signal_scanner_form", border=True):
        preset = st.radio(
            "Scan Intensity", # CORRECT: Label is nu onderdeel van de radio widget
            ["🟢 Fast", "🔵 Standard", "🔴 Deep", "⚙️ Custom"],
            index=1,
            horizontal=True,
            disabled=is_any_scan_running
        )

        st.caption("(The values below are only used when '⚙️ Custom' is selected)") # CORRECT: Italics verwijderd

        c1, c2 = st.columns(2)
        post_limit_custom = c1.number_input("Posts per subreddit", min_value=1, max_value=200, value=50, step=1, disabled=is_any_scan_running)
        comment_limit_custom = c2.number_input("Max comments per post", min_value=0, max_value=1000, value=100, step=10, disabled=is_any_scan_running)
        
        st.divider()

        time_filter = st.radio("Time frame for top posts", ["day", "week", "month", "year", "all"], index=2, horizontal=True, disabled=is_any_scan_running)
        subreddits_input = st.text_area("Subreddits to scan (one per line)", placeholder="e.g. sidehustle\nsolopreneur", height=150, disabled=is_any_scan_running)
        keywords_input = st.text_area("Pain point keywords (one per line)", placeholder="e.g. market research\nfind clients", height=150, disabled=is_any_scan_running)
        signal_form_submitted = st.form_submit_button("🔎 Run Buying Signal Scan", type="primary", use_container_width=True, disabled=is_any_scan_running)

    if signal_form_submitted and not st.session_state.signal_scan_running:
        st.session_state.signal_scan_running = True; st.session_state.cancel_scan = False
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
        if st.button("Cancel Scan"): st.session_state.cancel_scan = True
        all_signals, progress_bar = [], st.progress(0.0, text="Starting scan...")
        try:
            post_limit, comment_limit = st.session_state.limits
            custom_subreddits, custom_keywords = st.session_state.subreddits, st.session_state.keywords
            time_filter = st.session_state.time_filter
            if not custom_subreddits or not custom_keywords:
                st.warning("❗ Please provide both subreddits and keywords.")
            else:
                for i, sub_name_raw in enumerate(custom_subreddits):
                    if st.session_state.cancel_scan: st.warning("Scan cancelled by user."); break
                    sub_name = sub_name_raw.replace('r/', '').strip()
                    progress_bar.progress(i / len(custom_subreddits), text=f"Scanning r/{sub_name} ({i}/{len(custom_subreddits)})...")
                    try:
                        signals = find_buying_signals(reddit, sub_name, custom_keywords, time_filter, post_limit, comment_limit)
                        if signals: all_signals.extend(signals)
                        progress_bar.progress((i + 1) / len(custom_subreddits), text=f"✅ Completed r/{sub_name} ({i+1}/{len(custom_subreddits)})")
                    except (NotFound, Forbidden, BadRequest) as e:
                        st.warning(f"Skipped r/{sub_name}: {e.__class__.__name__}"); progress_bar.progress((i + 1) / len(custom_subreddits), text=f"⚠️ Skipped r/{sub_name}")
                    except PRAWException as e:
                        st.warning(f"A Reddit API error occurred at r/{sub_name}: {e}"); progress_bar.progress((i + 1) / len(custom_subreddits), text=f"⚠️ Skipped r/{sub_name}")
                if not st.session_state.cancel_scan:
                    st.session_state["signals_df"] = pd.DataFrame(all_signals) if all_signals else None
        finally:
            st.session_state.signal_scan_running = False; st.session_state.cancel_scan = False; st.rerun()

    if "signals_df" in st.session_state and st.session_state.signals_df is not None:
        df_signals = st.session_state["signals_df"]
        st.success(f"✅ Found {len(df_signals)} buying signals.")
        st.dataframe(df_signals, use_container_width=True, hide_index=True)
        df_signals_download = df_signals.copy()
        df_signals_download['Text'] = df_signals_download['Text'].str.replace('\n', ' ', regex=False).str.strip()
        csv_signals = df_signals_download.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Signals as CSV", csv_signals, 'opportunity_finder_signals.csv', 'text/csv', use_container_width=True)

# --- Hoofdlogica (Login State Machine) ---
def main():
    st.set_page_config(page_title="The Opportunity Finder", layout="wide")
    auth_code = st.query_params.get("code")
    if "refresh_token" in st.session_state:
        try:
            reddit_instance = praw.Reddit(
                client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                user_agent=f"TheOpportunityFinder/Boyd (user: {st.session_state.get('username', '...')})",
                refresh_token=st.session_state["refresh_token"]
            )
            if not reddit_instance.user.me(): raise PRAWException("Token expired or revoked.")
            show_main_app(reddit_instance)
        except PRAWException as e:
            st.error(f"Reddit connection failed: {e}. Please log in again."); st.session_state.clear(); st.rerun()
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