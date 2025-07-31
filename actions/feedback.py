from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from neo4j import GraphDatabase
import uuid
import datetime

# Reuse Neo4j settings from actions.py
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Anmol@123"  # Update if changed

def save_feedback_to_neo4j(feedback_data):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        session.run(
            """
            CREATE (f:Feedback {
                feedback_id: $feedback_id,
                user_query: $user_query,
                bot_response: $bot_response,
                feedback_type: $feedback_type,
                description: $description,
                timestamp: $timestamp
            })
            """,
            **feedback_data
        )
    driver.close()

class ActionStoreLastInteraction(Action):
    def name(self) -> Text:
        return "action_store_last_interaction"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Store last user query and bot response for feedback
        last_user = tracker.get_last_event_for("user")["text"] if tracker.events else ""
        last_bot = tracker.get_last_event_for("bot")["text"] if tracker.events else ""
        return [SlotSet("last_user_query", last_user), SlotSet("last_bot_response", last_bot)]

class ActionHandleThumbsUp(Action):
    def name(self) -> Text:
        return "action_handle_thumbs_up"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        query = tracker.get_slot("last_user_query") or tracker.latest_message.get("text", "")
        response = tracker.get_slot("last_bot_response") or ""
        feedback_id = str(uuid.uuid4())[:8].upper()
        try:
            save_feedback_to_neo4j({
                "feedback_id": feedback_id,
                "user_query": query,
                "bot_response": response,
                "feedback_type": "positive",
                "description": None,
                "timestamp": datetime.datetime.now().isoformat()
            })
            dispatcher.utter_message(text="👍 Thanks for the positive feedback! It helps us improve.")
        except Exception as e:
            dispatcher.utter_message(text="Error saving feedback. Please try again.")
        return []

class ActionHandleThumbsDown(Action):
    def name(self) -> Text:
        return "action_handle_thumbs_down"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="👎 Sorry to hear that. Please briefly describe what went wrong.")
        return [SlotSet("requested_slot", "feedback_description")]  # Prompt for description

class ActionSubmitThumbsDown(Action):
    def name(self) -> Text:
        return "action_submit_thumbs_down"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        query = tracker.get_slot("last_user_query") or tracker.latest_message.get("text", "")
        response = tracker.get_slot("last_bot_response") or ""
        description = tracker.get_slot("feedback_description") or tracker.latest_message.get("text", "")
        feedback_id = str(uuid.uuid4())[:8].upper()
        try:
            save_feedback_to_neo4j({
                "feedback_id": feedback_id,
                "user_query": query,
                "bot_response": response,
                "feedback_type": "negative",
                "description": description,
                "timestamp": datetime.datetime.now().isoformat()
            })
            dispatcher.utter_message(text=f"👎 Feedback noted: '{description}'. Thanks for helping us improve! Thanks for providing valuable feedback.")
        except Exception as e:
            dispatcher.utter_message(text="Error saving feedback. Please try again.")
        return [SlotSet("feedback_description", None), SlotSet("requested_slot", None)]
