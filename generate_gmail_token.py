"""Generate new Gmail OAuth token."""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

flow = InstalledAppFlow.from_client_secrets_file(
    'client_secret_34679635926-vutum35o4jtdrlc6t1064q6mmm3thujb.apps.googleusercontent.com.json',
    SCOPES
)
creds = flow.run_local_server(port=51723, open_browser=True)

token_data = {
    'token': creds.token,
    'refresh_token': creds.refresh_token,
    'token_uri': creds.token_uri,
    'client_id': creds.client_id,
    'client_secret': creds.client_secret,
    'scopes': list(creds.scopes)
}

with open('gmail_token.json', 'w') as f:
    json.dump(token_data, f, indent=2)

print('\nDONE! gmail_token.json created successfully!')
print(f'Refresh token: {creds.refresh_token[:20]}...')
