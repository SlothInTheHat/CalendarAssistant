import os
import msal
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from msal import PublicClientApplication
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import json

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


if __name__ == "__main__":
    TENANT_ID = os.getenv("TENANT_ID")
    CLIENT_ID = os.getenv("CLIENT_ID")

    amount = input("How many emails do you want to fetch? (1-25): ")
    if amount.isdigit():
        amount = int(amount) if int(amount) > 0 and int(amount) <= 25 else 5
    emails = fetch_emails(TENANT_ID, CLIENT_ID, amount)

    for email in emails:
        print(parse_email_content(email))