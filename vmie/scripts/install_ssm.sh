#!/bin/bash

# AWS SSM Agent Installation Script
# Based on official AWS documentation: https://docs.aws.amazon.com/systems-manager/latest/userguide/manually-install-ssm-agent-linux.html
# Compatible with Amazon Linux, RHEL, CentOS, SLES, Ubuntu, and Debian
# Designed to run with root privileges on EC2 instances

set -e

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to detect OS and version
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        VERSION=$VERSION_ID
    elif [ -f /etc/redhat-release ]; then
        OS="rhel"
        VERSION=$(grep -oE '[0-9]+\.[0-9]+' /etc/redhat-release | head -1)
    elif [ -f /etc/debian_version ]; then
        OS="debian"
        VERSION=$(cat /etc/debian_version)
    else
        log "ERROR: Cannot detect operating system"
        exit 1
    fi
    
    log "Detected OS: $OS $VERSION"
}

# Function to detect architecture
detect_architecture() {
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)
            echo "amd64"
            ;;
        aarch64|arm64)
            echo "arm64"
            ;;
        *)
            log "ERROR: Unsupported architecture: $ARCH"
            exit 1
            ;;
    esac
}

# Function to check if SSM agent is already installed and running
check_ssm_status() {
    log "Checking SSM agent status..."
    
    # Check if amazon-ssm-agent service exists
    if systemctl list-unit-files amazon-ssm-agent.service >/dev/null 2>&1; then
        log "SSM agent service found"
        
        # Check if service is active
        if systemctl is-active amazon-ssm-agent >/dev/null 2>&1; then
            log "SSM agent is already installed and running"
            return 0
        else
            log "SSM agent is installed but not running"
            return 1
        fi
    else
        log "SSM agent is not installed"
        return 1
    fi
}

# Function to install on Amazon Linux
install_amazon_linux() {
    log "Installing SSM agent on Amazon Linux..."
    
    # Amazon Linux 2 and Amazon Linux 2023 have SSM agent pre-installed
    # Just ensure it's started and enabled
    if yum list installed amazon-ssm-agent >/dev/null 2>&1; then
        log "SSM agent is already installed via yum"
    else
        log "Installing SSM agent via yum..."
        yum install -y amazon-ssm-agent
    fi
}

# Function to install on RHEL/CentOS
install_rhel_centos() {
    local arch="$1"
    local version="$2"
    log "Installing SSM agent on RHEL/CentOS $version ($arch)..."
    
    # Create temporary directory
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Cleanup function
    cleanup() {
        log "Cleaning up temporary files..."
        rm -rf "$TEMP_DIR"
    }
    trap cleanup EXIT
    
    # Download and install based on version and architecture
    if [[ "$version" =~ ^[6-7] ]]; then
        # RHEL/CentOS 6-7
        case "$arch" in
            amd64)
                yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
                ;;
            arm64)
                yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_arm64/amazon-ssm-agent.rpm
                ;;
        esac
    else
        # RHEL/CentOS 8+ (use dnf if available, fallback to yum)
        if command_exists dnf; then
            case "$arch" in
                amd64)
                    dnf install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
                    ;;
                arm64)
                    dnf install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_arm64/amazon-ssm-agent.rpm
                    ;;
            esac
        else
            case "$arch" in
                amd64)
                    yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
                    ;;
                arm64)
                    yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_arm64/amazon-ssm-agent.rpm
                    ;;
            esac
        fi
    fi
}

# Function to install on SLES
install_sles() {
    local arch="$1"
    log "Installing SSM agent on SLES ($arch)..."
    
    # Create temporary directory
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Cleanup function
    cleanup() {
        log "Cleaning up temporary files..."
        rm -rf "$TEMP_DIR"
    }
    trap cleanup EXIT
    
    # Download and install
    case "$arch" in
        amd64)
            wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
            ;;
        arm64)
            wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_arm64/amazon-ssm-agent.rpm
            ;;
    esac
    
    rpm --install amazon-ssm-agent.rpm
}

# Function to install on Ubuntu
install_ubuntu() {
    local arch="$1"
    log "Installing SSM agent on Ubuntu ($arch)..."
    
    # Create temporary directory
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Cleanup function
    cleanup() {
        log "Cleaning up temporary files..."
        rm -rf "$TEMP_DIR"
    }
    trap cleanup EXIT
    
    # Set non-interactive mode
    export DEBIAN_FRONTEND=noninteractive
    
    # Update package list
    log "Updating package list..."
    apt-get update -qq
    
    # Download and install
    case "$arch" in
        amd64)
            wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb
            ;;
        arm64)
            wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_arm64/amazon-ssm-agent.deb
            ;;
    esac
    
    dpkg -i amazon-ssm-agent.deb
    
    # Fix any dependency issues
    apt-get install -f -y -qq
}

# Function to install on Debian
install_debian() {
    local arch="$1"
    log "Installing SSM agent on Debian ($arch)..."
    
    # Create temporary directory
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Cleanup function
    cleanup() {
        log "Cleaning up temporary files..."
        rm -rf "$TEMP_DIR"
    }
    trap cleanup EXIT
    
    # Set non-interactive mode
    export DEBIAN_FRONTEND=noninteractive
    
    # Update package list
    log "Updating package list..."
    apt-get update -qq
    
    # Download and install
    case "$arch" in
        amd64)
            wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb
            ;;
        arm64)
            wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_arm64/amazon-ssm-agent.deb
            ;;
    esac
    
    dpkg -i amazon-ssm-agent.deb
    
    # Fix any dependency issues
    apt-get install -f -y -qq
}

# Function to start and enable SSM agent
start_and_enable_ssm() {
    log "Starting and enabling SSM agent service..."
    
    # Start the service
    if ! systemctl start amazon-ssm-agent; then
        log "Failed to start amazon-ssm-agent service"
        return 1
    fi
    
    # Enable the service to start on boot
    if ! systemctl enable amazon-ssm-agent; then
        log "Failed to enable amazon-ssm-agent service"
        return 1
    fi
    
    # Wait a moment for the service to fully start
    sleep 2
    
    return 0
}

# Function to verify installation
verify_installation() {
    log "Verifying SSM agent installation..."
    
    # Check service status
    if systemctl is-active amazon-ssm-agent >/dev/null 2>&1; then
        log "✓ SSM agent is running"
        
        # Show service status
        log "Service status:"
        systemctl status amazon-ssm-agent --no-pager -l || true
        
        # Check if agent is registered (this may take a few minutes)
        log "Note: It may take a few minutes for the agent to register with Systems Manager"
        
        return 0
    else
        log "✗ SSM agent is not running properly"
        
        # Try to get more information about why it failed
        log "Service status:"
        systemctl status amazon-ssm-agent --no-pager -l || true
        
        log "Recent logs:"
        journalctl -u amazon-ssm-agent --no-pager -l -n 20 || true
        
        return 1
    fi
}

# Main installation function
install_ssm_agent() {
    log "Starting SSM agent installation..."
    
    # Check if already installed and running
    if check_ssm_status; then
        log "SSM agent is already installed and running. Skipping installation."
        return 0
    fi
    
    # Detect OS and architecture
    detect_os
    ARCH=$(detect_architecture)
    log "Detected architecture: $ARCH"
    
    # Install based on OS
    case "$OS" in
        amzn)
            install_amazon_linux
            ;;
        rhel|centos|rocky|almalinux)
            install_rhel_centos "$ARCH" "$VERSION"
            ;;
        sles|opensuse*)
            install_sles "$ARCH"
            ;;
        ubuntu)
            install_ubuntu "$ARCH"
            ;;
        debian)
            install_debian "$ARCH"
            ;;
        *)
            log "ERROR: Unsupported operating system: $OS"
            log "Supported OS: Amazon Linux, RHEL, CentOS, SLES, Ubuntu, Debian"
            exit 1
            ;;
    esac
    
    # Start and enable the service
    if ! start_and_enable_ssm; then
        log "ERROR: Failed to start SSM agent service"
        exit 1
    fi
    
    # Verify installation
    if verify_installation; then
        log "✓ SSM agent installation completed successfully!"
    else
        log "✗ SSM agent installation completed but service is not running properly"
        exit 1
    fi
}

# Main execution
main() {
    log "=== AWS SSM Agent Installation Script ==="
    log "Based on: https://docs.aws.amazon.com/systems-manager/latest/userguide/manually-install-ssm-agent-linux.html"
    log "Running with root privileges on EC2 instance"
    
    install_ssm_agent
    
    log "=== Installation Complete ==="
    log "SSM agent should now be running and ready to receive commands"
    log ""
    log "Important notes:"
    log "1. The instance must have appropriate IAM permissions for SSM to work properly"
    log "2. The instance must have internet connectivity or VPC endpoints configured"
    log "3. It may take a few minutes for the agent to register with Systems Manager"
    log "4. You can check the agent status with: systemctl status amazon-ssm-agent"
}

main "$@"
