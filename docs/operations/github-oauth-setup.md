# GitHub OAuth Setup Guide

This guide will walk you through setting up GitHub OAuth authentication for Sterna.

## Prerequisites

- GitHub account
- Access to GitHub Developer Settings
- Project running locally

## Step 1: GitHub OAuth App Setup

1. **Go to GitHub Developer Settings**
   - Navigate to [https://github.com/settings/developers](https://github.com/settings/developers)
   - Sign in with your GitHub account

2. **Create a New OAuth App**
   - Click on "OAuth Apps" in the left sidebar
   - Click "New OAuth App" button
   - Fill in the application details:
     - **Application name**: Sterna Development
     - **Homepage URL**: `http://localhost:5173`
     - **Application description**: (Optional) OAuth integration for Sterna
     - **Authorization callback URL**: `http://localhost:5173/login`
   - Click "Register application"

3. **Save Your Credentials**
   - After creation, you'll see your credentials:
     - **Client ID**: A 20-character hexadecimal string
     - **Client Secret**: Click "Generate a new client secret" to create one
   - **Important**: Copy the client secret immediately - you won't be able to see it again
   - Save these credentials securely

4. **Configure OAuth Scopes**
   - GitHub OAuth uses scopes to define access levels
   - For basic authentication, you'll need:
     - `user:email` - Access to user email addresses
     - `read:user` - Read access to user profile data
   - These are configured in your application code, not in GitHub settings

## Step 2: Configure Backend

1. **Update Backend .env File**
   ```bash
   # In core/.env
   GITHUB_OAUTH_CLIENT_ID=your-github-client-id-here
   GITHUB_OAUTH_CLIENT_SECRET=your-github-client-secret-here
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
   Site.objects.update_or_create(id=1, defaults={'domain': 'localhost:8000', 'name': 'Sterna Development'}) 
   exit()
   ```

## Step 3: Configure Frontend

1. **Update Frontend .env.development File**
   ```bash
   # In core/frontend/.env.development
   VITE_GITHUB_CLIENT_ID=your-github-client-id-here
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

## Step 5: Test GitHub OAuth

1. Navigate to http://localhost:5173/login
2. You should see the GitHub Sign-In button
3. Click it and follow the GitHub authentication flow
4. After successful authentication, you'll be redirected to the dashboard

## Troubleshooting

### "GitHub Sign-In Not Configured" Message
- Ensure `VITE_GITHUB_CLIENT_ID` is set in frontend/.env.development
- Restart the frontend service after adding the environment variable

### "Invalid GitHub credential" Error
- Verify that the Client ID matches in both backend and frontend
- Check that the authorization callback URL is correct in GitHub OAuth App settings
- Ensure the callback URL matches: `http://localhost:8000/api/auth/github/callback`

### CORS Issues
- Add your frontend URL to `CORS_ALLOWED_ORIGINS` in backend .env
- Default should include: `http://localhost:5173`

### "Site matching query does not exist" Error
- Run the site creation command in Step 2.3
- Ensure SITE_ID=1 in Django settings

### "Bad verification code" Error
- This usually happens when the OAuth flow is interrupted
- Clear your browser cookies and try again
- Ensure your system clock is synchronized (OAuth tokens are time-sensitive)

### "Redirect URI mismatch" Error
- Verify the callback URL in GitHub OAuth App settings exactly matches your backend endpoint
- Check for trailing slashes - they matter!
- Ensure you're using the correct protocol (http vs https)

## Production Deployment

For production deployment, you'll need to:

1. **Create a separate GitHub OAuth App for production**
   - Use your production domain for Homepage URL
   - Update Authorization callback URL: `https://yourdomain.com/login`

2. **Update Environment Variables**
   - Set production Client ID and Secret in your production environment
   - Never use development credentials in production

3. **Enable HTTPS**
   - GitHub requires HTTPS for production OAuth apps
   - Ensure all OAuth endpoints use HTTPS

4. **Update Allowed Origins**
   - Configure CORS_ALLOWED_ORIGINS with your production frontend URL
   - Remove localhost URLs from production settings

5. **Rate Limiting**
   - Be aware of GitHub's OAuth rate limits
   - Implement proper error handling for rate limit responses

## Security Notes

- Never commit OAuth credentials to version control
- Use environment variables for all sensitive configuration
- In production, use HTTPS for all OAuth-related endpoints
- Regularly review authorized applications in your GitHub account
- Consider implementing token refresh mechanisms for long-lived sessions
- Monitor unusual authentication patterns
- Keep your Client Secret secure - regenerate if compromised
- Use GitHub's webhook events to monitor OAuth app usage

## Additional Resources

- [GitHub OAuth 2.0 Documentation](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)
- [GitHub OAuth Scopes](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)
- [GitHub REST API Authentication](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api)
- [Django-Allauth GitHub Provider](https://django-allauth.readthedocs.io/en/latest/providers.html#github)
- [Best Practices for OAuth Apps](https://docs.github.com/en/apps/oauth-apps/maintaining-oauth-apps/best-practices-for-oauth-apps)