# Fly.io Deployment Guide for Word Dash

## Prerequisites

1. **Fly.io Account**: Sign up at https://fly.io
2. **Flyctl CLI**: Install from https://fly.io/docs/getting-started/installing-flyctl/
3. **Git**: Your code should be in the `prod` branch

## Step-by-Step Deployment

### 1. Generate a Production SECRET_KEY

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Save this value - you'll need it in Step 3.

### 2. Prepare Your Fly.io App

```bash
# Log in to Fly.io
flyctl auth login

# Create a new app (choose a unique name)
flyctl launch --no-deploy
```

When prompted:
- **App Name**: Choose something like `word-dash` (must be unique)
- **Region**: Choose the closest one to your users (e.g., `ord` for US Midwest)
- **Add a database?**: Choose based on your preference:
  - **PostgreSQL** (recommended): More stable, better for Fly.io
  - **MySQL**: If you prefer MySQL compatibility

### 3. Set Environment Secrets

```bash
# Generate secret key and set all required secrets
flyctl secrets set \
  SECRET_KEY="YOUR_GENERATED_SECRET_KEY" \
  DEBUG=False \
  ALLOWED_HOSTS="your-app-name.fly.dev" \
  DB_ENGINE="django.db.backends.postgresql" \
  DB_NAME="word_dash" \
  DB_USER="postgres" \
  DB_PASSWORD="your-secure-password" \
  DB_HOST="your-db-hostname.internal" \
  DB_PORT="5432" \
  EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend" \
  EMAIL_HOST="smtp.gmail.com" \
  EMAIL_PORT="587" \
  EMAIL_USE_TLS="True" \
  EMAIL_HOST_USER="your-email@gmail.com" \
  EMAIL_HOST_PASSWORD="your-app-password" \
  DJANGO_ENV="production" \
  PYTHONUNBUFFERED="1"
```

**Important for Gmail**: Use an [App Password](https://support.google.com/accounts/answer/185833), not your regular password.

### 4. Configure Database Connection

If you used Fly.io's database attachment:

```bash
# For PostgreSQL
flyctl postgres attach your-db-name -a your-app-name
```

This will automatically set the `DATABASE_URL` environment variable.

### 5. Update ALLOWED_HOSTS

Replace the placeholder in the command above with your actual app name:
- If your app is `word-dash`, use: `word-dash.fly.dev`

### 6. Deploy Your Application

```bash
# From the prod branch
git checkout prod
git pull origin prod

# Deploy to Fly.io
flyctl deploy
```

The deployment will:
1. Build your Docker image
2. Push it to Fly.io's registry
3. Start your application
4. Run database migrations automatically

### 7. Verify Deployment

```bash
# Check logs
flyctl logs -a your-app-name

# SSH into the app instance (if needed for debugging)
flyctl ssh console -a your-app-name
```

### 8. Create a Superuser (First Time Only)

```bash
flyctl ssh console -a your-app-name
cd /app
python manage.py createsuperuser
```

## Scaling and Configuration

### Increase Machine Resources

```bash
flyctl scale memory 1024 -a your-app-name
flyctl scale count 2 -a your-app-name  # Add more instances
```

### View Current Secrets

```bash
flyctl secrets list -a your-app-name
```

### Update a Secret

```bash
flyctl secrets set SECRET_NAME="new-value" -a your-app-name
```

### Monitor Your App

```bash
# View metrics
flyctl metrics -a your-app-name

# View status
flyctl status -a your-app-name

# Scale down machines
flyctl machine list -a your-app-name
flyctl machine stop <machine-id>
```

## WebSocket Support (Channels)

Your app uses Django Channels for WebSocket support. The current setup uses:
- **ASGI Server**: Daphne
- **Channel Backend**: InMemoryChannelLayer (development)

**For production with multiple instances**, upgrade to:

```bash
# Install Redis
# Add to your app on Fly.io:
flyctl redis create -a your-app-name --enable-eviction

# Update settings.py CHANNEL_LAYERS to use Redis:
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [os.environ.get('REDIS_URL', 'redis://localhost:6379')],
        },
    }
}

# Set the Redis connection string
flyctl secrets set REDIS_URL="redis://<username>:<password>@<host>:<port>"
```

## Troubleshooting

### Migrations Failed

```bash
flyctl ssh console -a your-app-name
cd /app
python manage.py migrate --verbosity 2
```

### Static Files Not Loading

```bash
flyctl ssh console -a your-app-name
cd /app
python manage.py collectstatic --noinput --clear
```

### Database Connection Issues

```bash
# Check environment variables
flyctl ssh console -a your-app-name
env | grep DB_
```

### App Keeps Restarting

```bash
# Check logs for errors
flyctl logs -a your-app-name --follow
```

## Continuous Deployment (Optional)

To automatically deploy on git push to `prod`:

1. Generate a Fly.io token:
   ```bash
   flyctl tokens create deploy
   ```

2. Add to GitHub Secrets (if using GitHub):
   - `FLY_API_TOKEN`: Your token
   - `FLY_APP_NAME`: Your app name

3. Create `.github/workflows/deploy.yml`:
   ```yaml
   name: Deploy to Fly.io
   on:
     push:
       branches: [prod]
   
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v2
         - uses: superfly/flyctl-actions/setup-flyctl@master
         - run: flyctl deploy --remote-only
           env:
             FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
   ```

## Support

- Fly.io Docs: https://fly.io/docs/
- Django Deployment: https://docs.djangoproject.com/en/5.0/howto/deployment/
- Check Fly.io status: https://status.fly.io
