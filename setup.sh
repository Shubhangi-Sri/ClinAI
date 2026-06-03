#!/bin/bash
# ClinAI Local Setup Script (Mac / Linux)
# Run once: chmod +x setup.sh && ./setup.sh

set -e
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  ClinAI Local Setup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── Backend ──────────────────────────────────────────────────────────────────
echo -e "\n${GREEN}[1/4] Setting up Python backend...${NC}"
cd backend

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt -q

mkdir -p routers middleware audit

echo -e "${GREEN}✅ Backend dependencies installed${NC}"

# ── .env check ───────────────────────────────────────────────────────────────
if grep -q "REPLACE_WITH_YOUR_KEY" .env; then
  echo -e "\n${YELLOW}⚠️  ACTION REQUIRED: Open backend/.env and add your API keys${NC}"
  echo -e "   Minimum required: ANTHROPIC_API_KEY"
  echo -e "   All others are optional (system works without them in demo mode)\n"
fi

cd ..

# ── Frontend ─────────────────────────────────────────────────────────────────
echo -e "${GREEN}[2/4] Setting up React frontend...${NC}"
cd frontend
npm install -q
echo -e "${GREEN}✅ Frontend dependencies installed${NC}"
cd ..

# ── Copy router files ─────────────────────────────────────────────────────────
echo -e "\n${GREEN}[3/4] Checking router files...${NC}"
ROUTERS="backend/routers/health.py backend/routers/asr.py backend/routers/rag.py backend/routers/report.py backend/routers/fhir.py"
MIDDLEWARE="backend/middleware/security.py backend/middleware/encryption.py"
MISSING=0

for f in $ROUTERS $MIDDLEWARE; do
  if [ ! -f "$f" ]; then
    echo -e "   ${YELLOW}Missing: $f — copy from downloaded files${NC}"
    MISSING=1
  fi
done

touch backend/routers/__init__.py backend/middleware/__init__.py 2>/dev/null

if [ $MISSING -eq 0 ]; then
  echo -e "${GREEN}✅ All router files present${NC}"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo -e "  ${BLUE}Next steps:${NC}"
echo "  1. Add your ANTHROPIC_API_KEY to backend/.env"
echo "  2. Open two terminals in VS Code:"
echo ""
echo -e "     ${GREEN}Terminal 1 (Backend):${NC}"
echo "     cd backend && source .venv/bin/activate && python main.py"
echo ""
echo -e "     ${GREEN}Terminal 2 (Frontend):${NC}"
echo "     cd frontend && npm start"
echo ""
echo "  3. Open http://localhost:3000 in your browser"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
