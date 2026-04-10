#!/bin/bash
# Install system dependencies
sudo apt update && sudo apt install -y git festival xsel python3-pip libxml2-dev libxslt1-dev python3-dev libjpeg-dev zlib1g-dev build-essential python3-gi python3-gi-cairo gir1.2-gtk-4.0 yad

# Install python dependencies
pip install -r requirements.txt
