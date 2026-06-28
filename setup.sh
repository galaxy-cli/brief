#!/bin/bash
# Define paths relative to user environment
VENV_PATH="$HOME/.venv"
ALIAS_FILE="$HOME/.bash_aliases"
CURRENT_DIR="$(pwd)"

# 1. Initialize and build the Python isolated virtual space environment
if [ ! -d "$VENV_PATH" ]; then
    echo "🔧 Creating virtual environment at $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
    sleep 2
else
    echo "✓ Virtual environment already exists at $VENV_PATH."
fi

# 2. Activate the localized virtual environment context
source "$VENV_PATH/bin/activate"

# 3. Upgrade package pipeline to avoid binary compilation errors
echo "🤖 Upgrading core package managers..."
python3 -m pip install --upgrade pip > /dev/null 2>&1
sleep 1

# 4. Ingest and upgrade project-specific external libraries
if [ -f "requirements.txt" ]; then
    echo "📦 Synchronizing dependency libraries from requirements.txt..."
    python3 -m pip install --upgrade -r requirements.txt
else
    # Automatically seed required modules if requirements file is missing
    echo "⚠️ requirements.txt not found. Installing base configurations directly..."
    python3 -m pip install --upgrade feedparser newspaper3k
fi

# 5. Exit the virtual environment sub-shell safely
deactivate

# 6. Verify or build the permanent alias definition file
touch "$ALIAS_FILE"

# 7. Atomically insert the executable path shortcut without duplicating entries
if ! grep -q "alias brief=" "$ALIAS_FILE"; then
    echo "" >> "$ALIAS_FILE"
    echo "# brief application launcher" >> "$ALIAS_FILE"
    echo "alias brief='$VENV_PATH/bin/python3 $CURRENT_DIR/brief.py'" >> "$ALIAS_FILE"
    echo "✓ Added 'brief' executable alias to $ALIAS_FILE."
else
    echo "✓ Alias 'brief' is already configured inside $ALIAS_FILE."
fi

echo ""
echo "🎉 Setup complete! Reload your shell to apply changes:"
echo "   source ~/.bashrc"
echo ""
echo "   Then type 'brief' to start reading your feeds."