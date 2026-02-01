# Kiwi

AI-powered insurance claims management platform with document verification, claims tracking, and intelligent chatbot support.

## Features

- **AI Document Verification**: Automatically verify and validate claim documents using Vertex AI
- **Claims Status Tracking**: Real-time tracking of claim processing status
- **Intelligent Chatbot**: RAG-powered chatbot using Vertex AI to explain insurance terminology and answer questions
- **Minimalist UI/UX**: Clean, intuitive interface for easy navigation


## Tech Stack

### Frontend

- React 18 + TypeScript
- Vite
- TailwindCSS (for minimalist styling)
- React Router
- Axios for API calls

### Backend

- Python 3.11+
- FastAPI
- Google Cloud Vertex AI
- Pydantic for data validation
- SQLAlchemy (for database)

### Cloud & AI

- Google Cloud Platform
- Vertex AI for document analysis and RAG
- Cloud Storage for document uploads

## Project Structure

```
LunatiX/
├── backend/           # FastAPI backend
│   ├── app/
│   │   ├── api/      # API routes
│   │   ├── services/ # Business logic
│   │   ├── models/   # Data models
│   │   └── core/     # Config, dependencies
│   └── requirements.txt
├── frontend/         # React frontend
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── types/
│   └── package.json
└── README.md
```

## Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

Create `.env` files in both backend and frontend directories:

### Backend `.env`

```
GOOGLE_CLOUD_PROJECT=your-project-id
VERTEX_AI_LOCATION=us-central1
GCS_BUCKET_NAME=your-bucket-name
DATABASE_URL=sqlite:///./insurance.db
```

### Frontend `.env`

```
VITE_API_URL=http://localhost:8000
```

## License

MIT
