import base64
import hashlib
import os

import requests
from dotenv import load_dotenv
from flask import Flask, redirect, request, url_for

app = Flask(__name__)
load_dotenv()

# Replace with your API key and redirect URI
CLIENT_ID = os.environ.get("ETSY_CLIENT_ID")
REDIRECT_URI = os.environ.get("ETSY_REDIRECT_URI")
SCOPES = "listings_r shops_r"
STATE = "YOUR_STATE_STRING"


# Generate code verifier and code challenge
def generate_code_verifier_challenge():
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=")
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier).digest()
    ).rstrip(b"=")
    return code_verifier.decode(), code_challenge.decode()


@app.route("/login")
def login():
    code_verifier, code_challenge = generate_code_verifier_challenge()
    # Store these for later
    app.secret_code_verifier = code_verifier
    auth_url = (
        "https://www.etsy.com/oauth/connect"
        f"?response_type=code&redirect_uri={REDIRECT_URI}"
        f"&scope={SCOPES}&client_id={CLIENT_ID}&state={STATE}"
        f"&code_challenge={code_challenge}&code_challenge_method=S256"
    )
    return redirect(auth_url)


@app.route("/oauth/redirect")
def oauth_redirect():
    code = request.args.get("code")
    if request.args.get("state") != STATE:
        return "State does not match!", 400

    # Exchange code for access token
    token_url = "https://api.etsy.com/v3/public/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "code_verifier": app.secret_code_verifier,
    }

    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]
        print(f"Access Token: {access_token}")
        print(f"Refresh Token: {refresh_token}")
        return "Access Token Obtained!", 200
    else:
        return "Failed to obtain access token.", 400


if __name__ == "__main__":
    app.run(debug=True)
