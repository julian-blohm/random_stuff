#!/bin/bash

# Inform the user about the script
echo "This script will:"
echo "1. Zip a directory of your choice."
echo "2. Save the zip file to a location of your choice (default: your home directory)."
echo "3. Upload the zip file to a remote server using SCP."
echo

# Prompt user for input
read -rp "Enter the directory to be zipped: " SOURCE_DIR
read -rp "Enter the name for the zip file (without .zip): " ZIP_NAME
read -rp "Enter the local directory to store the zip file [default: $HOME]: " LOCAL_DIR
LOCAL_DIR=${LOCAL_DIR:-$HOME}
read -rp "Enter the remote server (user@host): " REMOTE_USER_HOST
read -rp "Enter the remote directory to store the zip file: " REMOTE_DIR

ZIP_FILE="${LOCAL_DIR%/}/${ZIP_NAME}.zip"

# Zip the source directory
zip -r "$ZIP_FILE" "$SOURCE_DIR"

# Copy the zip file to the remote server
scp "$ZIP_FILE" "$REMOTE_USER_HOST:$REMOTE_DIR"
