# FishOps Intelligence

FishOps Intelligence is a prospecting and relationship-development workspace
for Kenya's aquaculture value chain. It helps authorized users organize
business information, understand the prospect pipeline, and keep track of
which records need review.

## What it offers

- A searchable directory of aquaculture-related businesses.
- An overview of prospects by business type, location, and pipeline stage.
- CSV preview and explicit staging for user-provided business registers.
- Public BusinessList fish-merchant listings with visible contact numbers.
- A review queue to correct candidate details, approve records, or link them
  to existing businesses.
- Editable business/contact verification, pipeline progression, and manual
  outreach history with dated next steps.

## Data quality and responsible use

Information may be incomplete, outdated, or awaiting review. A record should
not be treated as verified unless it is explicitly marked as such. Confirm
contact details and suitability before relying on them, and respect applicable
privacy requirements, source terms, and requests not to be contacted.
Imports and collection only stage unverified records. They never send messages
or mark a business/contact verified automatically. The BusinessList adapter
reads the public fish-merchants category page and obeys robots.txt; it does not
access paid Data Hub exports or scrape individual profiles. RentechDigital's
full directory export is paid; use only data you are authorized to provide.

## Import, review, and follow up

1. Open **Data Collection** and upload a CSV. Common column names such as
   `name`, `phone`, `email`, `url`, `lat`, `lng`, `address`, `city`, and
   `state` are supported. Inspect the preview before selecting **Stage**.
2. To collect visible fish-merchant listings, select **Fetch BusinessList
   public listings**, review the results, then explicitly stage them.
3. Use **Review Queue** to correct details and approve, link, mark duplicate,
   or reject the source record. This review decision is not verification.
4. In **Directory**, record a verification method before marking a business or
   contact verified. Progression beyond **Needs Verification** is blocked until
   the business is verified.
5. Add contact details and log calls, emails, meetings, outcomes, and dated
   next steps manually. The app does not contact businesses automatically.

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
