# hcmut-211-cn-asg1
Computer Network: Assignment 1

On server's side:
```
python3 Server.py 5000
```

On client's side:
```
python3 ClientLauncher.py localhost 5000 6000 superIdol.Mjpeg
```

Bugs:
- Scroll at the start (before any Plays) would result in black screen (but the app still works).
- Rarely Pause while Playing (acceptable): maybe because race condition b/w threads (?).