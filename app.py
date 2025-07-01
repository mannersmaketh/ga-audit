import streamlit as st
from authlib.integrations.requests_client import OAuth2Session
import requests

# ---------------------------
# Setup your OAuth details
# ---------------------------
client_id = st.secrets["client_id"]
client_secret = st.secrets["client_secret"]
import os

if "STREAMLIT_SERVER_PORT" in os.environ:
    # Running locally
    redirect_uri = "http://localhost:8501"
else:
    # Running on Streamlit Cloud
    redirect_uri = "https://ga-audit.streamlit.app"


authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
token_url = "https://oauth2.googleapis.com/token"
scope = "https://www.googleapis.com/auth/analytics.readonly"

st.set_page_config(page_title="GA4 OAuth Demo", layout="centered")
st.title("🔐 GA4 OAuth Test Tool")

# ---------------------------
# Step 1: Start OAuth flow
# ---------------------------
if "access_token" not in st.session_state:

    if "code" not in st.query_params:
        oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
        auth_url, state = oauth.create_authorization_url(authorize_url)
        st.session_state["oauth_state"] = state
        st.markdown("### Step 1: Connect Your Google Analytics")
        st.markdown(f"[Click here to log in and authorize access]({auth_url})")

    else:
        # Exchange authorization code for token
        code = st.query_params["code"]
        oauth = OAuth2Session(client_id, client_secret, redirect_uri=redirect_uri)
        token = oauth.fetch_token(token_url, code=code)
        st.session_state["access_token"] = token["access_token"]
        st.success("✅ Authorization successful!")

# ---------------------------
# Step 2: Show GA4 Properties
# ---------------------------
if "access_token" in st.session_state:
    st.markdown("### Step 2: Your GA4 Accounts")

    headers = {
        "Authorization": f"Bearer {st.session_state['access_token']}"
    }

    resp = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", headers=headers)

    if resp.status_code == 200:
        data = resp.json()
        summaries = data.get("accountSummaries", [])
        if summaries:
            for summary in summaries:
                account = summary["displayName"]
                property_id = summary["propertySummaries"][0]["property"]
                st.write(f"**{account}** — GA4 Property ID: `{property_id}`")
        else:
            st.info("No GA4 accounts found for this user.")
    else:
        st.error("Failed to retrieve GA4 accounts.")
        st.text(resp.text)
