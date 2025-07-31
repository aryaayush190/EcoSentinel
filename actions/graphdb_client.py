from typing import Any, Text, Dict, List, Optional
import re
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from SPARQLWrapper import SPARQLWrapper, JSON
import logging
from urllib.parse import unquote

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GraphDB Endpoints
WATERBASE_SPARQL_ENDPOINT = "http://localhost:7200/repositories/waterbase"
POLICY_SPARQL_ENDPOINT = "http://localhost:7200/repositories/policy"

# Timeout for SPARQL queries (in seconds)
QUERY_TIMEOUT = 60

# Supported Spanish cities for policy queries
SUPPORTED_CITIES = [
    "Madrid", "Barcelona", "Valencia", "Seville", "Bilbao", "Zaragoza",
    "Málaga", "Palma de Mallorca", "Murcia", "Las Palmas", "Alicante",
    "Córdoba", "Valladolid", "Vigo", "Granada", "Oviedo"
]


class WaterQualityQueryHandler:
    """Enhanced water quality data handler with new schema.org-based SPARQL queries"""

    @staticmethod
    def extract_municipality_name(user_message: str) -> Optional[str]:
        """Extract municipality/city name from user message with improved patterns"""
        # Direct municipality extraction patterns
        patterns = [
            # Pattern for "water quality for/in [City]"
            r'\b(?:water\s+quality|quality|data|pollution)\s+(?:for|in|at|of)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)',
            # Pattern for "[City] water quality"
            r'\b([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(?:water|quality|pollution)',
            # Pattern for "in/for/about [City]"
            r'\b(?:in|for|about|regarding|from)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)',
            # Pattern for "city of [City]"
            r'\bcity\s+(?:of\s+)?([A-Za-z]+(?:\s+[A-Za-z]+)?)',
            # Generic city pattern
            r'\b([A-Za-z]{3,20})\s+(?:city|municipality|town)',
            # Simple word extraction (fallback)
            r'\b([A-Z][a-z]{2,15})\b'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, user_message, re.IGNORECASE)
            for match in matches:
                match = match.strip()
                # Filter out common non-city words
                if (len(match) >= 3 and
                        match.lower() not in ['water', 'quality', 'data', 'show', 'get', 'find', 'city', 'the', 'and',
                                              'for']):
                    return match.title()  # Capitalize properly

        # Last resort: look for capitalized words that might be city names
        words = re.findall(r'\b[A-Z][a-z]{2,15}\b', user_message)
        for word in words:
            if word.lower() not in ['Show', 'Get', 'Find', 'Water', 'Quality', 'Data', 'The', 'And', 'For']:
                return word

        return None

    @staticmethod
    def get_municipality_water_quality_query(municipality_name: str) -> str:
        """Get water quality data for a specific municipality using new schema"""

        query = f"""
        PREFIX schema1: <https://schema.org/>
        PREFIX envo: <http://purl.obolibrary.org/obo/ENVO_>
        PREFIX ex: <http://example.org/resource/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT ?chemical ?value ?unit ?year ?waterBody ?lat ?lon
        WHERE {{
          ?s schema1:location ?location ;
             schema1:name ?chemical ;
             schema1:value ?value ;
             schema1:unitCode ?unit ;
             schema1:dateMeasured ?year .

          # Flexible matching for municipality names
          FILTER(
            CONTAINS(LCASE(?location), LCASE("{municipality_name}")) ||
            CONTAINS(LCASE("{municipality_name}"), LCASE(?location)) ||
            ?location = "{municipality_name}" ||
            ?location = "{municipality_name.upper()}" ||
            ?location = "{municipality_name.lower()}"
          )

          OPTIONAL {{
            ?s schema1:waterBody ?waterBody .
          }}

          OPTIONAL {{
            ?s schema1:latitude ?lat ;
               schema1:longitude ?lon .
          }}
        }}
        ORDER BY DESC(?year) ?chemical
        LIMIT 100
        """
        return query

    @staticmethod
    def get_river_water_quality_query(municipality_name: str) -> str:
        """Get river water quality data for a specific municipality"""

        query = f"""
        PREFIX schema1: <https://schema.org/>
        PREFIX envo: <http://purl.obolibrary.org/obo/ENVO_>
        PREFIX ex: <http://example.org/resource/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT ?chemical ?value ?unit ?year ?lat ?lon
        WHERE {{
          ?s schema1:location ?location ;
             schema1:waterBody "RW" ;
             schema1:name ?chemical ;
             schema1:value ?value ;
             schema1:unitCode ?unit ;
             schema1:dateMeasured ?year .

          # Flexible matching for municipality names
          FILTER(
            CONTAINS(LCASE(?location), LCASE("{municipality_name}")) ||
            CONTAINS(LCASE("{municipality_name}"), LCASE(?location)) ||
            ?location = "{municipality_name}"
          )

          OPTIONAL {{
            ?s schema1:latitude ?lat ;
               schema1:longitude ?lon .
          }}
        }}
        ORDER BY DESC(?year) ?chemical
        LIMIT 100
        """
        return query

    @staticmethod
    def get_monitoring_stations_query(municipality_name: str) -> str:
        """Get monitoring station details for a municipality"""

        query = f"""
        PREFIX schema1: <https://schema.org/>
        PREFIX envo: <http://purl.obolibrary.org/obo/ENVO_>
        PREFIX ex: <http://example.org/resource/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT DISTINCT ?location ?lat ?lon ?waterBody (COUNT(?chemical) as ?parameterCount)
        WHERE {{
          ?s schema1:location ?location ;
             schema1:latitude ?lat ;
             schema1:longitude ?lon ;
             schema1:name ?chemical .

          # Flexible matching for municipality names
          FILTER(
            CONTAINS(LCASE(?location), LCASE("{municipality_name}")) ||
            CONTAINS(LCASE("{municipality_name}"), LCASE(?location)) ||
            ?location = "{municipality_name}"
          )

          OPTIONAL {{
            ?s schema1:waterBody ?waterBody .
          }}
        }}
        GROUP BY ?location ?lat ?lon ?waterBody
        ORDER BY DESC(?parameterCount)
        """
        return query

    @staticmethod
    def get_fuzzy_municipality_search_query(partial_name: str) -> str:
        """Search for municipalities that partially match the input"""

        query = f"""
        PREFIX schema1: <https://schema.org/>
        PREFIX envo: <http://purl.obolibrary.org/obo/ENVO_>
        PREFIX ex: <http://example.org/resource/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT DISTINCT ?location (COUNT(?chemical) as ?measurementCount)
        WHERE {{
          ?s schema1:location ?location ;
             schema1:name ?chemical .

          # Fuzzy matching for partial names
          FILTER(
            CONTAINS(LCASE(?location), LCASE("{partial_name}")) ||
            CONTAINS(LCASE("{partial_name}"), LCASE(?location))
          )
        }}
        GROUP BY ?location
        ORDER BY DESC(?measurementCount)
        LIMIT 10
        """
        return query

    @staticmethod
    def get_all_available_municipalities_query() -> str:
        """Get all municipalities available in the water quality database"""

        query = """
        PREFIX schema1: <https://schema.org/>
        PREFIX envo: <http://purl.obolibrary.org/obo/ENVO_>
        PREFIX ex: <http://example.org/resource/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT DISTINCT ?location (COUNT(?chemical) as ?measurementCount)
        WHERE {
          ?s schema1:location ?location ;
             schema1:name ?chemical .
        }
        GROUP BY ?location
        ORDER BY DESC(?measurementCount)
        LIMIT 50
        """
        return query

    @staticmethod
    def get_water_quality_summary_query(municipality_name: str) -> str:
        """Get summary of water quality parameters for a municipality"""

        query = f"""
        PREFIX schema1: <https://schema.org/>
        PREFIX envo: <http://purl.obolibrary.org/obo/ENVO_>
        PREFIX ex: <http://example.org/resource/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT ?chemical (COUNT(?value) as ?measurementCount) 
               (AVG(xsd:float(?value)) as ?avgValue) 
               (MIN(xsd:float(?value)) as ?minValue)
               (MAX(xsd:float(?value)) as ?maxValue)
               (SAMPLE(?unit) as ?unit)
               (MAX(?year) as ?latestYear)
        WHERE {{
          ?s schema1:location ?location ;
             schema1:name ?chemical ;
             schema1:value ?value ;
             schema1:unitCode ?unit ;
             schema1:dateMeasured ?year .

          # Flexible matching for municipality names
          FILTER(
            CONTAINS(LCASE(?location), LCASE("{municipality_name}")) ||
            CONTAINS(LCASE("{municipality_name}"), LCASE(?location)) ||
            ?location = "{municipality_name}"
          )

          FILTER(isNumeric(?value))
        }}
        GROUP BY ?chemical
        ORDER BY DESC(?measurementCount)
        LIMIT 20
        """
        return query

    @staticmethod
    def format_measurement_value(value: str, unit: str = None) -> str:
        """Format measurement values for display"""
        try:
            if value and str(value).strip():
                # Try to parse as float
                num_val = float(value)

                # Format based on magnitude
                if num_val == 0:
                    formatted = "0"
                elif abs(num_val) < 0.001:
                    formatted = f"{num_val:.2e}"
                elif abs(num_val) < 1:
                    formatted = f"{num_val:.3f}"
                elif abs(num_val) < 100:
                    formatted = f"{num_val:.2f}"
                else:
                    formatted = f"{num_val:.1f}"

                # Add unit if available
                if unit and unit.strip():
                    formatted += f" {unit}"

                return formatted
            return "No data"
        except (ValueError, TypeError):
            return str(value) if value else "No data"


class ActionQueryWaterData(Action):
    """Enhanced action for querying water data with new schema and improved municipality support"""

    def name(self) -> Text:
        return "action_query_water_data"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_message = tracker.latest_message.get('text', '')

        # Try to get municipality from slot first, then extract from message
        municipality = tracker.get_slot("city")
        if not municipality:
            municipality = WaterQualityQueryHandler.extract_municipality_name(user_message)

        # Check for specific query types
        is_river_query = any(word in user_message.lower() for word in ["river", "stream", "rw"])
        is_station_query = any(word in user_message.lower() for word in ["station", "monitoring", "location"])
        is_summary_query = any(word in user_message.lower() for word in ["summary", "overview", "statistics"])

        if not municipality:
            # If no municipality found, show available options
            sparql = SPARQLWrapper(WATERBASE_SPARQL_ENDPOINT)
            sparql.setReturnFormat(JSON)
            sparql.setTimeout(QUERY_TIMEOUT)

            try:
                query = WaterQualityQueryHandler.get_all_available_municipalities_query()
                sparql.setQuery(query)
                results = sparql.query().convert()

                if results["results"]["bindings"]:
                    response = "🌊 **Available municipalities with water quality data:**\n\n"
                    for result in results["results"]["bindings"][:15]:
                        location = result.get('location', {}).get('value', 'Unknown')
                        count = result.get('measurementCount', {}).get('value', '0')
                        response += f"• **{location}** ({count} measurements)\n"

                    response += "\n💡 **Tip**: Try asking 'Show water quality for [municipality name]'"
                    dispatcher.utter_message(text=response)
                else:
                    dispatcher.utter_message(
                        text="Please provide a municipality name for water quality data.\n\n"
                             "Examples:\n"
                             "• 'Show water quality for AArnoia'\n"
                             "• 'River water data for Madrid'\n"
                             "• 'Water pollution in Barcelona'")
                return []
            except Exception as e:
                logger.error(f"Error getting available municipalities: {str(e)}")
                dispatcher.utter_message(
                    text="Please provide a municipality name for water quality data.\n\n"
                         "Example: 'Show water quality for AArnoia'")
                return []

        sparql = SPARQLWrapper(WATERBASE_SPARQL_ENDPOINT)
        sparql.setReturnFormat(JSON)
        sparql.setTimeout(QUERY_TIMEOUT)

        try:
            logger.info(f"Querying water data for municipality: {municipality}")

            # Try exact match first
            if is_summary_query:
                query = WaterQualityQueryHandler.get_water_quality_summary_query(municipality)
            elif is_station_query:
                query = WaterQualityQueryHandler.get_monitoring_stations_query(municipality)
            elif is_river_query:
                query = WaterQualityQueryHandler.get_river_water_quality_query(municipality)
            else:
                query = WaterQualityQueryHandler.get_municipality_water_quality_query(municipality)

            sparql.setQuery(query)
            results = sparql.query().convert()

            # If no results found, try fuzzy search for similar municipality names
            if not results["results"]["bindings"]:
                logger.info(f"No exact match found for '{municipality}', trying fuzzy search...")
                fuzzy_query = WaterQualityQueryHandler.get_fuzzy_municipality_search_query(municipality)
                sparql.setQuery(fuzzy_query)
                fuzzy_results = sparql.query().convert()

                if fuzzy_results["results"]["bindings"]:
                    response = f"❌ No exact match found for '{municipality}'. Did you mean one of these?\n\n"
                    for result in fuzzy_results["results"]["bindings"][:5]:
                        location = result.get('location', {}).get('value', 'Unknown')
                        count = result.get('measurementCount', {}).get('value', '0')
                        response += f"• **{location}** ({count} measurements)\n"

                    response += f"\n💡 Try: 'Show water quality for [exact municipality name]'"
                    dispatcher.utter_message(text=response)
                    return []

            if not results["results"]["bindings"]:
                dispatcher.utter_message(
                    text=f"❌ No water quality data found for '{municipality}'. Please check the municipality name and try again.\n\n"
                         f"💡 **Tip**: Try asking for available municipalities first.")
                return []

            # Format response based on query type
            if is_station_query:
                response = f"📍 **Monitoring Stations for {municipality}:**\n\n"

                for result in results["results"]["bindings"]:
                    location = result.get('location', {}).get('value', municipality)
                    lat = result.get('lat', {}).get('value', 'N/A')
                    lon = result.get('lon', {}).get('value', 'N/A')
                    water_body = result.get('waterBody', {}).get('value', 'Unknown')
                    param_count = result.get('parameterCount', {}).get('value', '0')

                    response += f"• **Location**: {location}\n"
                    response += f"  **Coordinates**: {lat}, {lon}\n"
                    response += f"  **Water Body Type**: {water_body}\n"
                    response += f"  **Parameters Monitored**: {param_count}\n\n"

            elif is_summary_query:
                response = f"📊 **Water Quality Summary for {municipality}:**\n\n"

                for result in results["results"]["bindings"]:
                    chemical = result.get('chemical', {}).get('value', 'Unknown')
                    count = result.get('measurementCount', {}).get('value', '0')
                    avg_val = result.get('avgValue', {}).get('value', '')
                    min_val = result.get('minValue', {}).get('value', '')
                    max_val = result.get('maxValue', {}).get('value', '')
                    unit = result.get('unit', {}).get('value', '')
                    latest_year = result.get('latestYear', {}).get('value', '')

                    response += f"• **{chemical}**:\n"
                    response += f"  Measurements: {count}\n"
                    if avg_val:
                        response += f"  Average: {WaterQualityQueryHandler.format_measurement_value(avg_val, unit)}\n"
                        response += f"  Range: {WaterQualityQueryHandler.format_measurement_value(min_val, unit)} - {WaterQualityQueryHandler.format_measurement_value(max_val, unit)}\n"
                    if latest_year:
                        response += f"  Latest data: {latest_year}\n"
                    response += "\n"

            else:
                # General water quality response
                response = f"🌊 **Water Quality Data for {municipality}:**\n\n"

                # Group parameters by type
                physical_params = []
                chemical_params = []
                other_params = []

                years_available = set()
                water_bodies = set()
                locations = set()

                for result in results["results"]["bindings"]:
                    chemical = result.get('chemical', {}).get('value', 'Unknown Parameter')
                    value = result.get('value', {}).get('value', '')
                    unit = result.get('unit', {}).get('value', '')
                    year = result.get('year', {}).get('value', '')
                    water_body = result.get('waterBody', {}).get('value', '')
                    lat = result.get('lat', {}).get('value', '')
                    lon = result.get('lon', {}).get('value', '')

                    # Track metadata
                    if year:
                        years_available.add(year)
                    if water_body:
                        water_bodies.add(water_body)
                    if lat and lon:
                        locations.add(f"{lat[:6]}, {lon[:6]}")

                    formatted_value = WaterQualityQueryHandler.format_measurement_value(value, unit)

                    param_info = {
                        'name': chemical,
                        'value': formatted_value,
                        'year': year,
                        'water_body': water_body
                    }

                    # Categorize parameters
                    param_lower = chemical.lower()
                    if any(word in param_lower for word in
                           ['ph', 'temperature', 'temp', 'conductivity', 'turbidity', 'oxygen', 'dissolved']):
                        physical_params.append(param_info)
                    elif any(word in param_lower for word in
                             ['calcium', 'magnesium', 'sodium', 'potassium', 'chloride', 'sulphate', 'sulfate',
                              'carbonate', 'bicarbonate', 'hardness', 'nitrate', 'phosphate', 'nitrogen']):
                        chemical_params.append(param_info)
                    else:
                        other_params.append(param_info)

                # Display categorized results
                if physical_params:
                    response += "**🌡️ Physical Properties:**\n"
                    for param in physical_params[:8]:
                        response += f"  • **{param['name']}**: {param['value']}"
                        if param['year']:
                            response += f" ({param['year']})"
                        response += "\n"
                    response += "\n"

                if chemical_params:
                    response += "**⚗️ Chemical Composition:**\n"
                    for param in chemical_params[:10]:
                        response += f"  • **{param['name']}**: {param['value']}"
                        if param['year']:
                            response += f" ({param['year']})"
                        response += "\n"
                    response += "\n"

                if other_params:
                    response += "**📊 Other Measurements:**\n"
                    for param in other_params[:8]:
                        response += f"  • **{param['name']}**: {param['value']}"
                        if param['year']:
                            response += f" ({param['year']})"
                        response += "\n"
                    response += "\n"

                # Add summary information
                total_measurements = len(results["results"]["bindings"])
                response += f"📈 **Total measurements:** {total_measurements}\n"

                if years_available:
                    year_range = f"{min(years_available)} - {max(years_available)}" if len(years_available) > 1 else \
                    list(years_available)[0]
                    response += f"📅 **Data period:** {year_range}\n"

                if water_bodies:
                    response += f"🏞️ **Water bodies:** {', '.join(sorted(water_bodies))}\n"

                if locations:
                    response += f"📍 **Monitoring locations:** {len(locations)} station(s)\n"

        except Exception as e:
            logger.error(f"SPARQL query error: {str(e)}")
            dispatcher.utter_message(
                text="Sorry, there was an error accessing the water quality database. Please try again later.\n\n"
                     f"Error details: {str(e)}")
            return []

        dispatcher.utter_message(text=response)
        return []


# Keep your existing PolicyQueryHandler and ActionQueryPolicy classes unchanged
class PolicyQueryHandler:
    """Handles city policy and regulation queries - unchanged"""

    @staticmethod
    def extract_city_name(user_message: str) -> Optional[str]:
        """Extract city name from user message with fuzzy matching"""
        for city in SUPPORTED_CITIES:
            if city.lower() in user_message.lower():
                return city

        patterns = [
            r'\b(?:in|for|about|regarding)\s+([A-Za-z\s]+?)(?:\s|$|[,.!?])',
            r'\bcity\s+(?:of\s+)?([A-Za-z\s]+?)(?:\s|$|[,.!?])',
            r'\b([A-Za-z\s]{3,20})\s+(?:city|policies|regulations)'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, user_message, re.IGNORECASE)
            for match in matches:
                match = match.strip()
                for city in SUPPORTED_CITIES:
                    if match.lower() in city.lower() or city.lower() in match.lower():
                        return city
        return None

    @staticmethod
    def get_enhanced_policy_query(city: str, query_focus: str = "comprehensive") -> str:
        """Generate enhanced SPARQL query for city policies based on user focus"""

        base_prefixes = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX esp: <http://spain.environmental.org/>
        PREFIX openlca: <http://openlca.org/schema/>
        """

        if query_focus == "comprehensive":
            query = f"""
            {base_prefixes}

            SELECT DISTINCT ?cityName ?policyType ?policyName ?effectiveDate 
                   ?policyDescription ?complianceReq ?wasteSchedule 
                   ?emissionStandard ?waterRestrictions ?recyclingRate ?noiseLimit
            WHERE {{
              ?city a esp:City ;
                    rdfs:label ?cityName .

              FILTER(
                ?cityName = "{city}" ||
                CONTAINS(LCASE(?cityName), LCASE("{city}")) ||
                CONTAINS(LCASE("{city}"), LCASE(?cityName))
              )

              OPTIONAL {{
                ?city esp:hasRegulation ?regulation .
                ?regulation a ?policyType ;
                           rdfs:label ?policyName ;
                           esp:effectiveDate ?effectiveDate ;
                           esp:regulationText ?policyDescription ;
                           esp:complianceRequirement ?complianceReq .
              }}

              OPTIONAL {{
                ?city esp:hasWasteSystem ?wasteSystem .
                ?wasteSystem esp:hasContainer ?container .
                ?container esp:collectionSchedule ?wasteSchedule .
              }}

              OPTIONAL {{
                ?city esp:hasRegulation ?vehicleReg .
                ?vehicleReg a esp:VehicleRegulation ;
                           esp:emissionStandard ?emissionStandard .
              }}

              OPTIONAL {{
                ?city esp:hasRegulation ?waterReg .
                ?waterReg a esp:WaterConservationLaw ;
                         esp:waterUsageLimit ?waterRestrictions .
              }}

              OPTIONAL {{
                ?metrics rdfs:label ?metricsLabel ;
                        openlca:wasteRecyclingRate ?recyclingRate .
                FILTER(CONTAINS(LCASE(?metricsLabel), LCASE("{city}")))
              }}

              OPTIONAL {{
                ?city esp:hasRegulation ?noiseReg .
                ?noiseReg a esp:NoiseRegulation ;
                         esp:noiseLevel ?noiseLimit .
              }}
            }}
            ORDER BY ?effectiveDate
            LIMIT 30
            """
        else:
            query = f"""
            {base_prefixes}

            SELECT DISTINCT ?cityName ?containerType ?collectionSchedule 
                   ?recyclingRate ?wasteManagementPolicy
            WHERE {{
              ?city a esp:City ;
                    rdfs:label ?cityName ;
                    esp:hasWasteSystem ?wasteSystem .

              FILTER(CONTAINS(LCASE(?cityName), LCASE("{city}")))

              ?wasteSystem esp:hasContainer ?container .
              ?container esp:containerColor ?containerType ;
                        esp:collectionSchedule ?collectionSchedule .

              OPTIONAL {{
                ?metrics rdfs:label ?metricsLabel ;
                        openlca:wasteRecyclingRate ?recyclingRate .
                FILTER(CONTAINS(LCASE(?metricsLabel), LCASE("{city}")))
              }}

              OPTIONAL {{
                ?city esp:hasRegulation ?wastePolicy .
                ?wastePolicy a esp:WasteManagementRegulation ;
                           rdfs:label ?wasteManagementPolicy .
              }}
            }}
            """
        return query


class ActionQueryPolicy(Action):
    def name(self) -> Text:
        return "action_query_policy"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_message = tracker.latest_message.get('text', '')

        city = tracker.get_slot("city")
        if not city:
            city = PolicyQueryHandler.extract_city_name(user_message)

        if not city:
            dispatcher.utter_message(
                text=f"Please specify a city name. We currently have policy data for: {', '.join(SUPPORTED_CITIES)}."
            )
            return []

        if city not in SUPPORTED_CITIES:
            dispatcher.utter_message(
                text=f"We don't have policy data for '{city}' currently, but we are continuously updating our database. "
                     f"Available cities: {', '.join(SUPPORTED_CITIES)}."
            )
            return []

        sparql = SPARQLWrapper(POLICY_SPARQL_ENDPOINT)
        sparql.setReturnFormat(JSON)
        sparql.setTimeout(QUERY_TIMEOUT)

        try:
            query_focus = "waste" if any(
                word in user_message.lower() for word in ["waste", "garbage", "recycling"]) else "comprehensive"
            query = PolicyQueryHandler.get_enhanced_policy_query(city, query_focus)

            sparql.setQuery(query)
            results = sparql.query().convert()

        except Exception as e:
            logger.error(f"Policy SPARQL query error: {str(e)}")
            dispatcher.utter_message(
                text="Sorry, there was an error accessing the policy database. Please try again later.")
            return []

        if not results["results"]["bindings"]:
            dispatcher.utter_message(text=f"No policy data found for {city}. The database might be updating.")
            return []

        # Format response (keeping original policy formatting)
        response = f"🏛️ **Environmental Policies for {city}:**\n\n"

        policies_found = []
        waste_info = []
        emission_info = []
        water_info = []

        for result in results["results"]["bindings"]:
            if result.get('policyName'):
                policy_name = result.get('policyName', {}).get('value', 'Unknown')
                policy_type = result.get('policyType', {}).get('value', '').split('/')[-1]
                effective_date = result.get('effectiveDate', {}).get('value', 'N/A')
                description = result.get('policyDescription', {}).get('value', '')

                policies_found.append({
                    'name': policy_name,
                    'type': policy_type,
                    'date': effective_date,
                    'description': description[:100] + "..." if len(description) > 100 else description
                })

            if result.get('wasteSchedule'):
                waste_info.append(result.get('wasteSchedule', {}).get('value'))
            if result.get('emissionStandard'):
                emission_info.append(result.get('emissionStandard', {}).get('value'))
            if result.get('waterRestrictions'):
                water_info.append(result.get('waterRestrictions', {}).get('value'))

        if policies_found:
            response += "**📋 Regulations & Policies:**\n"
            for policy in policies_found[:5]:
                response += f"• **{policy['name']}** ({policy['type']})\n"
                response += f"  Effective: {policy['date']}\n"
                if policy['description']:
                    response += f"  {policy['description']}\n"
                response += "\n"

        if waste_info:
            response += "**🗑️ Waste Collection:**\n"
            for info in set(waste_info):
                response += f"• {info}\n"
            response += "\n"

        if emission_info:
            response += "**🚗 Emission Standards:**\n"
            for info in set(emission_info):
                response += f"• {info}\n"
            response += "\n"

        if water_info:
            response += "**💧 Water Restrictions:**\n"
            for info in set(water_info):
                response += f"• {info}\n"
            response += "\n"

        for result in results["results"]["bindings"]:
            if result.get('recyclingRate'):
                rate = result.get('recyclingRate', {}).get('value')
                response += f"**♻️ Recycling Rate:** {rate}%\n\n"
                break

        for result in results["results"]["bindings"]:
            if result.get('noiseLimit'):
                limit = result.get('noiseLimit', {}).get('value')
                response += f"**🔇 Noise Limits:** {limit}\n\n"
                break

        dispatcher.utter_message(text=response)
        return []