# Google OAuth Setup Guide

This guide will walk you through setting up Google OAuth authentication for Sterna.

## Prerequisites

- Google account
- Access to Google Cloud Console
- Project running locally

## Step 1: Google Cloud Console Setup

1. **Go to Google Cloud Console**
   - Navigate to [https://console.cloud.google.com/](https://console.cloud.google.com/)
   - Sign in with your Google account

2. **Create or Select a Project**
   - Click on the project dropdown in the top bar
   - Either select an existing project or create a new one
   - Name it something like "Sterna Development"

3. **Enable Required APIs**
   - In the left sidebar, go to "APIs & Services" > "Library"
   - Search for "Google+ API" and enable it
   - This API is required for OAuth authentication

4. **Create OAuth 2.0 Credentials**
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - If prompted, configure the OAuth consent screen first:
     - Choose "External" for user type (unless you have a Google Workspace)
     - Fill in the required fields:
       - App name: Sterna
       - User support email: Your email
       - Developer contact: Your email
     - Add scopes: email, profile
     - Save and continue

5. **Configure OAuth Client**
   - Application type: **Web application**
   - Name: "Sterna Development"
   - Authorized JavaScript origins:
     ```
     http://localhost:5173
     http://127.0.0.1:5173
     ```
   - Authorized redirect URIs (not required for implicit flow, but good to have):
     ```
     http://localhost:5173
     http://localhost:8000/api/auth/google/callback
     ```
   - Click "Create"

6. **Save Your Credentials**
   - After creation, you'll see your credentials:
     - **Client ID**: Looks like `xxxxx.apps.googleusercontent.com`
     - **Client Secret**: Keep this secure
   - Download the JSON file for backup

## Step 2: Configure Backend

1. **Update Backend .env File**
   ```bash
   # In core/.env
   GOOGLE_OAUTH_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret-here
   ```

2. **Run Migrations** (for Django sites framework)
   ```bash
   docker-compose exec web python manage.py migrate
   ```

3. **Create Site Object** (one-time setup)
   ```bash
   docker-compose exec web python manage.py shell
   ```
   Then in the Python shell:
   ```python
   from django.contrib.sites.models import Site
   Site.objects.update_or_create(
       id=1,
       defaults={'domain': 'localhost:8000', 'name': 'Sterna Development'}
   )
   exit()
   ```

## Step 3: Configure Frontend

1. **Update Frontend .env.development File**
   ```bash
   # In core/frontend/.env.development
   VITE_GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
   ```
   Note: Use the same Client ID as the backend, but frontend doesn't need the secret.

2. **Install Frontend Dependencies**
   ```bash
   docker-compose exec frontend npm install
   ```

## Step 4: Restart Services

```bash
# Rebuild backend with new packages
docker-compose build web

# Restart all services
docker-compose down
docker-compose up -d
```

## Step 5: Test Google OAuth

1. Navigate to http://localhost:5173/login
2. You should see the Google Sign-In button
3. Click it and follow the Google authentication flow
4. After successful authentication, you'll be redirected to the dashboard

## Troubleshooting

### "Google Sign-In Not Configured" Message
- Ensure `VITE_GOOGLE_CLIENT_ID` is set in frontend/.env.development
- Restart the frontend service after adding the environment variable

### "Invalid Google credential" Error
- Verify that the Client ID matches in both backend and frontend
- Check that the authorized origins include your development URL
- Ensure the Google+ API is enabled in Google Cloud Console

### CORS Issues
- Add your frontend URL to `CORS_ALLOWED_ORIGINS` in backend .env
- Default should include: `http://localhost:5173`

### "Site matching query does not exist" Error
- Run the site creation command in Step 2.3
- Ensure SITE_ID=1 in Django settings

## Production Deployment

For production deployment, you'll need to:

1. Update authorized origins and redirect URIs in Google Cloud Console
2. Use production domain instead of localhost
3. Set environment variables in your production environment
4. Consider using more secure OAuth flows (authorization code flow)
5. Enable HTTPS for all OAuth endpoints

## Security Notes

- Never commit OAuth credentials to version control
- Use environment variables for all sensitive configuration
- In production, use HTTPS for all OAuth-related endpoints
- Regularly rotate your OAuth client secret
- Monitor OAuth usage in Google Cloud Console

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Google Sign-In for Websites](https://developers.google.com/identity/gsi/web)
- [Django-Allauth Documentation](https://django-allauth.readthedocs.io/)
- [@react-oauth/google Documentation](https://www.npmjs.com/package/@react-oauth/google)