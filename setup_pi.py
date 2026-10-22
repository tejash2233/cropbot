"""Install CropBot as a systemd service on Raspberry Pi OS. Run: sudo python3 setup_pi.py"""
import os, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parent
if os.geteuid() != 0:
    raise SystemExit('Run with sudo: sudo python3 setup_pi.py')
user = os.environ.get('SUDO_USER', 'pi')
service = f'''[Unit]
Description=CropBot Flask dashboard
After=network-online.target
Wants=network-online.target

[Service]
User={user}
WorkingDirectory={ROOT}
ExecStart={ROOT / 'venv' / 'bin' / 'python'} {ROOT / 'app.py'}
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
'''
path=pathlib.Path('/etc/systemd/system/cropbot.service')
path.write_text(service,encoding='utf-8')
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','cropbot'],check=True)
print('CropBot service enabled. Find the Pi IP with hostname -I, then open http://<pi-ip>:5000')
