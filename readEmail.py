import os
import msal
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from msal import PublicClientApplication
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from datetime import datetime, timedelta
import json
import google.auth
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


load_dotenv()
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
OPENAI_KEY = os.getenv("CHAT_KEY")

def fetch_emails(tenant_id, client_id, amount):
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scopes = ["Mail.Read"]
    app = PublicClientApplication(client_id, authority=authority)
    result = None
    accounts = app.get_accounts()

    # Attempt to acquire token silently
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        # If silent acquisition fails, fall back to interactive (Browser) method
    if not result:
        result = app.acquire_token_interactive(scopes)

    email_list = []
    if "access_token" in result:

        # Use the access token to call Microsoft Graph API
        headers = {"Authorization": f"Bearer {result['access_token']}"}
        url = f"https://graph.microsoft.com/v1.0/me/messages?$top={amount}&$select=subject,from,receivedDateTime,body"
        response = requests.get(url, headers=headers)
        emails = response.json()
        for msg in emails.get("value", []):
            sender = "From: " + str(msg["from"]["emailAddress"]["address"])
            subject = "Subject: " + str(msg["subject"])
            html_body = msg["body"]["content"]
            soup = BeautifulSoup(html_body, "html.parser")
            plain_text = soup.get_text()
            combined_text = sender + "\n" + subject + "\n" + plain_text
            email_list.append(combined_text)
    else:
        print("Login error:", result.get("error_description"))
    return email_list


def parse_email_content(email_content):

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENAI_KEY)

    with open("prompt.txt", "r", encoding="utf-8") as f:
        guidlines = f.read()
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": guidlines},
            {"role": "user", "content": email_content},
        ], 
        response_format={ "type": "json_object" },

        max_tokens=500,
        temperature=0.2,
    )
    raw_output = response.choices[0].message.content
    try:
        parsed_json = json.loads(raw_output)
    except json.JSONDecodeError:
        print("⚠️ Model returned invalid JSON. Raw output was:\n", raw_output)
        with open("last_response.json", "w", encoding="utf-8") as f:
            f.write(raw_output)

        # Try to recover by trimming around first/last braces
        try:
            start = raw_output.find("{")     
            end = raw_output.rfind("}") + 1
            cleaned = raw_output[start:end]
            parsed_json = json.loads(cleaned)
        except Exception:
            # If still broken, return empty structure instead of crashing
            parsed_json = {"events": []}

    return parsed_json


def get_calendar_service():

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

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


def create_event(event_data, service):

    start_time = event_data.get("start_time", "09:00")
    end_time = event_data.get("end_time", "10:00")
    start_date = event_data.get("start_date", datetime.now().strftime("%Y-%m-%d"))
    end_date = event_data.get("end_date", start_date)
    location = event_data.get("location", "")
    description = event_data.get("description", event_data.get("title", ""))
    title = event_data.get("title", "Untitled Event")

    # Parse dates and times
    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
    end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")

    #Format as RFC3339
    start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    event = {
        "summary": event_data.get("title", "Untitled Event"),
        "description": event_data.get("description", ""),
        "location": event_data.get("location", ""),
        "start": {"dateTime": start_str, "timeZone": "America/Chicago"},
        "end": {"dateTime": end_str, "timeZone": "America/Chicago"},
    }

    start_date = normalize_date(event_data.get("start_date"))
    end_date = normalize_date(event_data.get("end_date", start_date))

    created_event = service.events().insert(calendarId="primary", body=event).execute()
    print("Event created:", created_event.get("htmlLink"))

if __name__ == "__main__":
    TENANT_ID = os.getenv("TENANT_ID")
    CLIENT_ID = os.getenv("CLIENT_ID")

    amount = input("How many emails do you want to fetch? (1-25): ")
    if amount.isdigit():
        amount = int(amount) if int(amount) > 0 and int(amount) <= 25 else 5
    emails = fetch_emails(TENANT_ID, CLIENT_ID, amount)

    event_jsons = []
    for email in emails:
        event_jsons.append(parse_email_content(email))

        service = get_calendar_service()
    for event in event_jsons:
        create_event(event, service)