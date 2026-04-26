
import streamlit as st
import pandas as pd
from sodapy import Socrata
import re
import calendar
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(layout="wide")

@st.cache_data
def load_data():
    # Fetch the 311 data
    client = Socrata("data.cityofnewyork.us", None, timeout=60)
    results_311 = client.get("erm2-nwe9", query="SELECT * WHERE caseless_one_of(complaint_type, 'Maintenance or Facility') AND caseless_contains(descriptor_2, 'restroom') LIMIT 10000")
    # Fetch the PARKS Public Restrooms data
    results_restrooms = client.get("i7jb-7jku")

    # Convert to pandas DataFrame
    df_311 = pd.DataFrame.from_records(results_311)
    df_restrooms = pd.DataFrame.from_records(results_restrooms)

    # Process df_311 dates
    df_311['created_date'] = pd.to_datetime(df_311['created_date'])
    df_311['closed_date'] = pd.to_datetime(df_311['closed_date'])
    df_311['day'] = df_311['created_date'].dt.date
    df_311['day_of_week'] = df_311['created_date'].dt.day_name()
    df_311['month'] = df_311['created_date'].dt.month
    df_311['year'] = df_311['created_date'].dt.year

    # Filter df_311 to only include specific zip codes
    zip_codes_to_keep = ['10002', '11235', '11215', '11368', '11214']
    df_311 = df_311[df_311['incident_zip'].isin(zip_codes_to_keep)]

    # Add park name column based on incident_zip
    zip_to_park = {
        '10002': 'Allen Street Malls',
        '11235': 'Homecrest Playground',
        '11215': 'Gowanus waterfront  former salt lot',
        '11368': 'Flushing Meadows Corona Park Flushing Bay Promenade',
        '11214': 'Bensonhurst Park'
    }
    df_311['park_name'] = df_311['incident_zip'].map(zip_to_park)

    # Rename columns for better readability
    df_311 = df_311.rename(columns={
        'descriptor': 'Complaint Type',
        'descriptor_2': 'Restroom Element'
    })

    return df_311, df_restrooms

# Load the data
df_311, df_restrooms = load_data()

st.title("NYC Modular Public Restroom O&M Dashboard")

# Display df_311
st.header("Modular Public Restroom Complaints")
if 'df_311' in globals() and isinstance(df_311, pd.DataFrame):
    st.dataframe(df_311)
else:
    st.warning("df_311 not found or is not a DataFrame in the current environment.")
    st.info("Please ensure df_311 is loaded before running this app.")

if 'df_311' in globals() and isinstance(df_311, pd.DataFrame) and not df_311.empty:
    # Open Requests Section
    st.subheader("Open Requests")
    open_requests = df_311[(df_311['status'].str.lower() == 'in progress')] if 'status' in df_311.columns else pd.DataFrame()
    
    if not open_requests.empty:
        open_requests_agg = open_requests.groupby(['park_name', 'Complaint Type']).size().reset_index(name='count')
        open_requests_pivot = open_requests_agg.pivot(index='park_name', columns='Complaint Type', values='count').reset_index()
        open_requests_pivot.columns.name = None  # Remove the column index name
        open_requests_pivot = open_requests_pivot.rename(columns={'park_name': 'Park Location'})
        
        # Fill NaN with 0 and convert numeric columns to int
        numeric_cols = open_requests_pivot.select_dtypes(include=['float64', 'int64']).columns
        open_requests_pivot[numeric_cols] = open_requests_pivot[numeric_cols].fillna(0).astype(int)
        
        st.dataframe(open_requests_pivot, use_container_width=True)
    else:
        st.info("No open requests (in progress) at this time")

    # Response Time Analysis
    st.subheader("Response Time Analysis")

    # Check if descriptor columns exist
    if 'Complaint Type' in df_311.columns and 'Restroom Element' in df_311.columns:
        # Calculate response time for closed complaints
        closed_complaints = df_311.dropna(subset=['closed_date']).copy()
        if not closed_complaints.empty:
            closed_complaints['response_time_days'] = (closed_complaints['closed_date'] - closed_complaints['created_date']).dt.days
            
            # Overall average response time
            avg_response_time = closed_complaints['response_time_days'].mean()
            st.metric("Average Response Time (Days)", f"{avg_response_time:.1f}")
            
            # Response time by park and year (pivoted)
            response_by_park_year = closed_complaints.groupby(['park_name', 'year'])['response_time_days'].mean().reset_index()
            response_pivot = response_by_park_year.pivot(index='park_name', columns='year', values='response_time_days').reset_index()
            response_pivot.columns.name = None  # Remove the column index name
            response_pivot = response_pivot.rename(columns={'park_name': 'Park Location'})
            
            # Add all-time average column
            all_time_avg = closed_complaints.groupby('park_name')['response_time_days'].mean().reset_index()
            all_time_avg = all_time_avg.rename(columns={'response_time_days': 'All-Time Avg (Days)'})
            response_pivot = response_pivot.merge(all_time_avg, left_on='Park Location', right_on='park_name', how='left')
            response_pivot = response_pivot.drop('park_name', axis=1)
            
            response_pivot = response_pivot.round(1)  # Round to 1 decimal place
            
            st.dataframe(response_pivot, use_container_width=True)
            
        else:
            st.warning("No closed complaints available for response time analysis")

    else:
        st.warning("Descriptor columns not found in the data")

        # Channel Type Analysis by Park
    if 'open_data_channel_type' in df_311.columns:
        channel_analysis = df_311.groupby(['park_name', 'open_data_channel_type']).size().reset_index(name='count')
        channel_pivot = channel_analysis.pivot(index='park_name', columns='open_data_channel_type', values='count').reset_index()
        channel_pivot.columns.name = None  # Remove the column index name
        channel_pivot = channel_pivot.rename(columns={'park_name': 'Park Location'})
        
        # Fill NaN with 0 and convert numeric columns to int
        numeric_cols = channel_pivot.select_dtypes(include=['float64', 'int64']).columns
        channel_pivot[numeric_cols] = channel_pivot[numeric_cols].fillna(0).astype(int)
        
        st.subheader("Channel Type Analysis")
        st.dataframe(channel_pivot, use_container_width=True)

    # Park name filter
    st.header("Filter by Park")
    available_parks = sorted(df_311['park_name'].unique())
    selected_parks = st.multiselect("Select park(s) to view:", 
                                    available_parks, 
                                    default=available_parks)
    
    # Filter data based on selected parks
    filtered_df_311 = df_311[df_311['park_name'].isin(selected_parks)]
    
    if filtered_df_311.empty:
        st.warning("No data available for the selected park(s)")
    else:
        # Create tabs for different visualizations
        tab1, tab2 = st.tabs(["Time Trends", "Day of Week"])

        with tab1:
            st.subheader("Complaints Over Time")
            # Monthly bar trend with year legend
            monthly_complaints = filtered_df_311.groupby([
                filtered_df_311['created_date'].dt.year.rename('year'),
                filtered_df_311['created_date'].dt.month.rename('month')
            ]).size().reset_index(name='count')
            monthly_complaints['Month'] = monthly_complaints['month'].apply(lambda x: calendar.month_abbr[x])
            monthly_complaints['Year'] = monthly_complaints['year'].astype(str)

            fig_monthly = px.bar(monthly_complaints, x='Month', y='count', color='Year',
                                 title='Monthly Restroom Complaints Trend',
                                 labels={'Month': 'Month', 'count': 'Number of Complaints', 'Year': 'Year'},
                                 category_orders={'Month': list(calendar.month_abbr)[1:]},
                                 barmode='group')
            fig_monthly.update_xaxes(tickangle=0)
            st.plotly_chart(fig_monthly, use_container_width=True)

        with tab2:
            st.subheader("Complaints by Day of Week and Month")
            # Create heatmap of day of week vs month
            day_month_complaints = filtered_df_311.groupby([
                filtered_df_311['day_of_week'],
                filtered_df_311['month']
            ]).size().reset_index(name='count')

            # Create pivot table for heatmap
            heatmap_data = day_month_complaints.pivot(
                index='day_of_week',
                columns='month',
                values='count'
            ).fillna(0)

            # Reorder days of week
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            heatmap_data = heatmap_data.reindex(day_order)

            # Create month labels
            month_labels = [calendar.month_abbr[i] for i in range(1, 13)]

            # Create columns for heatmap and peak analysis
            col1, col2 = st.columns([2, 1])  # Heatmap gets more space

            with col1:
                fig_heatmap = px.imshow(heatmap_data,
                                       labels=dict(x="Month", y="Day of Week", color="Number of Complaints"),
                                       x=month_labels,
                                       y=day_order,
                                       title="Restroom Complaints Heatmap: Day of Week vs Month",
                                       color_continuous_scale='Blues')
                fig_heatmap.update_xaxes(side="bottom")
                st.plotly_chart(fig_heatmap, use_container_width=True)

            with col2:
                # Add per-park analysis
                st.markdown("**Peak Complaint Days by Park**")
                park_day_analysis = filtered_df_311.groupby(['park_name', 'day_of_week']).size().reset_index(name='count')
                park_day_analysis = park_day_analysis.sort_values(['park_name', 'count'], ascending=[True, False])

                # Get top day for each park
                top_days_per_park = park_day_analysis.groupby('park_name').first().reset_index()
                top_days_per_park = top_days_per_park.rename(columns={'day_of_week': 'Peak Day', 'count': 'Complaints'})

                # Add peak month analysis
                park_month_analysis = filtered_df_311.groupby(['park_name', 'month']).size().reset_index(name='count')
                park_month_analysis = park_month_analysis.sort_values(['park_name', 'count'], ascending=[True, False])

                # Get top month for each park
                top_months_per_park = park_month_analysis.groupby('park_name').first().reset_index()
                top_months_per_park['Peak Month'] = top_months_per_park['month'].apply(lambda x: calendar.month_name[x])
                top_months_per_park = top_months_per_park[['park_name', 'Peak Month']]

                # Merge peak day and peak month data
                peak_analysis = pd.merge(top_days_per_park, top_months_per_park, on='park_name', how='left')

                st.dataframe(peak_analysis[['park_name', 'Peak Day', 'Peak Month']], use_container_width=True)

else:
    st.warning("No data available for visualizations")
