from typing import Any, Text, Dict, List, Optional
import re
import logging
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from groq import Groq
from SPARQLWrapper import SPARQLWrapper, JSON

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Groq setup
GROQ_API_KEY = "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"
GROQ_MODEL = "deepseek-r1-distill-llama-70b"

# GraphDB endpoint
WATERBASE_SPARQL_ENDPOINT = "http://localhost:7200/repositories/waterbase"
POLICY_SPARQL_ENDPOINT = "http://localhost:7200/repositories/policy"


class ResponseAnalyzer:
    """Utility class for response analysis and improvement"""

    def __init__(self, groq_api_key: str, groq_model: str):
        self.client = Groq(api_key=groq_api_key)
        self.model = groq_model

    def analyze_and_improve_response(self, original_response: str, user_query: str,
                                     user_language: str = "en", city_context: str = None) -> str:
        """Analyze and improve the bot response using Groq"""

        # Build context for analysis
        context = self._build_analysis_context(original_response, user_query, user_language, city_context)

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": context}],
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=2048,
                top_p=0.9,
                stream=False
            )

            improved_response = completion.choices[0].message.content.strip()
            return improved_response

        except Exception as e:
            logger.error(f"Groq API error: {str(e)}")
            # Return original response with minimal improvement if Groq fails
            return self._fallback_improvement(original_response, user_language)

    def _build_analysis_context(self, response: str, query: str, language: str, city: str) -> str:
        """Build comprehensive context for Groq analysis"""

        context = f"""
You are an expert response analyzer for an environmental data chatbot. Your task is to analyze and improve the given bot response.

ORIGINAL USER QUERY: "{query}"
ORIGINAL BOT RESPONSE: "{response}"
USER LANGUAGE: {language}
CITY CONTEXT: {city or 'Not available'}

DATA SOURCES USED:
- OpenAQ/AQICN APIs for real-time air quality data
- GraphDB repositories (waterbase/policy) at localhost:7200 with EEA schema
- Water quality data with parameters like pH, temperature, conductivity, nutrients
- City policy data for Spanish cities (Madrid, Barcelona, Valencia, etc.)

ANALYSIS REQUIREMENTS:
1. **Grammar & Structure**: Check for grammatical errors, improve sentence structure
2. **Accuracy Assessment**: Verify if the response contains factual information (no dummy data)
3. **Language Translation**: Translate to {language} if not already in that language
4. **Formatting**: Improve readability with proper formatting, bullet points, emojis where appropriate
5. **Completeness**: Ensure the response fully addresses the user's question

RESPONSE FORMAT:
Provide ONLY the improved response text. Do not include analysis explanations or metadata.

IMPORTANT RULES:
- NO dummy or fictional data
- Maintain all factual information from original response
- If original response has "N/A" or "No data found", keep those truthful statements
- Improve formatting and grammar only
- Add helpful context if city information is available
- Use appropriate emojis for environmental topics (🌊💧🏛️📊)

Improved Response:"""

        return context

    def _fallback_improvement(self, original_response: str, language: str) -> str:
        """Fallback improvement when Groq is unavailable"""

        # Basic improvements without external API
        improved = original_response

        # Add basic formatting
        if "Water Data Results:" in improved:
            improved = improved.replace("Water Data Results:", "🌊 **Water Quality Data:**")

        if "Environmental Policies" in improved:
            improved = improved.replace("Environmental Policies", "🏛️ **Environmental Policies**")

        # Add language note if not English
        if language != "en":
            language_names = {
                "es": "Spanish", "fr": "French", "de": "German",
                "it": "Italian", "pt": "Portuguese"
            }
            lang_name = language_names.get(language, language)
            improved += f"\n\n*Note: Response optimized for {lang_name} users*"

        return improved


class CityLookupHelper:
    """Helper class for city lookup from GraphDB"""

    @staticmethod
    def extract_station_id(text: str) -> Optional[str]:
        """Extract station ID from user text"""
        patterns = [
            r'\b(?:station|site|id)[\s_-]*:?\s*([A-Za-z0-9_-]+)',
            r'\b([A-Za-z]{2,4}\d{3,8})\b',  # Common station ID patterns
            r'\bID[\s:=]*([A-Za-z0-9_-]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def get_city_from_station(station_id: str) -> Optional[str]:
        """Get city name from station ID via GraphDB"""
        if not station_id:
            return None

        sparql = SPARQLWrapper(WATERBASE_SPARQL_ENDPOINT)
        sparql.setReturnFormat(JSON)
        sparql.setTimeout(5)  # Quick timeout for city lookup

        # Try multiple query patterns based on common EEA schemas
        queries = [
            f"""
            PREFIX EEA: <http://example.org/eea/>
            PREFIX wq: <http://example.org/water-quality/>
            PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>

            SELECT DISTINCT ?city ?location
            WHERE {{
              {{ 
                ?site EEA:monitoringSiteIdentifier "{station_id}" ;
                      EEA:city ?city .
              }} UNION {{
                ?site wq:siteId "{station_id}" ;
                      wq:location ?location .
                BIND(?location AS ?city)
              }} UNION {{
                <http://example.org/water-quality/site/{station_id}> wq:city ?city .
              }}
            }} LIMIT 1
            """,

            f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

            SELECT DISTINCT ?label
            WHERE {{
              ?site rdfs:label ?label .
              FILTER(CONTAINS(LCASE(STR(?site)), LCASE("{station_id}")))
              FILTER(REGEX(?label, "(Madrid|Barcelona|Valencia|Seville|Bilbao)", "i"))
            }} LIMIT 1
            """
        ]

        for query in queries:
            try:
                sparql.setQuery(query)
                results = sparql.query().convert()

                if results["results"]["bindings"]:
                    result = results["results"]["bindings"][0]
                    city = result.get("city", {}).get("value") or result.get("location", {}).get("value") or result.get(
                        "label", {}).get("value")
                    if city:
                        return city

            except Exception as e:
                logger.warning(f"City lookup query failed: {str(e)}")
                continue

        return None


class ActionAnalyzeResponse(Action):
    """Main action for analyzing and improving bot responses"""

    def name(self) -> Text:
        return "action_analyze_response"

    def __init__(self):
        self.analyzer = ResponseAnalyzer(GROQ_API_KEY, GROQ_MODEL)
        self.city_helper = CityLookupHelper()

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """Main execution method"""

        # Get the last bot response and user query
        last_bot_response = self._get_last_bot_response(tracker)
        user_query = tracker.latest_message.get("text", "")
        user_language = tracker.get_slot("language") or "en"

        if not last_bot_response:
            logger.warning("No bot response found to analyze")
            return []

        # Skip analysis for very short responses or error messages
        if len(last_bot_response) < 20 or "error" in last_bot_response.lower():
            return []

        # Get city context if station ID is mentioned
        station_id = self.city_helper.extract_station_id(user_query)
        city_context = None
        if station_id:
            city_context = self.city_helper.get_city_from_station(station_id)

        # Analyze and improve the response
        try:
            improved_response = self.analyzer.analyze_and_improve_response(
                original_response=last_bot_response,
                user_query=user_query,
                user_language=user_language,
                city_context=city_context
            )

            # Only send improved response if it's significantly different
            if self._is_improvement_significant(last_bot_response, improved_response):
                dispatcher.utter_message(text="📊 **Enhanced Response:**")
                dispatcher.utter_message(text=improved_response)

                # Add city context if available
                if city_context:
                    dispatcher.utter_message(text=f"📍 *Location Context: {city_context}*")

                return [SlotSet("analyzed", True)]

        except Exception as e:
            logger.error(f"Response analysis failed: {str(e)}")

        return []

    def _get_last_bot_response(self, tracker: Tracker) -> Optional[str]:
        """Extract the last bot response from tracker events"""

        # Look through recent events for bot responses
        events = list(reversed(tracker.events))

        for event in events:
            if event.get("event") == "bot":
                text = event.get("text", "")
                if text and len(text) > 10:  # Meaningful response
                    return text
            elif event.get("event") == "action" and event.get("name") == "utter_default":
                # Handle default responses
                return "I didn't understand your request. Could you please rephrase?"

        return None

    def _is_improvement_significant(self, original: str, improved: str) -> bool:
        """Check if the improved response is significantly different"""

        # Skip if responses are too similar
        if len(improved) < len(original) * 0.8:  # Avoid truncated responses
            return False

        # Check for meaningful improvements
        improvements = [
            "**" in improved and "**" not in original,  # Added formatting
            "🌊" in improved or "🏛️" in improved or "📊" in improved,  # Added emojis
            len(improved) > len(original) * 1.2,  # Significant expansion
            improved.count('\n') > original.count('\n'),  # Better structure
        ]

        return any(improvements)

    def _detect_language_from_text(self, text: str) -> str:
        """Simple language detection from user text"""
        text_lower = text.lower()

        # Spanish indicators
        spanish_words = ["que", "como", "donde", "cuando", "porque", "agua", "calidad", "madrid", "barcelona",
                         "política"]
        if any(word in text_lower for word in spanish_words):
            return "es"

        # French indicators
        french_words = ["que", "comment", "où", "quand", "pourquoi", "eau", "qualité", "politique"]
        if any(word in text_lower for word in french_words):
            return "fr"

        return "en"  # Default to English

# Removed ActionSetLanguage since no language rules exist