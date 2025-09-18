import os
import msal
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from msal import PublicClientApplication
import requests
from bs4 import BeautifulSoup

load_dotenv()
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

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


if __name__ == "__main__":
    TENANT_ID = os.getenv("TENANT_ID")
    CLIENT_ID = os.getenv("CLIENT_ID")

    amount = input("How many emails do you want to fetch? (1-25): ")
    if amount.isdigit():
        amount = int(amount) if int(amount) > 0 and int(amount) <= 25 else 5
    emails = fetch_emails(TENANT_ID, CLIENT_ID, amount)

    for email in emails:
        print(email)