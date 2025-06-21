# 🎯 Manual MLB GIF Dashboard

A comprehensive web dashboard for manually selecting MLB plays to convert into GIFs and send to Telegram. This system provides complete control over which plays become GIFs, with real-time game monitoring and an intuitive selection interface.

## ✨ Features

### 🎮 Manual Control
- **No Automatic GIF Creation**: Nothing happens automatically - you choose every GIF
- **Play-by-Play Selection**: Browse all plays from today's games and select exactly what you want
- **Real-time Updates**: New plays appear every 2 minutes during live games
- **Smart Impact Scoring**: Plays are ranked by impact to help you find the most interesting moments

### 📊 Comprehensive Dashboard
- **Beautiful Modern Interface**: Clean, responsive design that works on all devices
- **Live Game Monitoring**: Real-time scores, inning status, and game states
- **Play Details**: Full context for each play including batter, pitcher, impact score, and description
- **Visual Status Indicators**: Easy to see which plays have been processed or are in progress

### 🚀 Optimized Performance
- **512MB RAM Optimized**: Designed specifically for Render's free tier limitations
- **Memory Efficient**: GIFs are created, sent, and immediately deleted
- **Smart Cleanup**: Automatic removal of old games and temporary files
- **Efficient Caching**: Minimal memory footprint with intelligent data management

### 🎬 Professional GIF Creation
- **Baseball Savant Integration**: Uses official MLB video sources
- **High-Quality Output**: Optimized GIF compression for Telegram's file limits
- **Fast Processing**: Typically creates GIFs in under 30 seconds
- **Error Handling**: Robust fallback systems for reliable operation

## 🛠️ Setup Instructions

### Prerequisites
- Python 3.11+
- FFmpeg (for video processing)
- Telegram Bot Token and Chat ID

### Local Development

1. **Clone and Setup**
   ```bash
   git clone <your-repo>
   cd mlb-gif-dashboard
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   ```bash
   export TELEGRAM_BOT_TOKEN="your_telegram_bot_token_here"
   export TELEGRAM_CHAT_ID="your_telegram_chat_id_here"
   export SECRET_KEY="your_secret_key_here"
   ```

3. **Run the Dashboard**
   ```bash
   python manual_gif_dashboard.py
   ```

4. **Access Dashboard**
   Open http://localhost:5000 in your browser

### 🌐 Render Deployment

This system is optimized for Render's free tier:

1. **Create New Web Service**
   - Connect your GitHub repository
   - Choose "Web Service"
   - Select your repository

2. **Configure Build Settings**
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python manual_gif_dashboard.py`
   - **Environment**: Python 3.11

3. **Set Environment Variables**
   ```
   TELEGRAM_BOT_TOKEN = your_telegram_bot_token
   TELEGRAM_CHAT_ID = your_telegram_chat_id
   SECRET_KEY = auto-generated_or_custom
   PORT = 10000
   ```

4. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment to complete
   - Access your dashboard at the provided Render URL

### 📱 Telegram Bot Setup

1. **Create Telegram Bot**
   - Message @BotFather on Telegram
   - Send `/newbot` command
   - Follow the prompts to create your bot
   - Copy the bot token (looks like: `123456789:ABCdefGHIjklMNOpqrSTUvwxyz`)

2. **Get Chat ID**
   - Add your bot to a group or channel, OR
   - Start a private chat with your bot
   - Send a message to the bot/group
   - Visit: `https://api.telegram.org/bot<YourBOTToken>/getUpdates`
   - Find your chat ID in the response (positive for groups, negative for channels)

3. **Set Environment Variables**
   ```bash
   export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxyz"
   export TELEGRAM_CHAT_ID="your_chat_id_here"
   ```

## 🎯 How to Use

### 1. **Monitor Games**
   - Dashboard automatically starts monitoring today's MLB games
   - Games appear as they begin, with live scores and inning information
   - New plays are fetched every 2 minutes

### 2. **Browse Plays**
   - Each game shows all recent plays with full details
   - Plays are color-coded by impact level (high-impact plays highlighted)
   - View batter, pitcher, description, and game situation for each play

### 3. **Create GIFs**
   - Click "🎬 Create GIF" on any play you want to turn into a GIF
   - System will find the best video match from Baseball Savant
   - GIF is created, sent to Telegram, and immediately deleted from server

### 4. **Track Status**
   - Status bar shows monitoring status, last update time, and totals
   - Play buttons update to show processing status and completion
   - Toast notifications confirm successful GIF creation and delivery

## 🔧 Configuration

### Memory Optimization
- **Max Games**: 20 games kept in memory (configurable)
- **Max Plays per Game**: 50 plays per game (configurable)
- **Cleanup Interval**: Games older than 24 hours automatically removed
- **Temp File Management**: All temporary files cleaned up immediately

### Update Intervals
- **Game Monitoring**: Every 2 minutes (120 seconds)
- **Dashboard Refresh**: Every 30 seconds (frontend auto-refresh)
- **Cleanup Check**: Every monitoring cycle

### GIF Settings
- **Max Duration**: 8 seconds
- **Resolution**: 640p (high quality for Telegram)
- **Frame Rate**: 20 fps
- **Max File Size**: 50MB (Telegram bot limit)

## 🌟 API Endpoints

### Public Endpoints
- `GET /` - Main dashboard interface
- `GET /api/ping` - Health check for Render
- `GET /api/status` - System status information

### Game Data
- `GET /api/games` - All games with plays (JSON)

### Actions
- `POST /api/create_gif` - Create GIF for specific play
- `GET /start_monitoring` - Start game monitoring
- `GET /stop_monitoring` - Stop game monitoring

## 🔍 Monitoring and Logging

### Health Checks
- **Render Health Check**: `/api/ping` endpoint
- **System Status**: Real-time monitoring dashboard
- **Error Tracking**: Comprehensive logging system

### Log Files
- **gif_dashboard.log**: Main application log
- **Console Output**: Real-time status and errors

## 🎨 Dashboard Features

### Visual Elements
- **Modern Gradient Design**: Beautiful purple-to-blue gradient background
- **Glass Morphism**: Translucent cards with backdrop blur effects
- **Responsive Layout**: Works perfectly on desktop, tablet, and mobile
- **Smooth Animations**: Hover effects and loading indicators

### User Experience
- **Intuitive Navigation**: Clear labeling and logical flow
- **Real-time Updates**: Live data without page refreshes
- **Toast Notifications**: Success and error messages
- **Loading States**: Clear feedback during processing

### Accessibility
- **High Contrast**: Easy-to-read text and indicators
- **Mobile Optimized**: Touch-friendly interface on mobile devices
- **Keyboard Navigation**: Full keyboard accessibility support

## 🔒 Security

### Environment Variables
- All sensitive data stored in environment variables
- No hardcoded secrets in source code
- Configurable secret key for session security

### Data Privacy
- No persistent storage of game data
- Temporary files immediately cleaned up
- No user data collection or tracking

## 🚨 Troubleshooting

### Common Issues

**GIF Creation Fails**
- Check if FFmpeg is installed and accessible
- Verify Baseball Savant video availability
- Check Telegram bot token and chat ID

**Dashboard Not Updating**
- Verify MLB API connectivity
- Check system monitoring status
- Review browser console for JavaScript errors

**Memory Issues**
- Reduce max_games setting if needed
- Ensure proper cleanup is running
- Monitor Render metrics dashboard

### Debug Mode
```bash
export FLASK_DEBUG=true
python manual_gif_dashboard.py
```

## 📈 Performance Metrics

### Typical Performance
- **GIF Creation Time**: 15-45 seconds
- **Memory Usage**: <400MB on Render free tier
- **API Response Time**: <2 seconds
- **Dashboard Load Time**: <3 seconds

### Optimization Features
- Efficient MLB API usage
- Minimal memory footprint
- Smart caching strategies
- Immediate resource cleanup

## 🤝 Contributing

This system is designed to be easily customizable:

1. **Fork the repository**
2. **Make your changes**
3. **Test thoroughly**
4. **Submit a pull request**

### Areas for Enhancement
- Additional video sources
- Enhanced play filtering
- Custom notification formats
- Advanced analytics

## 📄 License

MIT License - Feel free to modify and distribute as needed.

---

**🎯 Ready to start creating amazing MLB GIFs manually? Deploy to Render and start selecting your favorite plays!** 