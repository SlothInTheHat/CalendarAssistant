from flask import Flask, jsonify
import requests
import json
import os
from dotenv import load_dotenv
import datetime
from datetime import datetime as dt
from bs4 import BeautifulSoup
import subprocess
import time
import google.auth.transport.requests
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from msal import PublicClientApplication
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Store events in a global variable for demo purposes
frontend_events = []

@app.route('/events')
def get_events():
    return jsonify(frontend_events)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# ---------------------------
# Step 0: Ensure Ollama is running
# ---------------------------
def start_ollama():
    """Start Ollama server if it's not already running."""
    try:
        # ping Ollama API
        requests.get("http://localhost:11434/api/tags", timeout=2)
        print("✅ Ollama server already running")
        return
    except requests.exceptions.RequestException:
        print("⚡ Starting Ollama server...")

    subprocess.Popen(
        ["ollama", "serve"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,  # Windows: run in background
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # wait until it responds
    for i in range(10):
        try:
            requests.get("http://localhost:11434/api/tags", timeout=2)
            print("✅ Ollama server started")
            return
        except requests.exceptions.RequestException:
            time.sleep(1)

    raise RuntimeError("❌ Failed to start Ollama server. Try running `ollama serve` manually.")

# ---------------------------
# Step 1: Authenticate user with OAuth
# ---------------------------
def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

# ---------------------------
# Step 2: Extract events with LLaMA
# ---------------------------
def extract_events_from_text(text: str):
    start_ollama()
    url = "http://localhost:11434/api/generate"

    prompt = f"""
    You are an assistant that extracts calendar events from text.
    Input:
    {text}

    Output:
    A JSON array of google calendar events, where each event has:
    - title
    - start_date (YYYY-MM-DD)
    - end_date (optional, YYYY-MM-DD)
    - start_time (optional, HH:MM)
    - end_time (optional, HH:MM)
    - location
    - description
    The location should be able to be filled into the google calendar location field as a valid location
    The description should include the room number if provided or any other important location information.
    The description should also include any relevant links in the text
    Do not include any extra text beyond the JSON in your response.
    """

    payload = {"model": "llama3", "prompt": prompt}
    response = requests.post(url, json=payload, stream=True)

    full_output = ""
    for line in response.iter_lines():
        if line:
            try:
                data = json.loads(line.decode("utf-8"))
                full_output += data.get("response", "")
            except json.JSONDecodeError:
                continue

    try:
        json_start = full_output.find("[")
        json_end = full_output.rfind("]") + 1
        if json_start == -1 or json_end == -1:
            raise ValueError("No JSON array found in model output")

        cleaned_output = full_output[json_start:json_end]
        events = json.loads(cleaned_output)

        if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
            raise ValueError("Parsed JSON is not a list of events")

        return events

    except Exception as e:
        print("⚠️ Failed to parse JSON:", e)
        print("Raw model output:\n", full_output)
        return []

# ---------------------------
# Step 3: Normalize dates
# ---------------------------
def normalize_date(date_str):
    """Normalize a date string into YYYY-MM-DD format."""
    if not date_str:
        return dt.today().strftime("%Y-%m-%d")

    try:
        # Case 1: Already YYYY-MM-DD
        parts = date_str.split("-")
        if len(parts) == 3:
            return date_str

        # Case 2: MM/DD/YYYY
        parsed = dt.strptime(date_str, "%m/%d/%Y")
        return parsed.strftime("%Y-%m-%d")

    except Exception:
        # Fallback to today if parsing fails
        return dt.today().strftime("%Y-%m-%d")

# ---------------------------
# Step 4: Create Google Calendar events
# ---------------------------
from datetime import datetime, timedelta

def create_event(event_data, service):
    start_date = normalize_date(event_data.get("start_date"))
    end_date = normalize_date(event_data.get("end_date", start_date))

    def parse_time(date_str, time_str):
        # Try 24-hour first
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            pass
        # Try 12-hour with am/pm
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        except ValueError:
            pass
        # Fallback to 09:00
        return datetime.strptime(f"{date_str} 09:00", "%Y-%m-%d %H:%M")

    start_time_str = event_data.get("start_time", "09:00")
    start_datetime_obj = parse_time(start_date, start_time_str)

    if "end_time" in event_data and event_data["end_time"]:
        end_time_str = event_data["end_time"]
        end_datetime_obj = parse_time(end_date, end_time_str)

        # If end is before start (e.g. start 23:30, end 00:15) → shift to next day
        if end_datetime_obj <= start_datetime_obj:
            end_datetime_obj += timedelta(days=1)
    else:
        end_datetime_obj = start_datetime_obj + timedelta(hours=1)

    # Format as RFC3339
    start_datetime = start_datetime_obj.strftime("%Y-%m-%dT%H:%M:%S")
    end_datetime = end_datetime_obj.strftime("%Y-%m-%dT%H:%M:%S")

    event = {
        "summary": event_data.get("title", "Untitled Event"),
        "description": event_data.get("description", event_data.get("title","")),
        "location": event_data.get("location", ""),
        "start": {"dateTime": start_datetime, "timeZone": "America/Chicago"},
        "end": {"dateTime": end_datetime, "timeZone": "America/Chicago"},
    }

    created_event = service.events().insert(calendarId="primary", body=event).execute()
    print("✅ Event created:", created_event.get("htmlLink"))

def fetch_emails(tenant, client, authority):
    SCOPES = ["Mail.Read"]
    app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        result = app.acquire_token_interactive(SCOPES)

    if "access_token" in result:
        headers = {"Authorization": f"Bearer {result['access_token']}"}
        url = "https://graph.microsoft.com/v1.0/me/messages?$top=5&$select=subject,from,receivedDateTime,body"

        response = requests.get(url, headers=headers)
        emails = response.json()
        email_list = []
        for msg in emails.get("value", []):
            sender = "From: " + str(msg["from"]["emailAddress"]["address"])
            subject = "Subject: " + str(msg["subject"])
            print(subject)
            html_body = msg["body"]["content"]
            soup = BeautifulSoup(html_body, "html.parser")
            plain_text = soup.get_text()
            combined_text = sender + "\n" + subject + "\n" + plain_text
            email_list.append(combined_text)
            print(combined_text)
    else:
        print("Login error:", result.get("error_description"))

    return email_list


# ---------------------------
# Main program loop
# ---------------------------
if __name__ == "__main__":

# Load environment variables from .env
    load_dotenv()

    TENANT_ID = os.getenv("TENANT_ID")
    CLIENT_ID = os.getenv("CLIENT_ID")
    AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
    email_list = fetch_emails(TENANT_ID, CLIENT_ID, AUTHORITY)

    service = get_calendar_service()

    for email in email_list:
        events = extract_events_from_text(email)

        if events:
            print("\n✅ Extracted Events:")
            for i, event in enumerate(events, 1):
                print(f"{i}. {event}")
                # create_event(event, service)
            frontend_events.extend(events)  # <-- Add this line
        else:
            print("⚠️ No valid events found.")

    # while True:
    #     print("\n📩 Paste your email or text below (Enter + Ctrl+D/Ctrl+Z when done):")
    #     user_input = ""
    #     try:
    #         while True:
    #             line = input()
    #             user_input += line + "\n"
    #     except EOFError:
    #         pass

    #     if not user_input.strip():
    #         print("🚪 Exiting program (no input).")
    #         break

    #     events = extract_events_from_text(user_input)

    #     if events:
    #         print("\n✅ Extracted Events:")
    #         for i, event in enumerate(events, 1):
    #             print(f"{i}. {event}")
    #             create_event(event, service)
    #     else:
    #         print("⚠️ No valid events found.")

    #     again = input("\n➕ Add more events? (y/n): ").strip().lower()
    #     if again != "y":
    #         print("👋 Goodbye!")
    #         break

    app.run(port=5000)