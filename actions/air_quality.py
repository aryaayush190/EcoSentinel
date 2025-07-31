from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# API Keys
AQICN_API_KEY = "4d01ff35831e1c3fcef01b6fe936630499625578"

# Nominatim for OpenStreetMap geocoding
geolocator = Nominatim(user_agent="rasa_air_quality_bot")


class ActionQueryAirQuality(Action):
    def name(self) -> Text:
        return "action_query_air_quality"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        city = tracker.get_slot("city")
        location = tracker.get_slot("location")

        # Clear slots after reading to prevent persistence issues
        events = [SlotSet("city", None), SlotSet("location", None)]

        if not city and not location:
            dispatcher.utter_message(
                text="Please provide a city name or your location (e.g., 'Paris', 'New York', or '48.8566,2.3522').")
            return events

        lat, lon = None, None
        location_name = None

        # Handle location coordinates or address
        if location:
            if "," in location and len(location.split(",")) == 2:  # Assume lat,lon format
                try:
                    lat, lon = map(float, location.split(","))
                    location_name = f"coordinates ({lat:.4f}, {lon:.4f})"
                except ValueError:
                    dispatcher.utter_message(
                        text="Invalid coordinate format. Please use 'latitude,longitude' format (e.g., '40.4168,-3.7038').")
                    return events
            else:  # Geocode address using OpenStreetMap Nominatim
                try:
                    geo = geolocator.geocode(location, timeout=10)
                    if geo:
                        lat, lon = geo.latitude, geo.longitude
                        location_name = geo.address.split(",")[0]  # Extract main location name
                    else:
                        dispatcher.utter_message(
                            text=f"Could not find location '{location}'. Please check the spelling or try coordinates.")
                        return events
                except GeocoderTimedOut:
                    dispatcher.utter_message(text="Location lookup timed out. Please try again or use coordinates.")
                    return events

        # Handle city name
        elif city:
            try:
                geo = geolocator.geocode(city, timeout=10)
                if geo:
                    lat, lon = geo.latitude, geo.longitude
                    location_name = city
                else:
                    dispatcher.utter_message(
                        text=f"Could not find city '{city}'. Please check the spelling or try a different format.")
                    return events
            except GeocoderTimedOut:
                dispatcher.utter_message(text="City lookup timed out. Please try again.")
                return events

        # Get air quality data
        if lat is not None and lon is not None:
            air_quality_response = self._get_air_quality_data(lat, lon, location_name)
            dispatcher.utter_message(text=air_quality_response)
        else:
            dispatcher.utter_message(text="Unable to determine location coordinates. Please try again.")

        return events

    def _get_air_quality_data(self, lat: float, lon: float, location_name: str) -> str:
        """Fetch air quality data from AQICN API"""

        try:
            # Query AQICN with coordinates
            url = f"https://api.waqi.info/feed/geo:{lat};{lon}/?token={AQICN_API_KEY}"
            resp = requests.get(url, timeout=15)
            data = resp.json()

            if data["status"] == "ok":
                station_data = data["data"]
                aqi = station_data.get("aqi", "N/A")

                response = f"🌍 Air Quality near {location_name}:\n"
                response += f"📍 Coordinates: {lat:.4f}, {lon:.4f}\n\n"

                if isinstance(aqi, (int, float)):
                    response += f"• **AQI: {aqi}**\n"
                else:
                    response += f"• **AQI: {aqi}**\n"

                # Get individual pollutant data if available
                iaqi = station_data.get('iaqi', {})

                if 'pm25' in iaqi and iaqi['pm25'].get('v') is not None:
                    response += f"• PM2.5: {iaqi['pm25']['v']} µg/m³\n"
                if 'pm10' in iaqi and iaqi['pm10'].get('v') is not None:
                    response += f"• PM10: {iaqi['pm10']['v']} µg/m³\n"
                if 'o3' in iaqi and iaqi['o3'].get('v') is not None:
                    response += f"• Ozone (O3): {iaqi['o3']['v']} µg/m³\n"
                if 'no2' in iaqi and iaqi['no2'].get('v') is not None:
                    response += f"• Nitrogen Dioxide (NO2): {iaqi['no2']['v']} µg/m³\n"
                if 'so2' in iaqi and iaqi['so2'].get('v') is not None:
                    response += f"• Sulfur Dioxide (SO2): {iaqi['so2']['v']} µg/m³\n"
                if 'co' in iaqi and iaqi['co'].get('v') is not None:
                    response += f"• Carbon Monoxide (CO): {iaqi['co']['v']} mg/m³\n"

                if isinstance(aqi, (int, float)):
                    aqi_level = self._aqi_to_level(aqi)
                    response += f"\n🏷️ Air Quality Level: {aqi_level}\n"

                station_name = station_data.get('city', {}).get('name', 'Unknown Station')
                response += f"\n📊 Data source: AQICN ({station_name})"

                return response
            else:
                # Try alternative AQICN search by city name if coordinates fail
                if location_name and location_name != f"coordinates ({lat:.4f}, {lon:.4f})":
                    return self._get_air_quality_by_city_name(location_name)
                else:
                    return f"❌ No air quality data available for coordinates {lat:.4f}, {lon:.4f}. This might be a remote area without monitoring stations."

        except Exception as e:
            # Fallback to city name search if coordinates fail
            if location_name and location_name != f"coordinates ({lat:.4f}, {lon:.4f})":
                return self._get_air_quality_by_city_name(location_name)
            else:
                return f"❌ Error fetching air quality data: {str(e)}. Please try again later."

    def _get_air_quality_by_city_name(self, city_name: str) -> str:
        """Fallback method to get air quality by city name"""
        try:
            # Clean city name
            clean_city = city_name.strip().replace(" ", "%20")
            url = f"https://api.waqi.info/feed/{clean_city}/?token={AQICN_API_KEY}"
            resp = requests.get(url, timeout=15)
            data = resp.json()

            if data["status"] == "ok":
                station_data = data["data"]
                aqi = station_data.get("aqi", "N/A")

                response = f"🌍 Air Quality in {city_name}:\n"

                city_info = station_data.get('city', {})
                if city_info.get('geo'):
                    lat, lon = city_info['geo']
                    response += f"📍 Coordinates: {lat:.4f}, {lon:.4f}\n\n"
                else:
                    response += "\n"

                if isinstance(aqi, (int, float)):
                    response += f"• **AQI: {aqi}**\n"
                else:
                    response += f"• **AQI: {aqi}**\n"

                # Get individual pollutant data
                iaqi = station_data.get('iaqi', {})

                if 'pm25' in iaqi and iaqi['pm25'].get('v') is not None:
                    response += f"• PM2.5: {iaqi['pm25']['v']} µg/m³\n"
                if 'pm10' in iaqi and iaqi['pm10'].get('v') is not None:
                    response += f"• PM10: {iaqi['pm10']['v']} µg/m³\n"
                if 'o3' in iaqi and iaqi['o3'].get('v') is not None:
                    response += f"• Ozone (O3): {iaqi['o3']['v']} µg/m³\n"
                if 'no2' in iaqi and iaqi['no2'].get('v') is not None:
                    response += f"• Nitrogen Dioxide (NO2): {iaqi['no2']['v']} µg/m³\n"
                if 'so2' in iaqi and iaqi['so2'].get('v') is not None:
                    response += f"• Sulfur Dioxide (SO2): {iaqi['so2']['v']} µg/m³\n"
                if 'co' in iaqi and iaqi['co'].get('v') is not None:
                    response += f"• Carbon Monoxide (CO): {iaqi['co']['v']} mg/m³\n"

                if isinstance(aqi, (int, float)):
                    aqi_level = self._aqi_to_level(aqi)
                    response += f"\n🏷️ Air Quality Level: {aqi_level}\n"

                station_name = station_data.get('city', {}).get('name', city_name)
                response += f"\n📊 Data source: AQICN ({station_name})"

                return response
            else:
                return f"❌ No air quality data available for {city_name}. Please try a different city or check the spelling."

        except Exception as e:
            return f"❌ Error fetching air quality data for {city_name}: {str(e)}"

    def _aqi_to_level(self, aqi: float) -> str:
        """Convert AQI value to descriptive level"""
        if aqi <= 50:
            return "Good 🟢"
        elif aqi <= 100:
            return "Moderate 🟡"
        elif aqi <= 150:
            return "Unhealthy for Sensitive Groups 🟠"
        elif aqi <= 200:
            return "Unhealthy 🔴"
        elif aqi <= 300:
            return "Very Unhealthy 🟣"
        else:
            return "Hazardous ⚫"