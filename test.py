# test.py
# Run this script to verify all project components are connected and functional.

from neo4j import GraphDatabase
from SPARQLWrapper import SPARQLWrapper, JSON
from groq import Groq  # Explicit import to fix NameError
import datetime

# Configurations (from your setup)
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Anmol@123"  # Update if different

WATERBASE_SPARQL_ENDPOINT = "http://localhost:7200/repositories/waterbase"
POLICY_SPARQL_ENDPOINT = "http://localhost:7200/repositories/policy"

GROQ_API_KEY = 
GROQ_MODEL = "deepseek-r1-distill-llama-70b"  # Fallback: "llama3-70b-8192"

def check_neo4j_connection():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            result = session.run("RETURN 1 AS connected").single()
        driver.close()
        return "✅ Neo4j is up and connected." if result and result["connected"] == 1 else "❌ Neo4j connection failed."
    except Exception as e:
        return f"❌ Neo4j error: {str(e)}"

def check_neo4j_data_storage():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            incident_count = session.run("MATCH (i:IncidentReport) RETURN count(i) AS count").single()["count"]
            feedback_count = session.run("MATCH (f:Feedback) RETURN count(f) AS count").single()["count"]
        driver.close()
        return f"✅ Neo4j data storage: {incident_count} IncidentReports, {feedback_count} Feedbacks stored." if incident_count >= 0 else "❌ No data nodes found in Neo4j."
    except Exception as e:
        return f"❌ Neo4j data check error: {str(e)}"

def check_sparql_endpoint(endpoint, repo_name):
    try:
        sparql = SPARQLWrapper(endpoint)
        sparql.setQuery("SELECT * WHERE {?s ?p ?o} LIMIT 1")
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        if "results" in results and results["results"]["bindings"]:
            return f"✅ {repo_name} GraphDB repo connected and responsive."
        else:
            return f"❌ {repo_name} GraphDB repo connected but no data returned."
    except Exception as e:
        return f"❌ {repo_name} GraphDB error: {str(e)}"

def check_data_fetch_from_repo(endpoint, repo_name):
    try:
        sparql = SPARQLWrapper(endpoint)
        sparql.setReturnFormat(JSON)

        if repo_name == "Waterbase":
            # Corrected query based on sample.ttl: Fetch observation ID and observed property
            query = """
PREFIX sosa: <http://www.w3.org/ns/sosa/>
SELECT DISTINCT ?site
WHERE {
  ?obs sosa:hasFeatureOfInterest ?site .
  FILTER(CONTAINS(STR(?site), "ES"))
}
ORDER BY ?site
LIMIT 1
            """
        elif repo_name == "Policy":
            # Your working Query 6: Fetch regulations for Madrid (can be updated for other cities)
            query = """
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX esp: <http://spain.environmental.org/>

            SELECT ?cityName ?regulationType ?regulationName ?effectiveDate ?regulationText ?complianceReq
            WHERE {
              ?city rdfs:label ?cityName ;
                    esp:hasRegulation ?regulation .
              ?regulation a ?regulationType ;
                          rdfs:label ?regulationName ;
                          esp:effectiveDate ?effectiveDate ;
                          esp:regulationText ?regulationText ;
                          esp:complianceRequirement ?complianceReq .
              FILTER(?cityName = "Madrid")
            }
            ORDER BY ?effectiveDate
            LIMIT 1
            """
        else:
            return f"❌ Unknown repository: {repo_name}"

        print(f"Debug: Running query for {repo_name}:\n{query}")  # For manual copy-paste testing

        sparql.setQuery(query)
        results = sparql.query().convert()

        if results["results"]["bindings"]:
            sample_data = results["results"]["bindings"][0]
            return f"✅ Data fetched from {repo_name}: Sample = {sample_data} (response from repo confirmed)."
        else:
            return f"❌ No data fetched from {repo_name} (query returned empty). Test in Workbench; check TTL import and namespaces."
    except Exception as e:
        return f"❌ Data fetch error from {repo_name}: {str(e)}"

def check_groq_api():
    try:
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": "Test connection"}],
            temperature=0.6,
            max_tokens=10,
            top_p=0.95,
            stream=False
        )
        if completion.choices[0].message.content:
            return "✅ Groq API connected and responsive."
        else:
            return "❌ Groq API responded but empty content."
    except Exception as e:
        return f"❌ Groq API error: {str(e)}"

# Run all checks
print(f"--- Project Setup Verification Report ({datetime.datetime.now()}) ---")
print(check_neo4j_connection())
print(check_neo4j_data_storage())
print(check_sparql_endpoint(WATERBASE_SPARQL_ENDPOINT, "Waterbase"))
print(check_data_fetch_from_repo(WATERBASE_SPARQL_ENDPOINT, "Waterbase"))
print(check_sparql_endpoint(POLICY_SPARQL_ENDPOINT, "Policy"))
print(check_data_fetch_from_repo(POLICY_SPARQL_ENDPOINT, "Policy"))
print(check_groq_api())
print("--- End of Report ---")
print("If all checks are ✅, the project is fully connected and ready. Fix ❌ issues before running.")
