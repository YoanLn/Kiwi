# LunatiX - Insurance Claims Platform

AI-powered insurance claims management platform with document verification, claims tracking, and intelligent chatbot support.

## Features

- **AI Document Verification**: Automatically verify and validate claim documents using Vertex AI
- **Claims Status Tracking**: Real-time tracking of claim processing status
- **Intelligent Chatbot**: RAG-powered chatbot using Vertex AI to explain insurance terminology and answer questions
- **Minimalist UI/UX**: Clean, intuitive interface for easy navigation

## Checklist

Note: Le site doit couvrir deux vues distinctes : la vue client et la vue assureur.

### Côté client

- [ ] Éviter le jargon : réponse séparée en deux (réponse formelle avec renvoi à un document + réponse simplifiée et compréhensible)
- [ ] Possibilité de cliquer sur un mot pour renvoyer à une définition ou demander directement au chatbot ce que ça signifie
- [ ] Voice input + audio summaries (le chatbot regarde où en sont les claims ou d'autres features)
- [ ] Photo-first claims
- [ ] Draft offline
- [ ] Claim summary card
- [ ] Version application mobile

### Côté assureur

- [ ] Checklist manuellement ajoutée par l'assureur (peut-être automatisée basée sur la documentation)
- [ ] Auto triage (classify claim type severity, if the user seemed very angry / stressed)
- [ ] Vérification de documents (detect missing fields, blurry images, wrong doc type)
- [ ] Peut-être dans le futur : détection de fraude + one-tap approvals for low-risk claims (based on thresholds and policy rules)

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
