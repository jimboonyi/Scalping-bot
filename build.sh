#!/bin/bash
set -e

# Create writable directories for apt
mkdir -p $HOME/.apt/{lists,archives}
export APT_DIR=$HOME/.apt

# Configure apt to use custom directories
echo "Dir::State \"$APT_DIR\";
Dir::State::status \"$APT_DIR/status\";
Dir::Cache \"$APT_DIR\";
Dir::Cache::archives \"$APT_DIR/archives\";" > $APT_DIR/apt.conf

# Install system dependencies
apt-get -o Dir::Etc::SourceList=/dev/null update
apt-get -o Dir::Etc::SourceList=/dev/null install -y \
    build-essential \
    wget \
    python3-dev

# Install TA-Lib in user space
TA_LIB_DIR=$HOME/ta-lib
mkdir -p $TA_LIB_DIR
wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=$TA_LIB_DIR
make -j$(nproc)
make install
cd ..
rm -rf ta-lib*

# Install Python dependencies
pip install --user -r requirements.txt

# Set environment variables
echo "export TA_LIBRARY_PATH=$TA_LIB_DIR/lib" >> $HOME/.bashrc
echo "export LD_LIBRARY_PATH=$TA_LIB_DIR/lib:\$LD_LIBRARY_PATH" >> $HOME/.bashrc
