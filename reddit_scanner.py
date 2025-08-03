import streamlit as st
import praw
import pandas as pd
from collections import defaultdict

# --- Haal de keys op uit Streamlit Secrets ---
CLIENT_ID = st.secrets["reddit_client_id"]
CLIENT_SECRET = st.secrets["reddit_client_secret"]
USER_AGENT = "AudienceFinder by Boyd v0.1"

def find_communities(search_queries: list):
    """
    Searches for relevant Reddit communities, aggregates duplicate finds,
    and lists all keywords that found the community.
    """
    try:
        reddit = praw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT,
        )
    except Exception as e:
        print(f"Error initializing Reddit client: {e}")
        raise e

    aggregated_results = {}

    for query in search_queries:
        query = query.strip()
        if not query:
            continue
        
        try:
            for subreddit in reddit.subreddits.search(query, limit=7):
                community_name = subreddit.display_name

                if community_name in aggregated_results:
                    aggregated_results[community_name]['Found By'].add(query)
                else:
                    aggregated_results[community_name] = {
                        'Community': community_name,
                        'Members': subreddit.subscribers,
                        'Community Link': f"https://www.reddit.com/r/{community_name}",
                        'Top Posts (Month)': f"https://www.reddit.com/r/{community_name}/top/?t=month",
                        'Found By': {query} 
                    }
        except Exception as e:
            print(f"Could not search with query '{query}'. Error: {e}")

    if not aggregated_results:
        return pd.DataFrame()

    final_list = list(aggregated_results.values())
    
    for item in final_list:
        item['Found By (Keywords)'] = ', '.join(sorted(list(item['Found By'])))
        del item['Found By']

    df = pd.DataFrame(final_list)

    if df.empty:
        return df

    df = df.sort_values(by='Members', ascending=False)
    
    column_order = [
        'Community', 
        'Members', 
        'Found By (Keywords)', 
        'Community Link', 
        'Top Posts (Month)'
    ]
    df = df[column_order].reset_index(drop=True)

    return df
    