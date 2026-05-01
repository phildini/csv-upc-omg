# Fly.io Deployment Guide

## Prerequisites
- [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/)
- GitHub repository secrets: `FLY_API_TOKEN`

## Initial Setup

### 1. Create Fly.io Application
```bash
flyctl apps create csv-upc-omg
```

### 2. Create Persistent Volume (500MB)
```bash
flyctl volumes create csv_upc_omg_data --size 1
```

### 3. Set Environment Variables
```bash
flyctl secrets set \
  DATABASE_URL=sqlite:////data/db.sqlite3 \
  SECRET_KEY=$(openssl rand -base64 48) \
  ALLOWED_HOSTS=omgupc.com,*.fly.dev,localhost \
  MEDIA_ROOT=/data/media \
  DEBUG=False
```

### 4. Deploy Application
```bash
flyctl deploy
```

### 5. Add Custom Domain
```bash
flyctl certs add omgupc.com
```

## Environment Variables

### Required
- `DATABASE_URL=sqlite:////data/db.sqlite3` - SQLite database on volume
- `SECRET_KEY` - Django secret key (64 random characters)
- `ALLOWED_HOSTS=omgupc.com,*.fly.dev,localhost` - Allowed hosts
- `MEDIA_ROOT=/data/media` - Media files location on volume
- `DEBUG=False` - Production mode

### Optional
- `DJANGO_SUPERUSER_USERNAME=admin` - Admin username
- `DJANGO_SUPERUSER_EMAIL=admin@example.com` - Admin email
- `DJANGO_SUPERUSER_PASSWORD=password` - Admin password

## File Structure on Volume
```
/data/
├── db.sqlite3          # SQLite database
└── media/              # User uploaded files
```

## Continuous Deployment

### GitHub Actions Setup
1. Add `FLY_API_TOKEN` to GitHub repository secrets
2. Push to `main` branch triggers auto-deploy after tests pass

### Manual Deployment
```bash
# Build and deploy
flyctl deploy

# View logs
flyctl logs

# SSH into app
flyctl ssh console

# Run Django management commands
flyctl ssh console -C "python web/manage.py migrate"
flyctl ssh console -C "python web/manage.py createsuperuser"
```

## Health Monitoring
- Health endpoint: `https://omgupc.com/health/`
- Returns JSON: `{"status": "healthy", "timestamp": 1234567890, "service": "csv-upc-omg"}`

## Backups
```bash
# Create volume snapshot
flyctl volumes snapshots create csv_upc_omg_data

# List snapshots
flyctl volumes snapshots list csv_upc_omg_data

# Restore from snapshot
flyctl volumes restore csv_upc_omg_data <snapshot-id>
```

## Troubleshooting

### Database Issues
```bash
# Check database file exists
flyctl ssh console -C "ls -la /data/"

# Run migrations
flyctl ssh console -C "python web/manage.py migrate"

# Create backup before operations
flyctl volumes snapshots create csv_upc_omg_data
```

### Application Issues
```bash
# View logs
flyctl logs

# Restart application
flyctl apps restart csv-upc-omg

# Scale resources if needed
flyctl scale memory 512
flyctl scale count 2
```

## Maintenance

### Update Application
```bash
git push origin main  # Auto-deploys via GitHub Actions
# OR
flyctl deploy         # Manual deploy
```

### Database Maintenance
```bash
# Access Django shell
flyctl ssh console -C "python web/manage.py shell"

# Create superuser (if not created on first deploy)
flyctl ssh console -C "python web/manage.py createsuperuser"
```

## Monitoring
- Fly.io dashboard: https://fly.io/apps/csv-upc-omg
- Health checks: Automatic via Fly.io
- Logs: `flyctl logs` or Fly.io dashboard

## Rollback
```bash
# View deploy history
flyctl releases

# Rollback to previous version
flyctl releases rollback v<version-number>
```
