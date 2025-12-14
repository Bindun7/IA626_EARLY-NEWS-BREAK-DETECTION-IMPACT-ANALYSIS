

#IA626_EARLY NEWS BREAK DETECTION AND IMPACT ANALYSIS
# Bindu Nagaraj

"""
EARLY NEWS BREAK DETECTION AND IMPACT ANALYSIS

Code overview:
1. Fetches news articles using NewsAPI
2. Computes sentiment using VADER
3. Fetches Google Trends search interest
4. Detects OFFICIAL break date (t0) from Google Trends peak
5. Treats Google Trends as EARLY SIGNAL before official news break
6. Compares:
   - Pre-break window (t-3 .. t-1)
   - Post-break window (t0 .. t+3)
7. Quantifies:
   - Search trend changes
   - Sentiment changes
8. Generates:
   - CSV reports
   - JSON report
   - Create and comparison plots
 
"""



import os
import time
import json
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pytrends.request import TrendReq

# configurations

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data_cpv2")
FIG_DIR = os.path.join(DATA_DIR, "figures")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

QUERY ="power plant leakage" #"Tariff on India"
GT_KEYWORD = QUERY
LANG = "en"



from dotenv import load_dotenv
load_dotenv()

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
print("Loaded API KEY:", NEWSAPI_KEY)

if not NEWSAPI_KEY:
    print("[Warning] NEWSAPI_KEY not found in environment. Using local key.")
    NEWSAPI_KEY = "NEWSAPI_KEY"


PAGE_SIZE = 100
MAX_PAGES = 2
DAYS_BACK = 30


# featch news articles

def fetch_news(from_date=None, to_date=None):
    articles = []

    for page in range(1, MAX_PAGES + 1):
        params = {
            "q": QUERY,
            "language": LANG,
            "pageSize": PAGE_SIZE,
            "page": page,
            "sortBy": "publishedAt",
            "apiKey": NEWSAPI_KEY,
        }

        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%d")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%d")

        print(f"[NewsAPI] Page {page}")
        r = requests.get("https://newsapi.org/v2/everything", params=params)

        if r.status_code != 200:
            print("[NewsAPI ERROR]", r.text)
            break

        batch = r.json().get("articles", [])
        if not batch:
            break

        articles.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        time.sleep(1)

    return normalize_articles(articles)


def normalize_articles(articles):
    df = pd.json_normalize(articles)
    df["publishedAt"] = pd.to_datetime(df["publishedAt"], errors="coerce")
    df["date"] = df["publishedAt"].dt.date
    df["description"] = df["description"].fillna(df["content"]).astype(str)

    return df[["source.name", "title", "description", "url", "date"]].rename(
        columns={"source.name": "source"}
    )

# sentiment analysis

def add_sentiment(df):
    analyzer = SentimentIntensityAnalyzer()
    df["sentiment"] = df.apply(
        lambda r: analyzer.polarity_scores(
            f"{r['title']} {r['description']}"
        )["compound"],
        axis=1
    )
    return df

def daily_sentiment(df):
    return df.groupby("date")["sentiment"].mean().reset_index()


# google trends fetch

def fetch_google_trends():
    end = datetime.utcnow().date()
    start = end - timedelta(days=DAYS_BACK)
    timeframe = f"{start} {end}"

    pytrends = TrendReq(hl="en-US", tz=0)
    pytrends.build_payload([GT_KEYWORD], timeframe=timeframe)

    df = pytrends.interest_over_time().reset_index()
    df = df.rename(columns={GT_KEYWORD: "search_volume"})
    df["date"] = df["date"].dt.date

    return df[["date", "search_volume"]]

# official break date detection

def detect_break_date(trends_df):
    idx = trends_df["search_volume"].idxmax()
    t0 = trends_df.loc[idx, "date"]
    print(f"[BREAK] Official break detected on {t0}")
    return t0

# PRE & POST Break details

def split_pre_post(merged, t0):
    pre = merged[merged["date"].between(t0 - timedelta(days=3), t0 - timedelta(days=1))]
    post = merged[merged["date"].between(t0, t0 + timedelta(days=3))]
    return pre, post


# builing day wise report


def build_daywise_break_report(merged, t0):
    """
    Generates report for:
    t-3, t-2, t-1, t0, t+1, t+2, t+3 , 
    with date,days_from_break,search_volume,sentiment
    """
    df = merged.copy()
    df["days_from_break"] = (pd.to_datetime(df["date"]) - pd.to_datetime(t0)).dt.days

    window = df[df["days_from_break"].between(-3, 3)].copy()

    window["relative_day"] = window["days_from_break"].apply(
        lambda x: f"t{x}" if x < 0 else ("t0" if x == 0 else f"t+{x}")
    )

    window = window.sort_values("days_from_break")

    cols = ["relative_day", "date", "search_volume", "sentiment"]
    return window[cols]


#Save Day-wise report

def save_daywise_reports(daywise_df):
    csv_path = os.path.join(DATA_DIR, "break_daywise_search_sentiment.csv")
    json_path = os.path.join(DATA_DIR, "break_daywise_search_sentiment.json")

   
    daywise_df.to_csv(csv_path, index=False)

    # Convert date column to string 
    json_ready_df = daywise_df.copy()
    json_ready_df["date"] = json_ready_df["date"].astype(str)

    with open(json_path, "w") as f:
        json.dump(json_ready_df.to_dict(orient="records"), f, indent=2)

    print(f"[Report] Saved day-wise CSV -> {csv_path}")
    print(f"[Report] Saved day-wise JSON -> {json_path}")



 # computing metrics

def compute_metrics(pre, post):
    metrics = {
        "pre_avg_search": float(pre["search_volume"].mean()),
        "post_avg_search": float(post["search_volume"].mean()),
        "pre_avg_sentiment": float(pre["sentiment"].mean()),
        "post_avg_sentiment": float(post["sentiment"].mean()),
    }

    metrics["search_change_pct"] = (
        ((metrics["post_avg_search"] - metrics["pre_avg_search"])
         / metrics["pre_avg_search"]) * 100
        if metrics["pre_avg_search"] > 0 else None
    )

    metrics["sentiment_change"] = (
        metrics["post_avg_sentiment"] - metrics["pre_avg_sentiment"]
    )

    return metrics


#lagged correlation analysis

def compute_lagged_sentiment_search(merged, max_lag=7):

    
    rows = []

    for lag in range(0, max_lag + 1):
        shifted_sentiment = merged["sentiment"].shift(lag)
        search = merged["search_volume"]

        valid = (~shifted_sentiment.isna()) & (~search.isna())
        if valid.sum() < 3:
            corr = None
        else:
            corr = shifted_sentiment[valid].corr(search[valid])

        rows.append({
            "lag_days": lag,
            "sentiment_leads_by_days": lag,
            "correlation": corr
        })

    return pd.DataFrame(rows)


# pre-break news fetch
def fetch_pre_break_news(t0):
    start = t0 - timedelta(days=3)
    end = t0 - timedelta(days=1)
    return fetch_news(start, end)

# creating pre and post break reports

def save_pre_post_reports(pre, post):
    pre.to_csv(os.path.join(DATA_DIR, "pre_break_window.csv"), index=False)
    post.to_csv(os.path.join(DATA_DIR, "post_break_window.csv"), index=False)

# visualizations

def generate_plots(merged, pre, post, t0):
    # Timeline search
    plt.figure(figsize=(10,5))
    plt.plot( merged["date"],merged["search_volume"],label="Google Search Volume",color="blue",linewidth=2)
    plt.axvline(t0, color="red", linestyle="--", label="Official Break")
    plt.title("Google Search Trend Around Official Break")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "search_timeline.png"))
    plt.close()

    # Timeline sentiment
    plt.figure(figsize=(10,5))
    plt.plot(merged["date"], merged["sentiment"],label="Daily News Sentiment",
    color="blue",
    linewidth=2,
    marker="o")
    plt.axvline(t0, color="red", linestyle="--", label="Official Break")
    plt.title("News Sentiment Around Official Break")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "sentiment_timeline.png"))
    plt.close()

    # Pre vs Post search
    plt.figure(figsize=(6,4))
    plt.bar(["Pre-break", "Post-break"],
            [pre["search_volume"].mean(), post["search_volume"].mean()])
    plt.title("Average Search Volume: Pre vs Post")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "pre_post_search.png"))
    plt.close()

    # Pre vs Post sentiment
    plt.figure(figsize=(6,4))
    plt.bar(["Pre-break", "Post-break"],
            [pre["sentiment"].mean(), post["sentiment"].mean()])
    plt.title("Average Sentiment: Pre vs Post")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "pre_post_sentiment.png"))
    plt.close()

    # Search vs sentiment scatter
    plt.figure(figsize=(7,5))
    plt.scatter(pre["search_volume"], pre["sentiment"], label="Pre-break")
    plt.scatter(post["search_volume"], post["sentiment"], label="Post-break")
    plt.xlabel("Search Volume")
    plt.ylabel("Sentiment")
    plt.legend()
    plt.title("Search vs Sentiment (Pre vs Post)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "search_vs_sentiment.png"))
    plt.close()


#adding lagged correlation plot

def plot_lagged_correlation(lag_df):
    plt.figure(figsize=(7,4))
    plt.plot(lag_df["lag_days"], lag_df["correlation"], marker="o")
    plt.axhline(0, linestyle="--")
    plt.xlabel("Sentiment Leads Search By (Days)")
    plt.ylabel("Correlation")
    plt.title("Lagged Sentiment → Search Correlation")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "lagged_sentiment_search.png"))
    plt.close()

#save lagged report

def save_lagged_report(lag_df):
    lag_df.to_csv(os.path.join(DATA_DIR, "lagged_sentiment_search.csv"), index=False)

    summary = {
        "best_lag": lag_df.sort_values("correlation", ascending=False)
                         .iloc[0].to_dict()
    }

    with open(os.path.join(DATA_DIR, "lagged_sentiment_search_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

# finaljson report

def save_final_report(metrics, t0, pre_news_count):
    report = {
        "official_break_date": str(t0),
        "analysis_window": "t-3 to t+3",
        "pre_break_article_count": pre_news_count,
        "metrics": metrics,
        "interpretation": {
            "early_signal_present": metrics["pre_avg_search"] > 0,
            "interest_increased_after_break":
                metrics["post_avg_search"] > metrics["pre_avg_search"],
            "sentiment_shift": metrics["sentiment_change"]
        }
    }

    with open(os.path.join(DATA_DIR, "final_break_report.json"), "w") as f:
        json.dump(report, f, indent=2)

# main pipeline

def main():
    print(" PIPELINE STARTED")

    news = fetch_news()
    news = add_sentiment(news)
    news.to_csv(os.path.join(DATA_DIR, "news_articles.csv"), index=False)

    daily_sent = daily_sentiment(news)
    daily_sent.to_csv(os.path.join(DATA_DIR, "news_sentiment_daily.csv"), index=False)

    trends = fetch_google_trends()
    trends.to_csv(os.path.join(DATA_DIR, "google_trends_daily.csv"), index=False)

    merged = pd.merge(trends, daily_sent, on="date", how="left").fillna(0)
    merged.to_csv(os.path.join(DATA_DIR, "merged_daily.csv"), index=False)


    #  Lagged sentiment  search analysis 
    lag_df = compute_lagged_sentiment_search(merged, max_lag=7)
    save_lagged_report(lag_df)
    plot_lagged_correlation(lag_df)

    t0 = detect_break_date(merged)

    # Day-wise pre and post break report (t-3 to  t+3) 

    daywise_df = build_daywise_break_report(merged, t0)
    save_daywise_reports(daywise_df)


    pre, post = split_pre_post(merged, t0)
    metrics = compute_metrics(pre, post)

    pre_news = fetch_pre_break_news(t0)
    pre_news.to_csv(os.path.join(DATA_DIR, "pre_break_news.csv"), index=False)

    save_pre_post_reports(pre, post)
    generate_plots(merged, pre, post, t0)
    save_final_report(metrics, t0, len(pre_news))

    print(" PIPELINE COMPLETED ")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
