# Publishing To Cerebro From Nuke

1. Be sure to install ffmpeg for thumbnail rendering.<br>
- in Command Prompt enter:
    `winget install ffmpeg`
- check installation `ffmpeg --version`

2. You need json file with your Cerebro auth credentials.<br>
- add your username and password to file:
`‪C:\Users\Admin\.nuke\cerebro\cerebro_account_info.json`
```
{
    "name": "your@mail.com", 
    "pass": "your_password"
}
```
