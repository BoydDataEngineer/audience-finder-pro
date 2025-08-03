import praw
import streamlit as st

CLIENT_ID = st.secrets["reddit_client_id"]
CLIENT_SECRET = st.secrets["reddit_client_secret"]
USER_AGENT = "SignalFinder by The Audience Finder v0.1"

def initialize_reddit_client():
    """Initialiseert en valideert de PRAW Reddit client."""
    if CLIENT_ID == "VUL_HIER_UW_CLIENT_ID_IN" or CLIENT_SECRET == "VUL_HIER_UW_CLIENT_SECRET_IN":
        print("FOUT: Vul uw Reddit API credentials in bij de CONFIGURATIE sectie.")
        return None
    
    try:
        reddit = praw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT,
        )
        # Test of de credentials geldig zijn
        print(f"Succesvol ingelogd als read-only client: {reddit.user.me() is None}")
        return reddit
    except Exception as e:
        print(f"Fout bij het initialiseren van de Reddit client: {e}")
        return None

def find_buying_signals(reddit, subreddits, keywords, time_filter="month", post_limit=50, comment_limit=100):

    """Scant subreddits op posts en comments die de opgegeven keywords bevatten."""
    found_signals = []
    
    print(f"\nStarten met scannen van {len(subreddits)} subreddits...")
    
    for i, subreddit_name in enumerate(subreddits):
        print(f"[{i+1}/{len(subreddits)}] Scannen van r/{subreddit_name}...")
        try:
            subreddit = reddit.subreddit(subreddit_name)
            top_posts = subreddit.top(time_filter=time_filter, limit=post_limit)

            for post in top_posts:
                # Scan de titel van de post
                for keyword in keywords:
                    if keyword.lower() in post.title.lower() and post.author:
                        signal = {
                            'Subreddit': subreddit_name,
                            'Type': 'Post Title',
                            'Author': post.author.name,
                            'Text': post.title,
                            'Link': f"https://www.reddit.com{post.permalink}",
                            'Matched Keyword': keyword
                        }
                        found_signals.append(signal)
                        break  # Ga naar volgende post na eerste match in titel

                # Scan de comments van de post
                post.comments.replace_more(limit=0)
                comment_count = 0
                for comment in post.comments.list():
                    if comment_count >= comment_limit:
                        break
                    
                    if hasattr(comment, 'body') and comment.author:
                        for keyword in keywords:
                            if keyword.lower() in comment.body.lower():
                                signal = {
                                    'Subreddit': subreddit_name,
                                    'Type': 'Comment',
                                    'Author': comment.author.name,
                                    'Text': comment.body.replace('\n', ' ').strip(), # Maak comment compacter
                                    'Link': f"https://www.reddit.com{comment.permalink}",
                                    'Matched Keyword': keyword
                                }
                                found_signals.append(signal)
                                break # Ga naar volgende comment na eerste match
                    comment_count += 1
        except Exception as e:
            print(f"  -> Kon r/{subreddit_name} niet volledig scannen. Fout: {e}")

    return found_signals