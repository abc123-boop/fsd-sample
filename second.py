from flask import Flask, render_template, request, jsonify, url_for, session
import requests
import plotly.graph_objs as go
import plotly.io as pio
import json
import os
import numpy as np
from datetime import datetime
import pandas as pd

app = Flask(__name__)
app.secret_key = 'your_secret_key' 

API_URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Indicator_3_1_Climate_Indicators_Annual_Mean_Global_Surface_Temperature/FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson"
API_URL_CO2 = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Indicator_3_2_Climate_Indicators_Monthly_Atmospheric_Carbon_Dioxide_concentrations/FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson"
API_URL_SEA = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Indicator_3_3_melted_new/FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson"



@app.before_request
def initialize_breadcrumb():
    if 'breadcrumb' not in session:
        session['breadcrumb'] = [{'name': 'Home', 'url': url_for('index')}]

def add_to_breadcrumb(name, endpoint):
    breadcrumb = session.get('breadcrumb', [])
    if not any(item['url'] == url_for(endpoint) for item in breadcrumb):
        breadcrumb.append({'name': name, 'url': url_for(endpoint)})
    session['breadcrumb'] = breadcrumb

@app.route("/")
def index():
    session['breadcrumb'] = [{'name': 'Home', 'url': url_for('index')}]
    return render_template("first.html", breadcrumb=session['breadcrumb'])

@app.route("/second")
def second():
    add_to_breadcrumb('Temperature Trends', 'second')
    return render_template("second.html", breadcrumb=session['breadcrumb'])

@app.route("/countries")
def get_countries():
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()
        if "features" not in data:
            return jsonify({"error": "No features found in the data"}), 500

        countries = sorted(
            set(feature["properties"]["Country"] for feature in data["features"] if "properties" in feature)
        )
        return jsonify(countries)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/choropleth", methods=["GET"])
def get_choropleth():
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()

        year = request.args.get("year", "2023")
        year_field = f"F{year}"

        country_data = []
        temperatures = []
        for feature in data["features"]:
            properties = feature.get("properties", {})
            country = properties.get("Country")
            temperature = properties.get(year_field, None)
            if country and temperature is not None:
                country_data.append(country)
                temperatures.append(temperature)

        # Build the choropleth plot
        fig = go.Figure(data=go.Choropleth(
            locations=country_data,
            z=temperatures,
            locationmode='country names',
            colorscale='Viridis',
            colorbar_title='Temp Change (°C)',
        ))
        fig.update_layout(
            title=f"Global Temperature Change in {year}",
            geo=dict(
                showframe=False,
                showcoastlines=True,
                projection_type='equirectangular'
            )
        )

        graph_json = pio.to_json(fig)
        return jsonify({"plot": graph_json})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/plot", methods=["POST"])
def plot_country_data():
    try:
        country = request.json.get("country")
        if not country:
            return jsonify({"error": "No country selected"}), 400

        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()

        country_data = None
        for feature in data["features"]:
            if "properties" in feature and "Country" in feature["properties"]:
                if feature["properties"]["Country"].strip().lower() == country.strip().lower():
                    country_data = feature["properties"]
                    break

        if not country_data:
            return jsonify({"error": f"No data found for country: {country}"}), 404

        years = [
            int(field.replace("F", "")) for field in country_data.keys() if field.startswith("F")
        ]
        values = [
            country_data[field] for field in country_data.keys() if field.startswith("F")
        ]

        filtered_years = [year for year, value in zip(years, values) if value is not None]
        filtered_values = [value for value in values if value is not None]

        if not filtered_years or not filtered_values:
            return jsonify({"error": "No valid data for the selected country"}), 404

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=filtered_years,
            y=filtered_values,
            mode="lines+markers",
            name=country
        ))
        fig.update_layout(
            title=f"{country}",
            xaxis_title="Year",
            yaxis_title="Temperature Change (°C)",
            template="presentation",
        )

        graph_json = pio.to_json(fig)
        return jsonify({"plot": graph_json})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/third")
def co2_page():
    add_to_breadcrumb('CO2 Levels', 'co2_page')
    return render_template("third.html", breadcrumb=session['breadcrumb'])

@app.route("/co2_line_graph", methods=["GET"])
def co2_line_graph():
    try:
        year = request.args.get("year", "2023")  # Default to 2023 if no year is provided
        response = requests.get(API_URL_CO2)
        response.raise_for_status()
        data = response.json()

        # Convert date to month and year
        monthly_data = {}
        for feature in data["features"]:
            properties = feature.get("properties", {})
            date_str = properties.get("Date")
            if date_str:
                try:
                    # Adjusting date format parsing (check the format of the date field in your data)
                    date = datetime.strptime(date_str, "%YM%m")  # Example format: "1958M03"
                    if date.year == int(year):
                        month = date.month
                        value = properties.get("Value")
                        unit = properties.get("Unit")

                        # Convert percentage to ppm if the unit is 'percent'
                        if unit == "percent" and value is not None:
                            value = value * 10000  # Convert percent to ppm
                        
                        if month not in monthly_data:
                            monthly_data[month] = []
                        monthly_data[month].append(value)

                except ValueError:
                    continue  # Ignore any invalid date formats

        # Calculate the average for each month
        months = []
        avg_values = []
        for month in range(1, 13):
            if month in monthly_data:
                avg_values.append(np.mean(monthly_data[month]))
                months.append(month)

        # Create the line plot
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=months,
            y=avg_values,
            mode="lines+markers",
            name=f"CO2 Levels in {year}",
        ))
        fig.update_layout(
            title=f"CO2 Levels vs. Month for {year}",
            xaxis_title="Month",
            yaxis_title="CO2 Concentration (PPM)",
            template="presentation",
        )

        graph_json = pio.to_json(fig)
        return jsonify({"plot": graph_json})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/co2_bar_chart", methods=["GET"])
def co2_bar_chart():
    try:
        response = requests.get(API_URL_CO2)
        response.raise_for_status()
        data = response.json()

        yearly_data = {}
        for feature in data["features"]:
            properties = feature.get("properties", {})
            date_str = properties.get("Date")
            if date_str:
                try:
                    # Adjusting date format parsing (check the format of the date field in your data)
                    date = datetime.strptime(date_str, "%YM%m")  # Example format: "1958M03"
                    year = date.year
                    value = properties.get("Value")
                    unit = properties.get("Unit")

                    # Convert percentage to ppm if the unit is 'percent'
                    if unit == "percent" and value is not None:
                        value = value * 10000  # Convert percent to ppm

                    if year not in yearly_data:
                        yearly_data[year] = []
                    yearly_data[year].append(value)

                except ValueError:
                    continue  # Ignore any invalid date formats

        # Calculate the average for each year
        years = []
        avg_values = []
        for year in range(1958, 2025):
            if year in yearly_data:
                avg_values.append(np.mean(yearly_data[year]))
                years.append(year)

        # Create the bar chart
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=years,
            y=avg_values,
            name="Average CO2 Levels",
        ))
        fig.update_layout(
            title="Average CO2 Levels from 1958 to 2024",
            xaxis_title="Year",
            yaxis_title="Average CO2 Concentration (PPM)",
            template="presentation",
        )

        graph_json = pio.to_json(fig)
        return jsonify({"plot": graph_json})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/fourth")
def sea_change():
    add_to_breadcrumb('Sea Level Trends', 'sea_change')
    return render_template("fourth.html", breadcrumb=session['breadcrumb'])


@app.route("/mean_sea_levels_for_year", methods=["GET"])
def mean_sea_levels_for_year():
    """Generate a bar chart of mean sea levels for a specific year across all seas."""
    try:
        year = request.args.get("year")  # Input year
        if not year or not year.isdigit():
            return jsonify({"error": "Invalid year provided."}), 400

        year = int(year)
        response = requests.get(API_URL_SEA)
        response.raise_for_status()
        data = response.json()

        # Filter and calculate mean sea level for the specified year
        sea_data = {}
        for feature in data["features"]:
            properties = feature.get("properties", {})
            measure = properties.get("Measure")  # Sea name
            date_str = properties.get("Date")
            value = properties.get("Value")

            if measure and date_str and value is not None:
                try:
                    date = datetime.strptime(date_str[1:], "%m/%d/%Y")
                    if date.year == year:
                        value = float(value)
                        if measure not in sea_data:
                            sea_data[measure] = []
                        sea_data[measure].append(value)
                except Exception as e:
                    continue  # Skip malformed data

        if not sea_data:
            return jsonify({"error": f"No data available for the year {year}."}), 404

        # Calculate mean values
        sea_names = list(sea_data.keys())
        mean_values = [np.mean(sea_data[sea]) for sea in sea_names]

        # Create bar chart
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=mean_values,
            y=sea_names,
            orientation="h",
            name=f"Mean Sea Levels for {year}",
        ))
        fig.update_layout(
            title="Mean Sea Level vs Year for All Seas",
            xaxis_title="Mean Sea Level (mm)",
            yaxis_title="",
            template="presentation",
            barmode='group',
            xaxis=dict(
                tickangle=45, 
                tickmode='array',
            ),
            yaxis=dict(
                title=""
            ),
            margin=dict(
                l=150,  
                r=50,  
                t=50,  
                b=150  
            ),
            autosize=True  
        )

        graph_json = pio.to_json(fig)
        return jsonify({"plot": graph_json})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sea_level_vs_day", methods=["GET"])
def sea_level_vs_day():
    """Generate a line graph of sea level vs day for a specific sea with different lines for each year."""
    try:
        sea_name = request.args.get("seaName")  # Input sea name
        if not sea_name:
            return jsonify({"error": "Sea name is required."}), 400

        response = requests.get(API_URL_SEA)
        response.raise_for_status()
        data = response.json()

        # Filter data for the specified sea name
        sea_data = {}
        for feature in data["features"]:
            properties = feature.get("properties", {})
            measure = properties.get("Measure")
            date_str = properties.get("Date")
            value = properties.get("Value")

            if measure and sea_name.lower() in measure.lower() and date_str and value is not None:
                try:
                    date = datetime.strptime(date_str[1:], "%m/%d/%Y")
                    day = date.day
                    year = date.year  # Extract the year
                    if year not in sea_data:
                        sea_data[year] = {}
                    if day not in sea_data[year]:
                        sea_data[year][day] = []
                    sea_data[year][day].append(float(value))  # Collect the value for each day in each year
                except Exception as e:
                    continue

        if not sea_data:
            return jsonify({"error": f"No data available for {sea_name}."}), 404

        # Prepare data for plotting: plot a separate line for each year
        fig = go.Figure()
        for year, days_data in sea_data.items():
            days = sorted(days_data.keys())
            mean_values = [np.mean(days_data[day]) for day in days]  # Calculate the mean value for each day

            # Add a trace for this year's data
            fig.add_trace(go.Scatter(
                x=days,
                y=mean_values,
                mode="lines+markers",
                name=f"Sea Level {year}"
            ))

        fig.update_layout(
            title=f"Sea Level vs Day for {sea_name}",
            xaxis_title="Day of the Month",
            yaxis_title="Sea Level (mm)",
            template="presentation",
            margin=dict(
                l=150,  # Left margin
                r=0,  # Right margin
                t=50,  # Top margin
                b=150  # Bottom margin for x-axis labels
            ),
            autosize=True,
            height=500,
            width=800
        )

        graph_json = pio.to_json(fig)
        return jsonify({"plot": graph_json})

    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/seas", methods=["GET"])
def seas():
    """Endpoint to get available sea names for the dropdown options."""
    try:
        response = requests.get(API_URL_SEA)
        response.raise_for_status()
        data = response.json()

        seas = set()
        for feature in data["features"]:
            properties = feature.get("properties", {})
            sea_name = properties.get("Measure")
            if sea_name:
                seas.add(sea_name)

        return jsonify({"seas": sorted(seas)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
