#!/bin/bash

# ==============================================================================
# Setup Script for macOS
# ==============================================================================
# This script automates the installation of project dependencies on macOS
# using Homebrew. It will:
# 1. Check for and install Homebrew.
# 2. Install PostgreSQL and Redis.
# 3. Start PostgreSQL and Redis services.
# 4. Create the required database and user for the project.
# ==============================================================================

# --- Script Configuration ---
DB_NAME="resource_accounting"
DB_USER="your_db_user"       # <-- IMPORTANT: Change this to your desired username
DB_PASSWORD="your_db_password" # <-- IMPORTANT: Change this to a secure password

# --- Helper Functions ---
function print_info {
    echo -e "\033[34m[INFO] $1\033[0m"
}

function print_success {
    echo -e "\033[32m[SUCCESS] $1\033[0m"
}

function print_warning {
    echo -e "\033[33m[WARNING] $1\033[0m"
}

function print_error {
    echo -e "\033[31m[ERROR] $1\033[0m"
    exit 1
}

# --- 1. Install Homebrew ---
print_info "Checking for Homebrew..."
if ! command -v brew &> /dev/null
then
    print_warning "Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ $? -ne 0 ]; then
        print_error "Homebrew installation failed. Please install it manually and re-run this script."
    fi
    print_success "Homebrew installed successfully."
else
    print_success "Homebrew is already installed."
fi

# --- 2. Install Dependencies ---
print_info "Installing PostgreSQL and Redis using Homebrew..."
brew update
brew install postgresql redis

if [ $? -ne 0 ]; then
    print_error "Failed to install PostgreSQL or Redis."
fi
print_success "PostgreSQL and Redis installed successfully."

# --- 3. Start Services ---
print_info "Starting PostgreSQL and Redis services..."
brew services start postgresql
brew services start redis
print_success "Services started."

# --- 4. Configure PostgreSQL ---
print_info "Configuring PostgreSQL database and user..."

# Check if user already exists
if psql -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1
then
    print_warning "User '$DB_USER' already exists. Skipping user creation."
else
    print_info "Creating user: $DB_USER"
    createuser --createdb $DB_USER -U postgres || print_error "Failed to create user."
    psql -U postgres -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    print_success "User '$DB_USER' created."
fi

# Check if database already exists
if psql -U postgres -lqt | cut -d \| -f 1 | grep -qw $DB_NAME
then
    print_warning "Database '$DB_NAME' already exists. Skipping database creation."
else
    print_info "Creating database: $DB_NAME"
    createdb -U postgres -O $DB_USER $DB_NAME || print_error "Failed to create database."
    print_success "Database '$DB_NAME' created and owner set to '$DB_USER'."
fi

# --- 5. Final Instructions ---
print_success "All dependencies have been set up!"
print_info "Please complete the following final step:"
print_info "1. Copy `.env.example` to `.env`.
2. Update the `.env` file with the following credentials:
   DB_USER=${DB_USER}
   DB_PASSWORD=${DB_PASSWORD}
   DB_NAME=${DB_NAME}"
