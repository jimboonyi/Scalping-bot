#!/bin/bash
set -o errexit

# Install TA-Lib dependencies
apt-get update
apt-get install -y build-essential wget

# Download and install TA-Lib
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
make install
cd ..
rm -rf ta-lib-0.4.0-src.tar.gz ta-lib

# Install Python dependencies
pip install -r requirements.txt
