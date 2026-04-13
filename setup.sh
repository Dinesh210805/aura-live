#!/bin/bash
# AURA — one-command setup
set -e

echo "Setting up AURA..."

# Install Python dependencies
pip install -r "requirements copy.txt"

# Create .env from example (never overwrites an existing .env)
cp -n .env.example .env && echo "Created .env — add your API keys before starting." \
  || echo ".env already exists — skipping copy."

echo ""
echo "Setup complete. Next steps:"
echo "  1. Edit .env with your GROQ_API_KEY and GEMINI_API_KEY"
echo "  2. python main.py"
echo "  3. Open http://localhost:8000/demo"
echo ""
echo "For full instructions: cat quickstart.md"
