import streamlit as st
import pandas as pd
import os
import json
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric, FilterExpression, Filter
from google.oauth2 import service_account

# --- Streamlit UI ---
st.title("GA4 90-Day Audit Tool")

uploaded_file = st.file_uploader("Upload your GA4 service account JSON", type=["json"])
property_id = st.text_input("Enter your GA4 Property ID")

run_button = st.button("Run Audit")

# --- GA4 Call ---
def run_ga4_audit(credentials, property_id):
    client = BetaAnalyticsDataClient(credentials=credentials)
    date_range = DateRange(start_date="90daysAgo", end_date="today")

    req = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[],
        metrics=[Metric(name="sessions"), Metric(name="totalUsers")],
        date_ranges=[date_range]
    )
    response = client.run_report(req)
    data = []
    for row in response.rows:
        record = {}
        for i, dim in enumerate(response.dimension_headers):
            record[dim.name] = row.dimension_values[i].value
        for i, met in enumerate(response.metric_headers):
            record[met.name] = row.metric_values[i].value
        data.append(record)
    return pd.DataFrame(data)

# --- Run Button Trigger ---
if run_button and uploaded_file and property_id:
    try:
        creds_dict = json.load(uploaded_file)
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        df = run_ga4_audit(credentials, property_id)
        st.success("Audit Complete!")
        st.dataframe(df)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "ga4_audit.csv", "text/csv")
    except Exception as e:
        st.error(f"Error: {e}")
