# 🤖 Telegram Bot Setup Guide

This guide will walk you through setting up a Telegram bot for your MLB GIF Dashboard.

## 📋 Quick Setup Checklist

- [ ] Create Telegram Bot with @BotFather
- [ ] Get Bot Token
- [ ] Create/Choose Chat/Channel
- [ ] Get Chat ID
- [ ] Set Environment Variables
- [ ] Test Bot Connection

## 🚀 Step-by-Step Setup

### Step 1: Create Your Telegram Bot

1. **Open Telegram** and search for `@BotFather`
2. **Start a chat** with @BotFather
3. **Send the command**: `/newbot`
4. **Choose a name** for your bot (e.g., "MLB GIF Dashboard")
5. **Choose a username** for your bot (must end in 'bot', e.g., "mlb_gif_dashboard_bot")
6. **Copy the Bot Token** - it looks like: `123456789:ABCdefGHIjklMNOpqrSTUvwxyz`

### Step 2: Get Your Chat ID

You have several options for where to send the GIFs:

#### Option A: Private Chat (Simplest)
1. **Start a chat** with your newly created bot
2. **Send any message** to the bot (e.g., "Hello")
3. **Visit this URL** in your browser (replace `YOUR_BOT_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
4. **Find your Chat ID** in the response - it's a positive number like `123456789`

#### Option B: Group Chat
1. **Create a group** or use an existing one
2. **Add your bot** to the group
3. **Send a message** in the group (mentioning the bot: `@your_bot_name hello`)
4. **Visit the getUpdates URL** (same as above)
5. **Find the Chat ID** - it will be a negative number like `-123456789`

#### Option C: Channel
1. **Create a channel** or use an existing one
2. **Add your bot** as an administrator with "Post Messages" permission
3. **Post a message** in the channel
4. **Visit the getUpdates URL** (same as above)
5. **Find the Chat ID** - it will be a negative number starting with `-100`

### Step 3: Set Environment Variables

#### For Local Development:
```bash
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxyz"
export TELEGRAM_CHAT_ID="your_chat_id_here"
```

#### For Render Deployment:
1. Go to your Render dashboard
2. Select your web service
3. Go to "Environment" tab
4. Add these variables:
   - `TELEGRAM_BOT_TOKEN` = `123456789:ABCdefGHIjklMNOpqrSTUvwxyz`
   - `TELEGRAM_CHAT_ID` = `your_chat_id_here`

### Step 4: Test Your Setup

Run the test script:
```bash
python test_telegram_bot.py
```

You should see:
- ✅ Bot connection successful
- ✅ Test message sent successfully
- A test message in your Telegram chat

## 🔧 Troubleshooting

### Common Issues:

**"Bot not configured" error:**
- Make sure both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set
- Check for typos in the environment variable names

**"Bot connection failed" error:**
- Verify your bot token is correct
- Make sure you copied the full token including the colon

**"Failed to send test message" error:**
- Check your Chat ID is correct
- For groups/channels, make sure the bot has permission to post
- For private chats, make sure you've started a conversation with the bot

**"Forbidden: bot was blocked by the user" error:**
- Unblock the bot in your Telegram client
- Start a new conversation with the bot

**"Chat not found" error:**
- Double-check your Chat ID
- For groups, make sure the Chat ID is negative
- For channels, make sure the Chat ID starts with `-100`

### Finding Chat ID Alternative Method:

If the `getUpdates` method doesn't work, try this:

1. **Add @userinfobot** to your group/channel
2. **Send `/start` command** in the group/channel
3. The bot will reply with the Chat ID

## 📱 Bot Permissions

### For Private Chats:
- No special permissions needed
- Just start a conversation with the bot

### For Groups:
- Add the bot to the group
- No admin permissions required (unless group restricts non-admin posting)

### For Channels:
- Add the bot as an administrator
- Enable "Post Messages" permission
- Optionally enable "Edit Messages" if you want the bot to edit its posts

## 🎯 GIF Delivery Features

Your MLB GIF Dashboard will now send:

- **High-quality GIFs** (up to 50MB - much larger than Discord's 8MB limit!)
- **Rich formatting** with game details, player info, and impact scores
- **Individual pitch GIFs** with detailed pitch information
- **Highlight GIFs** from MLB's official highlights
- **Real-time notifications** as you create GIFs through the dashboard

## 🔒 Security Notes

- **Keep your bot token secret** - never share it publicly
- **Use environment variables** - don't hardcode tokens in your code
- **Revoke tokens if compromised** - use @BotFather to generate new tokens
- **Limit bot permissions** - only give necessary permissions in groups/channels

## 🎉 You're Ready!

Once you see "✅ All tests passed!" from the test script, your Telegram bot is ready to receive MLB GIFs from your dashboard!

The dashboard will now send beautiful, high-quality GIFs directly to your chosen Telegram chat whenever you click "🎬 Create GIF" on any play. 