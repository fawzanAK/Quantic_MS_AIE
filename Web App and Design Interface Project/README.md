# Café Fausse — Web Application

A full-stack website for Café Fausse, a fine-dining restaurant, built for the Web Application & Interface Design project (Quantic MS AI Engineering).

## Solution overview

- **Frontend:** React 18 + JSX, built with Vite, React Router for client-side navigation across 5 pages (Home, Menu, Reservations, About, Gallery). Styling is plain CSS using Flexbox and CSS Grid (see the wireframe file for the intended layout per section), with a shared Header/Footer and a reusable Newsletter form component used on the homepage and in the footer.
- **Backend:** Flask REST API (`/api/reservations`, `/api/newsletter`, `/api/menu`) backed by PostgreSQL via SQLAlchemy.
- **Database:** Two required tables — `customers` (customer_id, customer_name, customer_email, phone_number, newsletter_signup) and `reservations` (reservation_id, customer_id, time_slot, table_number, guests) — plus a small `newsletter_signups` table for people who subscribe without booking a table.
- **Reservation logic:** On submit, the backend looks up or creates the customer record, checks how many of the 30 tables are already booked for the exact requested time slot, and if any are free, assigns one at random and confirms the booking. If all 30 are taken for that slot, it returns an error asking the customer to pick another time. An `/api/reservations/availability` endpoint lets the frontend gray out fully-booked time slots for the selected date.
- **Newsletter signup:** A validated email form (client-side + server-side validation) that stores the subscription in the database, either by flagging an existing customer's `newsletter_signup` field or creating a standalone signup row.

## Design reference

Wireframes for all 5 pages (desktop + mobile, with layout/interaction annotations) were produced first and are the structural basis for the components in `frontend/src/pages`. See the wireframe export shared alongside this repo for the original reference.

## Project structure

```
Web App and Design Interface Project/
├── backend/
│   ├── app.py              # Flask app factory + /api/menu, /api/health
│   ├── config.py           # Reads DATABASE_URL, SECRET_KEY, TOTAL_TABLES from env
│   ├── extensions.py       # SQLAlchemy instance
│   ├── models.py           # Customer, Reservation, NewsletterSignup
│   ├── menu_data.py        # Static menu content
│   ├── init_db.py          # Run once to create tables
│   ├── routes/
│   │   ├── reservations.py # POST /api/reservations, GET /api/reservations/availability
│   │   └── newsletter.py   # POST /api/newsletter
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── pages/           # Home, Menu, Reservations, About, Gallery (+ matching CSS)
    │   ├── components/      # Header, Footer, Newsletter
    │   ├── api.js           # fetch() wrapper for the Flask API
    │   └── App.jsx / main.jsx
    ├── package.json
    └── .env.example
```

## Running locally

### Prerequisites
- Node.js 18+
- Python 3.10+
- PostgreSQL running locally (or accessible via a connection string)

### 1. Database
Create a database and user, e.g.:
```sql
CREATE DATABASE cafe_fausse;
CREATE USER cafe_fausse_user WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE cafe_fausse TO cafe_fausse_user;
```

### 2. Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then edit DATABASE_URL if needed
python init_db.py               # creates the tables
python app.py                   # runs on http://localhost:5000
```

### 3. Frontend
```bash
cd frontend
npm install
cp .env.example .env            # VITE_API_BASE_URL=http://localhost:5000
npm run dev                     # runs on http://localhost:5173
```

Open `http://localhost:5173` in your browser. The reservation form and newsletter signup call the Flask API directly; you can verify their effect on the database with `psql` (e.g. `SELECT * FROM reservations;`) as required by the assignment.

## Notes on requirements coverage

- 5 pages built in React/JSX: Home, Menu, Reservations, About, Gallery.
- Consistent header/nav and footer (contact info, hours, links) across all pages.
- Flexbox used for the header, quick-link cards, awards strip, and form field rows; CSS Grid used for the footer, menu item grids, team bios, and the gallery's masonry-style layout.
- Reservation system assigns one of 30 tables at random per time slot and rejects fully-booked slots.
- Newsletter signup with client + server-side email validation, persisted to PostgreSQL.
- Responsive layouts down to a 375px mobile viewport (nav collapses to a hamburger menu, grids collapse to 1–2 columns).

See `ai-tooling.md` for how Claude was used throughout this project.
