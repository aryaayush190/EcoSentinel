# actions.py
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.events import SlotSet, EventType, AllSlotsReset, UserUtteranceReverted, ActionExecuted
import uuid
from neo4j import GraphDatabase
import re

# Neo4j connection settings (update with your credentials)
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Anmol@123"  # Change this to your actual password


def save_report_to_neo4j(report_data):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        session.run(
            """
            CREATE (r:IncidentReport {
                report_id: $report_id,
                user_name: $user_name,
                incident_type: $incident_type,
                has_proof: $has_proof,
                address: $address,
                contact_number: $contact_number,
                incident_description: $incident_description,
                created_at: datetime()
            })
            """,
            **report_data
        )
    driver.close()


class ValidateEnvironmentIncidentForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_environment_incident_form"

    def _is_exit_command(self, text: str) -> bool:
        """Check if the user input is an exit command"""
        if not isinstance(text, str):
            return False

        exit_keywords = [
            'exit', 'quit', 'cancel', 'stop', 'abort', 'end', 'terminate',
            'exit form', 'quit form', 'cancel form', 'stop form',
            'i want to exit', 'i want to quit', 'i want to cancel',
            'get me out', 'take me out', 'leave form', 'escape',
            'nevermind', 'forget it', 'no thanks', 'not now'
        ]

        user_text = text.strip().lower()

        # Exact match check
        if user_text in exit_keywords:
            return True

        # Partial match check for longer phrases
        for keyword in exit_keywords:
            if keyword in user_text and len(user_text) <= len(keyword) + 10:
                return True

        return False

    def _check_exit_intent_or_text(self, tracker: Tracker) -> bool:
        """Check if user wants to exit based on intent or text content"""
        # Check intent
        latest_intent = tracker.latest_message.get("intent", {}).get("name")
        if latest_intent == "exit_form":
            return True

        # Check text content for exit keywords
        user_text = tracker.latest_message.get("text", "")
        return self._is_exit_command(user_text)

    def _exit_form(self, dispatcher: CollectingDispatcher):
        """Helper method to exit form"""
        dispatcher.utter_message(
            text="❌ Form cancelled. Your information was not saved. How else can I help you?"
        )
        return {
            "requested_slot": None,
            "user_name": None,
            "incident_type": None,
            "contact_number": None,
            "incident_description": None,
            "address": None,
            "has_proof": None
        }

    def _extract_entity_value(self, tracker: Tracker, entity_name: str) -> Optional[str]:
        """Extract entity value from the latest message"""
        entities = tracker.latest_message.get("entities", [])
        for entity in entities:
            if entity.get("entity") == entity_name:
                return entity.get("value")
        return None

    async def required_slots(
            self,
            slots_mapped_in_domain: List[Text],
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Text]:
        """Define the required slots for the form"""
        return ["incident_type", "user_name", "contact_number", "incident_description", "address", "has_proof"]

    def extract_incident_type(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        """Extract incident_type slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Try entity first
        entity_value = self._extract_entity_value(tracker, "incident_type")
        if entity_value:
            return {"incident_type": entity_value}

        # Then try text
        text = tracker.latest_message.get("text", "").strip()
        if text and not self._is_exit_command(text):
            return {"incident_type": text}

        return {}

    def extract_user_name(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        """Extract user_name slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Try entity first
        entity_value = self._extract_entity_value(tracker, "user_name")
        if entity_value:
            return {"user_name": entity_value}

        # Then try text
        text = tracker.latest_message.get("text", "").strip()
        if text and not self._is_exit_command(text):
            return {"user_name": text}

        return {}

    def extract_contact_number(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        """Extract contact_number slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Try entity first
        entity_value = self._extract_entity_value(tracker, "contact_number")
        if entity_value:
            return {"contact_number": entity_value}

        # Then try text
        text = tracker.latest_message.get("text", "").strip()
        if text and not self._is_exit_command(text):
            return {"contact_number": text}

        return {}

    def extract_incident_description(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        """Extract incident_description slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Try entity first
        entity_value = self._extract_entity_value(tracker, "incident_description")
        if entity_value:
            return {"incident_description": entity_value}

        # Then try text
        text = tracker.latest_message.get("text", "").strip()
        if text and not self._is_exit_command(text):
            return {"incident_description": text}

        return {}

    def extract_address(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        """Extract address slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Try entity first
        entity_value = self._extract_entity_value(tracker, "address")
        if entity_value:
            return {"address": entity_value}

        # Then try text
        text = tracker.latest_message.get("text", "").strip()
        if text and not self._is_exit_command(text):
            return {"address": text}

        return {}

    def extract_has_proof(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        """Extract has_proof slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Try entity first
        entity_value = self._extract_entity_value(tracker, "has_proof")
        if entity_value:
            return {"has_proof": entity_value}

        # Then try text
        text = tracker.latest_message.get("text", "").strip()
        if text and not self._is_exit_command(text):
            return {"has_proof": text}

        return {}

    def validate_incident_type(
            self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> Dict[Text, Any]:
        """Validate incident_type slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Use extracted value or fallback to text
        value = slot_value if slot_value else tracker.latest_message.get("text", "").strip()

        if not value or len(str(value).strip()) < 2:
            dispatcher.utter_message(text="Please provide a valid incident type (at least 2 characters).")
            return {"incident_type": None}

        return {"incident_type": str(value).strip()}

    def validate_user_name(
            self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> Dict[Text, Any]:
        """Validate user_name slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Use extracted value or fallback to text
        value = slot_value if slot_value else tracker.latest_message.get("text", "").strip()

        if not value or len(str(value).strip()) < 2:
            dispatcher.utter_message(text="Please enter a valid name (at least 2 characters).")
            return {"user_name": None}

        return {"user_name": str(value).strip()}

    def validate_contact_number(
            self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> Dict[Text, Any]:
        """Validate contact_number slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Use extracted value or fallback to text
        value = slot_value if slot_value else tracker.latest_message.get("text", "").strip()

        if not value:
            dispatcher.utter_message(text="Please enter a valid contact number.")
            return {"contact_number": None}

        # Clean the number (remove spaces, hyphens, etc.)
        cleaned_number = re.sub(r'[^\d]', '', str(value))

        if not (8 <= len(cleaned_number) <= 15):
            dispatcher.utter_message(text="Please enter a valid contact number (8-15 digits).")
            return {"contact_number": None}

        return {"contact_number": cleaned_number}

    def validate_incident_description(
            self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> Dict[Text, Any]:
        """Validate incident_description slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Use extracted value or fallback to text
        value = slot_value if slot_value else tracker.latest_message.get("text", "").strip()

        if not value or len(str(value).strip()) < 6:
            dispatcher.utter_message(text="Please provide a detailed description (at least 6 characters).")
            return {"incident_description": None}

        return {"incident_description": str(value).strip()}

    def validate_address(
            self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> Dict[Text, Any]:
        """Validate address slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Use extracted value or fallback to text
        value = slot_value if slot_value else tracker.latest_message.get("text", "").strip()

        if not value or len(str(value).strip()) < 6:
            dispatcher.utter_message(text="Please enter a complete address (at least 6 characters).")
            return {"address": None}

        return {"address": str(value).strip()}

    def validate_has_proof(
            self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> Dict[Text, Any]:
        """Validate has_proof slot"""
        if self._check_exit_intent_or_text(tracker):
            return self._exit_form(dispatcher)

        # Use extracted value or fallback to text
        value = slot_value if slot_value else tracker.latest_message.get("text", "").strip()

        if isinstance(value, bool):
            return {"has_proof": value}

        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ["yes", "y", "true", "1", "yeah", "yep"]:
                return {"has_proof": True}
            elif value_lower in ["no", "n", "false", "0", "nope", "nah"]:
                return {"has_proof": False}

        dispatcher.utter_message(text="Please reply with 'yes' or 'no' to indicate if you have proof/evidence.")
        return {"has_proof": None}


class ActionSubmitEnvironmentIncident(Action):
    def name(self) -> Text:
        return "action_submit_environment_incident"

    def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        # Get all slot values
        user_name = tracker.get_slot("user_name")
        incident_type = tracker.get_slot("incident_type")
        has_proof = tracker.get_slot("has_proof")
        address = tracker.get_slot("address")
        contact_number = tracker.get_slot("contact_number")
        incident_description = tracker.get_slot("incident_description")

        # Validate that all required slots are filled
        required_slots = [user_name, incident_type, address, contact_number, incident_description]
        if not all(slot is not None for slot in required_slots):
            dispatcher.utter_message(
                text="❌ Error: Some required information is missing. Please try again."
            )
            return [AllSlotsReset()]

        # Generate unique report ID
        report_id = str(uuid.uuid4())[:8].upper()

        try:
            # Save to Neo4j
            report_data = {
                "report_id": report_id,
                "user_name": user_name,
                "incident_type": incident_type,
                "has_proof": has_proof if has_proof is not None else False,
                "address": address,
                "contact_number": contact_number,
                "incident_description": incident_description,
            }
            save_report_to_neo4j(report_data)

            # Success message with report summary
            dispatcher.utter_message(
                text=f"✅ **Thank you! Your incident report has been successfully submitted.**\n\n"
                     f"📋 **Your Report ID: {report_id}**\n"
                     f"*Please save this ID for your records.*"
            )

            dispatcher.utter_message(
                text=(
                    f"📊 **Report Summary:**\n"
                    f"👤 **Name:** {user_name}\n"
                    f"📍 **Address:** {address}\n"
                    f"📞 **Contact:** {contact_number}\n"
                    f"📌 **Incident Type:** {incident_type}\n"
                    f"📷 **Proof Available:** {'Yes' if has_proof else 'No'}\n"
                    f"📝 **Description:** {incident_description}"
                )
            )

            # Evidence upload instruction
            if has_proof:
                dispatcher.utter_message(
                    text=(
                        f"📎 **Upload Evidence:**\n"
                        f"Since you mentioned having proof/evidence, please visit our evidence portal "
                        f"and use your Report ID **{report_id}** to upload any photos, videos, or documents.\n\n"
                        f"🌐 **Portal Link:** [Evidence Upload Portal](https://your-portal-url.com/upload)\n"
                        f"🔑 **Your Report ID:** {report_id}"
                    )
                )

            dispatcher.utter_message(
                text="✨ Your report will be reviewed by our team within 24-48 hours. "
                     "Thank you for helping protect our environment! 🌱"
            )

        except Exception as e:
            dispatcher.utter_message(
                text="❌ Sorry, there was an error saving your report. Please try again later "
                     "or contact our support team."
            )
            print(f"Error saving to Neo4j: {e}")

        return [AllSlotsReset()]


class ActionActivateIncidentForm(Action):
    """Action to activate the incident reporting form"""

    def name(self) -> Text:
        return "action_activate_incident_form"

    def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        dispatcher.utter_message(
            text="🌍 **Environmental Incident Report Form**\n\n"
                 "I'll help you report an environmental incident. Please answer the following questions:\n"
                 "*(You can type 'exit' at any time to cancel)*"
        )
        return []


class ActionExitForm(Action):
    """Custom action to handle form exit"""

    def name(self) -> Text:
        return "action_exit_form"

    def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        dispatcher.utter_message(
            text="❌ Form cancelled. Your information was not saved. How else can I help you?"
        )
        return [AllSlotsReset(), ActionExecuted("action_listen")]


class ActionDeactivateLoop(Action):
    def name(self) -> Text:
        return "action_deactivate_loop"

    def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        dispatcher.utter_message(
            text="❌ Form cancelled. Your information was not saved. How else can I help you?"
        )
        return [AllSlotsReset()]