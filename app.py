import streamlit as st
from authlib.integrations.requests_client import OAuth2Session
import requests
import pandas as pd

# --------------- CONFIG ---------------
client_id = st.secrets["client_id"]
client_secret = st.secrets["client_secret"]
redirect_uri = "https://ga-audit.streamlit.app"
authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
token_url = "https://oauth2.googleapis.com/token"
scope = "https://www.googleapis.com/auth/analytics.readonly"

st.set_page_config(page_title="GA4 Audit", layout="centered")
st.title("📊 GA4 Executive Audit Report")

# --------------- OAUTH FLOW ---------------
if "access_token" not in st.session_state:
    if "code" not in st.query_params:
        oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
        auth_url, state = oauth.create_authorization_url(authorize_url)
        st.session_state["oauth_state"] = state
        st.markdown(f"[Click here to connect Google Analytics]({auth_url})")
        st.stop()
    else:
        code = st.query_params["code"]
        oauth = OAuth2Session(client_id, client_secret, redirect_uri=redirect_uri)
        token = oauth.fetch_token(token_url, code=code)
        st.session_state["access_token"] = token["access_token"]

# --------------- RETRIEVE PROPERTIES ---------------
headers = {"Authorization": f"Bearer {st.session_state['access_token']}"}
resp = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", headers=headers)
summaries = resp.json().get("accountSummaries", [])

options = []
for summary in summaries:
    account = summary.get("displayName", "Unnamed Account")
    for prop in summary.get("propertySummaries", []):
        options.append({
            "label": f"{account} — {prop.get('displayName')} ({prop.get('property')})",
            "id": prop.get("property")
        })

property_labels = [opt["label"] for opt in options]
property_ids = {opt["label"]: opt["id"] for opt in options}
selected_label = st.selectbox("Choose a GA4 Property", property_labels)

# --------------- REPORT GENERATION ---------------
if selected_label:
    property_id = property_ids[selected_label]
    run_report_url = f"https://analyticsdata.googleapis.com/v1beta/{property_id}:runReport"

    def fetch_metric_report(metrics, dimensions=None, filters=None):
        body = {
            "dateRanges": [{"startDate": "90daysAgo", "endDate": "today"}],
            "metrics": [{"name": m} for m in metrics]
        }
        if dimensions:
            body["dimensions"] = [{"name": d} for d in dimensions]
        if filters:
            body["dimensionFilter"] = filters
        response = requests.post(run_report_url, headers=headers, json=body)
        return response.json()

        # ---------- CONFIGURATION AUDITS ----------
        retention_url = f"https://analyticsadmin.googleapis.com/v1beta/{property_id}/dataRetentionSettings"
        retention_response = requests.get(retention_url, headers=headers)
        
        if retention_response.status_code == 200:
            retention_resp = retention_response.json()
            retention_value = retention_resp.get("eventDataRetention", "UNKNOWN")
            retention_flag = "⚠️ Too Short" if "2_MONTHS" in retention_value or "14" not in retention_value else "✅ OK"
        else:
            retention_value = "ERROR"
            retention_flag = "❌ Not Retrieved"
        
        stream_url = f"https://analyticsadmin.googleapis.com/v1beta/{property_id}/webDataStreams"
        stream_response = requests.get(stream_url, headers=headers)
        
        if stream_response.status_code == 200:
            stream_resp = stream_response.json()
            streams = stream_resp.get("webDataStreams", [])
        else:
            st.warning(f"⚠️ Failed to fetch web data streams (status {stream_response.status_code})")
            streams = []
        
        stream_info = []
        if streams:
            for stream in streams:
                measurement_id = stream.get("measurementId", "N/A")
                enhanced_settings = stream.get("enhancedMeasurementSettings", {})
                enhanced = enhanced_settings.get("streamEnabled", False)
                stream_info.append((measurement_id, enhanced))
        else:
            stream_info.append(("Not Found", "Not Found"))
        

    # ---------- METRICS ----------
    core = fetch_metric_report(["sessions", "totalUsers", "purchaseRevenue"])
    metrics = {m["name"]: core["rows"][0]["metricValues"][i]["value"] for i, m in enumerate(core["metricHeaders"])}

    sessions = float(metrics["sessions"])
    users = float(metrics["totalUsers"])
    metrics["sessions_per_user"] = round(sessions / users, 2) if users else 0

    engage = fetch_metric_report(["engagedSessions", "sessions"])
    engaged = int(engage["rows"][0]["metricValues"][0]["value"])
    total_sessions = int(engage["rows"][0]["metricValues"][1]["value"])
    metrics["engagement_rate"] = round(engaged / total_sessions, 2) if total_sessions else 0

    purchase_raw = fetch_metric_report(["eventCount"], filters={
        "filter": {
            "fieldName": "eventName",
            "stringFilter": {"value": "purchase"}
        }
    })
    purchase_count = int(purchase_raw["rows"][0]["metricValues"][0]["value"]) if purchase_raw.get("rows") else 0
    metrics["purchase_event_count"] = purchase_count
    metrics["purchase_event_count_per_user"] = round(purchase_count / users, 2) if users else 0

    channel_data = fetch_metric_report(["sessions"], ["defaultChannelGrouping"])
    df_channel = pd.DataFrame([{
        "channel": row["dimensionValues"][0]["value"],
        "sessions": int(row["metricValues"][0]["value"])
    } for row in channel_data.get("rows", [])])
    unassigned_sessions = df_channel[df_channel["channel"] == "Unassigned"]["sessions"].sum()
    total = df_channel["sessions"].sum()
    metrics["percent_unassigned_sessions"] = round((unassigned_sessions / total) * 100, 2) if total else 0

    device_data = fetch_metric_report(["totalUsers"], ["deviceCategory", "platform"])
    device_rows = []
    for row in device_data.get("rows", []):
        combo = f"{row['dimensionValues'][0]['value']} / {row['dimensionValues'][1]['value']}"
        device_rows.append((f"Device Mix - {combo}", int(row["metricValues"][0]["value"])))

    conv_data = fetch_metric_report(["sessions", "eventCount"], ["defaultChannelGrouping", "sourceMedium"], filters={
        "filter": {
            "fieldName": "eventName",
            "stringFilter": {"value": "purchase"}
        }
    })
    conv_rows = []
    for row in conv_data.get("rows", []):
        grouping = row["dimensionValues"][0]["value"]
        source = row["dimensionValues"][1]["value"]
        s = int(row["metricValues"][0]["value"])
        p = int(row["metricValues"][1]["value"])
        cvr = round(p / s * 100, 2) if s else 0
        label = f"CVR - {grouping} ({source})"
        conv_rows.append((label, f"{cvr}%"))

    top_events = fetch_metric_report(["eventCount"], ["eventName"])
    event_spam = sorted([
        (f"Top Event - {row['dimensionValues'][0]['value']}", int(row["metricValues"][0]["value"]))
        for row in top_events.get("rows", [])
    ], key=lambda x: -x[1])[:10]

    # ---------- FINAL REPORT ----------
    st.markdown("### 📈 Metrics Overview")
    st.write(f"**Sessions** = {int(sessions):,}")
    st.write(f"**Users** = {int(users):,}")
    st.write(f"**Revenue** = ${float(metrics['purchaseRevenue']):,.2f}")
    st.write(f"**Sessions per User** = {metrics['sessions_per_user']}")
    st.write(f"**Engagement Rate** = {metrics['engagement_rate']}")
    st.write("**Purchase Tracking Accuracy:**")
    st.write(f"- eventCount for purchase = {metrics['purchase_event_count']}")
    st.write(f"- eventCount per user for purchase = {metrics['purchase_event_count_per_user']}")
    st.write(f"**% of Unassigned Traffic** = {metrics['percent_unassigned_sessions']}%")

    st.markdown("### 🧩 Device / Platform Mix")
    for label, value in device_rows:
        st.write(f"- {label} = {value:,} users")

    st.markdown("### 🔄 Conversion Rate Consistency")
    for label, value in conv_rows:
        st.write(f"- {label} = {value}")

    st.markdown("### 🔥 Top Events by Volume")
    for label, value in event_spam:
        st.write(f"- {label} = {value:,}")

    st.markdown("### ⚙️ GA4 Configuration Audit")
    st.write(f"**Data Retention Setting** = {retention_value} ({retention_flag})")
    st.write("**Web Data Streams:**")
    for mid, enhanced in stream_info:
        st.write(f"- Measurement ID: `{mid}` — Enhanced Measurement Enabled: `{enhanced}`")

    # ---------- CSV DOWNLOAD ----------
    audit_data = [
        ("Sessions", sessions),
        ("Users", users),
        ("Revenue", metrics["purchaseRevenue"]),
        ("Sessions per User", metrics["sessions_per_user"]),
        ("Engagement Rate", metrics["engagement_rate"]),
        ("Purchase Event Count", metrics["purchase_event_count"]),
        ("Purchase Event Count per User", metrics["purchase_event_count_per_user"]),
        ("% Unassigned Traffic", metrics["percent_unassigned_sessions"]),
        ("Data Retention", f"{retention_value} ({retention_flag})"),
    ]

    for i, (mid, enhanced) in enumerate(stream_info):
        audit_data.append((f"Web Stream {i+1} - Measurement ID", mid))
        audit_data.append((f"Web Stream {i+1} - Enhanced Measurement Enabled", enhanced))

    audit_data += device_rows + conv_rows + event_spam

    df_csv = pd.DataFrame(audit_data, columns=["Metric", "Value"])
    csv = df_csv.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Full Audit CSV", csv, "ga4_audit_summary.csv", "text/csv")
