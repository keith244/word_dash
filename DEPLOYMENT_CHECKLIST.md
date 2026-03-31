# Deployment Checklist for Fly.io

## ✅ What's Been Prepared

Your project is now ready for deployment to Fly.io. Here's what has been set up:

### 1. **Configuration Management**
   - ✅ `settings.py` updated to read from environment variables
   - ✅ Falls back to `config.json` for development
   - ✅ Supports both MySQL and PostgreSQL databases
   - ✅ `.env.example` created with all required variables

### 2. **Containerization**
   - ✅ `Dockerfile` - Multi-stage build with minimal footprint
   - ✅ `.dockerignore` - Optimized for faster builds
   - ✅ `start.sh` - Startup script that handles migrations

### 3. **Fly.io Configuration**
   - ✅ `fly.toml` - Complete Fly.io configuration
   - ✅ Health checks configured
   - ✅ Static files handling with WhiteNoise
   - ✅ Automatic migrations on deploy

### 4. **Dependencies**
   - ✅ `requirements.txt` updated with:
     - `gunicorn` - WSGI server (backup)
     - `daphne` - ASGI server for WebSocket support
     - `whitenoise` - Static file serving
     - `psycopg2-binary` - PostgreSQL support
     - `python-dotenv` - Environment variable loading

### 5. **Documentation**
   - ✅ `DEPLOYMENT.md` - Complete step-by-step guide
   - ✅ `config.production.example.json` - Production config template

## 📋 Next Steps

### 1. Generate Your Production SECRET_KEY
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 2. Commit These Changes to Your `prod` Branch
```bash
git add .
git commit -m "Prepare for Fly.io deployment"
git push origin prod
```

### 3. Install Flyctl CLI
```bash
# Windows PowerShell:
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"

# Or download from: https://fly.io/docs/getting-started/installing-flyctl/
```

### 4. Follow the DEPLOYMENT.md Guide
The complete step-by-step deployment instructions are in `DEPLOYMENT.md`

## ⚠️ Important Notes

### Database Choice
- **PostgreSQL** (Recommended): Better integration with Fly.io, use `django.db.backends.postgresql`
- **MySQL**: Supported with `django.db.backends.mysql`

### WebSocket Support (Channels)
- Your app uses Django Channels
- Currently configured with `InMemoryChannelLayer` (fine for single instance)
- For multiple instances, switch to `channels_redis.core.RedisChannelLayer` (see DEPLOYMENT.md)

### Static Files
- WhiteNoise handles static file serving automatically
- Files from `static/` directory are collected and served
- You can use Fly.io's static file mounting for better performance

### Environment Variables
Use `flyctl secrets set` to securely configure sensitive values:
- `SECRET_KEY` - Always generate a new one for production!
- Database credentials
- Email settings
- API keys

## 🔒 Security Reminders

- [ ] Generate a new `SECRET_KEY` (don't use the dev one)
- [ ] Set `DEBUG=False` in production
- [ ] Use environment variables for all secrets (never commit them)
- [ ] Configure proper `ALLOWED_HOSTS` for your domain
- [ ] Enable HTTPS (Fly.io does this automatically)
- [ ] For Gmail: Use [App Passwords](https://support.google.com/accounts/answer/185833)

## 📞 Deployment Support

- Fly.io Docs: https://fly.io/docs/
- Django Deployment: https://docs.djangoproject.com/en/5.0/howto/deployment/
- Channels Documentation: https://channels.readthedocs.io/

## Helpful Commands After Deployment

```bash
# Check deployment status
flyctl status -a <app-name>

# View logs
flyctl logs -a <app-name>

# SSH into instance
flyctl ssh console -a <app-name>

# View secrets
flyctl secrets list -a <app-name>

# Scale resources
flyctl scale memory 1024 -a <app-name>
flyctl scale count 2 -a <app-name>
```

---

**Ready to deploy!** Follow the steps in `DEPLOYMENT.md` to get your app live on Fly.io.
