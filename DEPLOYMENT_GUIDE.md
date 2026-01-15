# Deployment Guide for Voice Chatbot

This guide will help you deploy your voice chatbot to either Render or Heroku.

## Prerequisites
- Your OpenAI API key
- A GitHub account (recommended) or direct deployment
- Account on Render.com or Heroku.com

---

## Option 1: Deploy to Render (Recommended - Free tier available)

### Step 1: Prepare Your Files
1. Create a new folder on your computer for this project
2. Copy all these files into that folder:
   - `server.py`
   - `requirements.txt`
   - `Procfile`
   - `runtime.txt`
   - `.gitignore`

### Step 2: Upload to GitHub (Optional but recommended)
1. Go to github.com and create a new repository
2. Upload all your files to this repository
3. Make sure `.env` is NOT uploaded (it should be ignored by .gitignore)

### Step 3: Deploy on Render
1. Go to https://render.com and sign up/login
2. Click "New +" → "Web Service"
3. Connect your GitHub repository (or choose "Deploy from Git URL")
4. Configure the service:
   - **Name**: voice-chatbot (or your preferred name)
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn server:app`
   - **Plan**: Free (or paid if you prefer)

### Step 4: Set Environment Variables
In the Render dashboard, go to "Environment" and add:
- **OPENAI_API_KEY**: Your actual OpenAI API key
- **OPENAI_REALTIME_MODEL**: gpt-4o-realtime-preview-2024-12-17
- **OPENAI_REALTIME_VOICE**: alloy
- **RT_SILENCE_MS**: 1200
- **RT_VAD_THRESHOLD**: 0.5
- **FLASK_DEBUG**: 0

### Step 5: Deploy
1. Click "Create Web Service"
2. Wait for the build to complete (5-10 minutes)
3. Once deployed, Render will give you a URL like: `https://your-app-name.onrender.com`
4. Visit `https://your-app-name.onrender.com/realtime` to use your chatbot!

---

## Option 2: Deploy to Heroku

### Step 1: Install Heroku CLI
1. Download from https://devcenter.heroku.com/articles/heroku-cli
2. Install and login: `heroku login`

### Step 2: Prepare Your Files
Same as Render - copy all files to a folder

### Step 3: Initialize Git (if not already done)
```bash
git init
git add .
git commit -m "Initial commit"
```

### Step 4: Create Heroku App
```bash
heroku create your-app-name
```

### Step 5: Set Environment Variables
```bash
heroku config:set OPENAI_API_KEY=your_actual_api_key_here
heroku config:set OPENAI_REALTIME_MODEL=gpt-4o-realtime-preview-2024-12-17
heroku config:set OPENAI_REALTIME_VOICE=alloy
heroku config:set RT_SILENCE_MS=1200
heroku config:set RT_VAD_THRESHOLD=0.5
heroku config:set FLASK_DEBUG=0
```

### Step 6: Deploy
```bash
git push heroku main
```

### Step 7: Open Your App
```bash
heroku open
```
Or visit: `https://your-app-name.herokuapp.com/realtime`

---

## Troubleshooting

### App crashes on startup
- Check that all environment variables are set correctly
- Check the logs: 
  - Render: Click "Logs" in dashboard
  - Heroku: Run `heroku logs --tail`

### Can't connect to OpenAI
- Verify your API key is valid
- Make sure you have credits in your OpenAI account
- Check that your API key has access to the Realtime API

### "Application Error" message
- Usually means the server failed to start
- Check logs for Python errors
- Verify all dependencies are in requirements.txt

### Port already in use (shouldn't happen in deployment)
- This is a local issue only
- Cloud platforms automatically assign ports
- The updated code uses `PORT` environment variable

---

## Testing Your Deployment

1. Visit your app URL with `/realtime` at the end
2. Click on one of the scenario buttons (e.g., "Order Breakfast (EN)")
3. Click "Connect" button
4. Allow microphone access when prompted
5. Start speaking!

---

## Cost Considerations

### Render
- Free tier available (good for testing)
- App may sleep after inactivity
- Paid plans start at $7/month for always-on

### Heroku
- Free tier discontinued (Nov 2022)
- Paid plans start at $5/month for hobby tier
- $7/month for always-on production tier

### OpenAI API
- Realtime API costs vary based on usage
- Check https://openai.com/pricing for current rates
- Monitor usage in OpenAI dashboard

---

## Next Steps

After deployment:
1. Test all 7 conversation scenarios
2. Share the URL with users
3. Monitor usage and costs
4. Customize the BOTS array in server.py for your needs

Need help? Check the logs first, then review this guide!
