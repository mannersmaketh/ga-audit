import streamlit as st
from authlib.integrations.requests_client import OAuth2Session
import requests
import pandas as pd
import os

# -------------------- CONFIG --------------------
client_id = st.secrets["client_id"]
client_secret = st.secrets["client_secret"]
redirect_uri = "https://ga-audit.streamlit.app"  # Update if your URL is different

authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
token_url = "https://oauth2.googleapis.com/token"
scope = "https://www.googleapis.com/auth/analytics.readonly"

# -------------------- PAGE SETUP --------------------
st.set_page_config(page_title="GA4 Audit Tool", layout="centered")
st.title("📊 GA4 OAuth Audit Tool")

# -------------------- OAUTH FLOW --------------------
if "access_token" not in st.session_state:

    if "code" not in st.query_params:
        oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
        auth_url, state = oauth.create_authorization_url(authorize_url)
        st.session_state["oauth_state"] = state
        st.markdown("### Step 1: Connect Your Google Analytics Account")
        st.markdown(f"[Click here to authorize]({auth_url})")

    else:
        code = st.query_params["code"]
        oauth = OAuth2Session(client_id, client_secret, redirect_uri=redirect_uri)
        token = oauth.fetch_token(token_url, code=code)
        st.session_state["access_token"] = token["access_token"]
        st.success("✅ Authorization successful!")

# -------------------- PROPERTY PICKER --------------------
if "access_token" in st.session_state:
    headers = {"Authorization": f"Bearer {st.session_state['access_token']}"}
    resp = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", headers=headers)

    if resp.status_code == 200:
        summaries = resp.json().get("accountSummaries", [])
        options = []

        for summary in summaries:
            account = summary.get("displayName", "Unnamed Account")
            for prop in summary.get("propertySummaries", []):
                options.append({
                    "label": f"{account} — {prop.get('displayName')} ({prop.get('property')})",
                    "id": prop.get("property")
                })

        if not options:
            st.warning("No GA4 properties found for this account.")
        else:
            property_labels = [opt["label"] for opt in options]
            property_ids = {opt["label"]: opt["id"] for opt in options}
            
            selected_label = st.selectbox("### Step 2: Choose a GA4 Property", property_labels)
            
            if selected_label:
                property_id = property_ids[selected_label]

                # -------------------- GA4 DATA QUERY --------------------
                st.markdown("### Step 3: Querying 90 Days of Metrics…")

                run_report_url = f"https://analyticsdata.googleapis.com/v1beta/{property_id}:runReport"
                body = {
                    "dateRanges": [{"startDate": "90daysAgo", "endDate": "today"}],
                    "metrics": [
                        {"name": "sessions"},
                        {"name": "totalUsers"},
                        {"name": "purchaseRevenue"}
                    ]
                }

                ga_response = requests.post(run_report_url, headers=headers, json=body)

                if ga_response.status_code == 200:
                    report = ga_response.json()
                    metrics = report.get("metricHeaders", [])
                    rows = report.get("rows", [])

                    if not rows:
                        st.info("No data available for the selected property.")
                    else:
                        data = []
                        for row in rows:
                            values = row["metricValues"]
                            data.append({metrics[i]["name"]: values[i]["value"] for i in range(len(values))})

                        df = pd.DataFrame(data)
                        st.dataframe(df)

                        csv = df.to_csv(index=False).encode("utf-8")
                        st.download_button("⬇️ Download CSV", csv, "ga4_metrics.csv", "text/csv")
                else:
                    st.error("Failed to query GA4 Data API.")
                    st.text(ga_response.text)
    else:
        st.error("Failed to retrieve GA4 accounts.")
        st.text(resp.text)
