@echo off
title Film4K Web Player & TV Live Stream
echo ================================================================
echo           FILM4K WEB STREAMER & TV CHANNELS (PORT 5000)
echo ================================================================
echo.
echo Dang khoi dong Web Server tren http://localhost:5000 ...
echo Trinh duyet se tu dong mo trong giay lat...
echo.

start "" "http://localhost:5000"
python web_player_server.py
pause
