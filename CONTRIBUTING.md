Thank you for your interest in contributing to ClinAI!

Guidelines

- Fork the repository and create a feature branch named `feat/<short-desc>` or a fix branch `fix/<short-desc>`.
- Keep changes small and focused. One logical change per pull request.
- Write clear PR descriptions and reference any related issue numbers.
- Follow existing code style: Python uses 4-space indentation, type hints where helpful; JavaScript follows the existing React patterns.
- Add tests for any new backend logic. Place tests under `backend/tests`.

Local development

- Backend

```bash
cd backend
python -m venv .venv
# Windows
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

- Frontend

```bash
cd frontend
npm install
npm start
```

Contact

If you need help or want to propose a larger change, open an issue or email the maintainer (yourname@example.com).
