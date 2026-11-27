# FishOps Intelligence

FishOps Intelligence is a prospecting and relationship-development workspace
for Kenya's aquaculture value chain. It helps authorized users organize
business information, understand the prospect pipeline, and keep track of
which records need review.

## What it offers

- A searchable directory of aquaculture-related businesses.
- An overview of prospects by business type, location, and pipeline stage.
- A review queue for candidate records gathered from public sources.
- Verification status to help distinguish reviewed information from
  unconfirmed leads.

## Data quality and responsible use

Information may be incomplete, outdated, or awaiting review. A record should
not be treated as verified unless it is explicitly marked as such. Confirm
contact details and suitability before relying on them, and respect applicable
privacy requirements, source terms, and requests not to be contacted.

## Access

The application uses Auth0 through Streamlit's built-in OpenID Connect login
and permits only the administrator email addresses configured in Streamlit
secrets. Before enabling the new login, ensure those administrators have
accounts in the Auth0 tenant and verified email addresses. Supabase passwords
are not migrated; users must set up their Auth0 credentials separately.

For local development, add the `[auth]` and `[auth.auth0]` sections from
`.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`. Copy the
`AUTH0_CLIENT_SECRET` value from your local `.env` into the `client_secret`
setting, and generate a unique `cookie_secret` (for example, with
`python -c "import secrets; print(secrets.token_hex(32))"`). Never commit
`.streamlit/secrets.toml`.

For the deployed app, configure the same sections in the Streamlit app's
secrets settings, changing `redirect_uri` to the production callback below.
The Auth0 application allows the local callback
`http://localhost:8501/oauth2callback` and the production callback
`https://fishops-intelligence-4ofjpgfc6zyhsxxuafvqvz.streamlit.app/oauth2callback`.
Visit the [FishOps Intelligence app](https://fishops-intelligence-4ofjpgfc6zyhsxxuafvqvz.streamlit.app/)
to sign in.
