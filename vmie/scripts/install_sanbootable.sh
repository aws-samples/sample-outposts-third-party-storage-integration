#!/bin/bash

# Sanbootable Installation Script
# This script auto-detects the package manager and installs sanbootable accordingly
# Compatible with Debian/Ubuntu (apt) and RHEL/CentOS/Amazon Linux (yum/dnf)

set -e

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Function to check if a command exists
command_exists() {
    type "$1" &> /dev/null
}

# Function to verify installation
verify_installation() {
    log "Verifying sanbootable installation..."

    # Check if the package is installed
    if command_exists dpkg > /dev/null 2>&1; then
        if dpkg -s sanbootable > /dev/null 2>&1; then
            log "Sanbootable package is installed (Debian/Ubuntu)"
        else
            log "WARNING: Unable to verify sanbootable installation"
            return 1
        fi
    elif command_exists rpm > /dev/null 2>&1; then
        if rpm -q sanbootable > /dev/null 2>&1; then
            log "Sanbootable package is installed (RHEL/CentOS/Fedora)"
        else
            log "WARNING: Unable to verify sanbootable installation"
            return 1
        fi
    else
        log "WARNING: Unable to verify sanbootable installation"
        return 1
    fi

    log "Sanbootable installation verified successfully"
}

# Function to detect package manager and install sanbootable
install_sanbootable() {
    log "Starting sanbootable installation..."
    
    # Create temporary directory
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Cleanup function
    cleanup() {
        log "Cleaning up temporary files..."
        rm -rf "$TEMP_DIR"
    }
    trap cleanup EXIT
    
    # Auto-detect package manager and install
    if command_exists apt-get; then
        log "Detected apt package manager (Debian/Ubuntu)"
        install_with_apt
    elif command_exists yum; then
        log "Detected yum package manager (RHEL/CentOS/Amazon Linux)"
        install_with_yum
    elif command_exists dnf; then
        log "Detected dnf package manager (Fedora/newer RHEL)"
        install_with_dnf
    else
        log "ERROR: No supported package manager found (apt, yum, or dnf)"
        exit 1
    fi
    
    # Verify installation
    verify_installation
    log "Sanbootable installation completed successfully!"
}

wait_for_apt_locks() {
    local max_attempts=60  # Maximum number of attempts (10 minutes total)
    local attempt=1

    while fuser /var/lib/dpkg/lock >/dev/null 2>&1 || fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || fuser /var/cache/apt/archives/lock >/dev/null 2>&1; do
        if [ $attempt -ge $max_attempts ]; then
            log "ERROR: Package manager is still locked after 10 minutes. Aborting."
            exit 1
        fi
        log "Waiting for package manager locks to be released... ($attempt/$max_attempts)"
        sleep 10
        attempt=$((attempt + 1))
    done
}

# Function to install with apt (Debian/Ubuntu)
install_with_apt() {
    log "Installing sanbootable using apt..."

    # Wait for any existing locks to be released
    wait_for_apt_locks

    # Set non-interactive mode
    export DEBIAN_FRONTEND=noninteractive
    
    # Download sanbootable package
    log "Downloading sanbootable.deb..."
    curl -fsSL -o sanbootable.deb https://github.com/ipxe/sanbootable/releases/latest/download/sanbootable.deb
    
    # Update package list
    log "Updating package list..."
    sudo apt-get update -qq
    
    # Install sanbootable
    log "Installing sanbootable package..."
    sudo apt-get install -y -qq ./sanbootable.deb
}

# Function to install with yum (RHEL/CentOS/Amazon Linux)
install_with_yum() {
    log "Installing sanbootable using yum..."
    
    # Install directly from URL
    log "Installing sanbootable.rpm..."
    sudo yum install -y -q https://github.com/ipxe/sanbootable/releases/latest/download/sanbootable.rpm
}

# Function to install with dnf (Fedora/newer RHEL)
install_with_dnf() {
    log "Installing sanbootable using dnf..."
    
    # Install directly from URL
    log "Installing sanbootable.rpm..."
    sudo dnf install -y -q https://github.com/ipxe/sanbootable/releases/latest/download/sanbootable.rpm
}

# Main execution
main() {
    log "=== Sanbootable Installation Script ==="
    log "Auto-detecting system and installing sanbootable..."
    
    install_sanbootable
    
    log "=== Installation Complete ==="
}

main "$@"
